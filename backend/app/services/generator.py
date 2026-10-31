"""Grounded LLM generation engine with strict citation validation.

Constructs prompts from retrieved evidence, calls LLM provider, extracts
and validates citations against retrieved source IDs, handles insufficient
evidence cases.
"""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.models.event import EventRecord, parse_to_utc_datetime
from app.services.retrieval import RetrievalService, get_retrieval_service


class GeneratorError(Exception):
    """Base exception for generation failures."""


class GeneratorConfigurationError(GeneratorError):
    """Raised when generator configuration is invalid."""


class GeneratorProviderError(GeneratorError):
    """Raised when LLM provider fails.

    Carries non-secret diagnostic metadata so operators can distinguish an
    invalid key (401), a disabled model (403/404), a quota breach (429), and an
    upstream outage (5xx). The client-facing response remains generic.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        status_code: Optional[int] = None,
        error_category: Optional[str] = None,
        provider_status: Optional[str] = None,
        timeout_phase: Optional[str] = None,
        attempts: Optional[int] = None,
    ):
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.status_code = status_code
        self.error_category = error_category
        self.provider_status = provider_status
        self.timeout_phase = timeout_phase
        self.attempts = attempts


class GeneratorTimeoutError(GeneratorProviderError):
    """Raised when LLM request times out."""


class GeneratorRateLimitError(GeneratorProviderError):
    """Raised when LLM provider rate limits."""


_SECRET_PATTERNS = (
    (re.compile(r"AIza[0-9A-Za-z_\-]{20,}"), "[redacted]"),
    (re.compile(r"sk-[0-9A-Za-z_\-]{16,}"), "[redacted]"),
    (re.compile(r"(?i)\b(api[_-]?key|key|token)=([^&\s]+)"), r"\1=[redacted]"),
)

_HTTP_ERROR_CATEGORIES = {
    400: "invalid_request",
    401: "authentication_failed",
    403: "permission_denied",
    404: "model_not_found",
    408: "timeout",
    429: "rate_limited",
}


def _sanitize_provider_message(message: Any, max_length: int = 300) -> str:
    """Redact API-key-like tokens and truncate upstream error text."""
    text = str(message or "").strip()
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    if len(text) > max_length:
        text = text[:max_length] + "..."
    return text


def _classify_provider_error(
    status_code: Optional[int], provider_status: Optional[str] = None
) -> str:
    """Map an HTTP status (and provider status string) to a stable category."""
    if status_code is not None:
        if status_code in _HTTP_ERROR_CATEGORIES:
            return _HTTP_ERROR_CATEGORIES[status_code]
        if 500 <= status_code < 600:
            return "provider_unavailable"
    normalized = str(provider_status or "").strip().lower().replace(" ", "_")
    return normalized or "unknown"


_TIMEOUT_PHASES = {
    httpx.ConnectTimeout: "connect",
    httpx.ReadTimeout: "read",
    httpx.WriteTimeout: "write",
    httpx.PoolTimeout: "pool",
}


def _timeout_phase(exc: httpx.TimeoutException) -> str:
    """Name the httpx timeout phase (connect/read/write/pool).

    ``httpx.Client(timeout=30.0)`` applies the value to each phase separately,
    so the phase tells operators whether the request never connected or
    connected but received no response.
    """
    for exc_type, phase in _TIMEOUT_PHASES.items():
        if isinstance(exc, exc_type):
            return phase
    return "unknown"


def _provider_error_details(
    response: httpx.Response, provider: str, model: str
) -> dict[str, Any]:
    """Extract safe diagnostics from a Gemini/OpenAI error response body."""
    provider_status: Optional[str] = None
    upstream_message: Any = None

    try:
        body = response.json()
    except ValueError:
        body = None

    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            provider_status = error.get("status") or error.get("type") or error.get("code")
            upstream_message = error.get("message")
        elif isinstance(error, str):
            upstream_message = error

    safe_message = (
        _sanitize_provider_message(upstream_message)
        or f"HTTP {response.status_code}"
    )
    return {
        "provider": provider,
        "model": model,
        "status_code": response.status_code,
        "provider_status": str(provider_status) if provider_status is not None else None,
        "error_category": _classify_provider_error(response.status_code, provider_status),
        "safe_message": safe_message,
    }


def _raise_for_provider_error(
    response: httpx.Response,
    provider: str,
    model: str,
    attempts: Optional[int] = None,
) -> None:
    """Raise the correct generator exception for a non-2xx provider response."""
    details = _provider_error_details(response, provider, model)
    message = (
        f"{provider} request failed (HTTP {details['status_code']}, "
        f"category={details['error_category']}): {details['safe_message']}"
    )
    exc_class = (
        GeneratorRateLimitError
        if details["status_code"] == 429
        else GeneratorProviderError
    )
    raise exc_class(
        message,
        provider=details["provider"],
        model=details["model"],
        status_code=details["status_code"],
        error_category=details["error_category"],
        provider_status=details["provider_status"],
        attempts=attempts,
    )


def describe_exception_for_logging(exc: BaseException) -> dict[str, Any]:
    """Return non-secret diagnostic fields for a generator exception.

    Only safe metadata is included. Any upstream text is passed through the
    secret sanitizer so an accidentally echoed API key or query token cannot
    reach the logs.
    """
    return {
        "exception_type": type(exc).__name__,
        "provider": getattr(exc, "provider", None),
        "model": getattr(exc, "model", None),
        "status_code": getattr(exc, "status_code", None),
        "provider_status": getattr(exc, "provider_status", None),
        "error_category": getattr(exc, "error_category", None),
        "timeout_phase": getattr(exc, "timeout_phase", None),
        "attempts": getattr(exc, "attempts", None),
        "message": _sanitize_provider_message(exc),
    }


DEFAULT_LLM_TIMEOUT = 30.0
# Retries stay inside this hard wall-clock deadline, so a 30s contract never
# silently grows into a multi-minute request.
DEFAULT_LLM_REQUEST_DEADLINE_SECONDS = 30.0
DEFAULT_LLM_MAX_ATTEMPTS = 3
DEFAULT_LLM_RETRY_BASE_DELAY_SECONDS = 0.5
DEFAULT_LLM_RETRY_MAX_DELAY_SECONDS = 4.0
DEFAULT_GEMINI_THINKING_LEVEL = "low"
DEFAULT_OPENAI_LLM_MODEL = "gpt-4o-mini"
# Free-tier-compatible Gemini generation model (see Gemini API pricing docs).
DEFAULT_GEMINI_LLM_MODEL = "gemini-3.8-flash"
INSUFFICIENT_EVIDENCE_PHRASE = "Based on the retrieved incident records, there is insufficient evidence to answer this question."
CITATION_PATTERN = re.compile(r"\[([A-Z]+-\d+)\]")

# Transient upstream failures. 501/505 mean the implementation itself is wrong,
# so they are deliberately excluded.
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

# A connect/pool timeout means the request never reached the model, so a retry
# cannot duplicate generation. Read/write timeouts are never retried: the
# provider may already be generating, and a retry would duplicate long work.
RETRYABLE_TIMEOUT_PHASES = frozenset({"connect", "pool"})

SUPPORTED_THINKING_LEVELS = frozenset({"minimal", "low", "medium", "high"})


@dataclass(frozen=True)
class LLMRetryPolicy:
    """Bounded retry budget for one LLM generation request.

    ``deadline_seconds`` is a hard wall-clock budget shared by every attempt
    plus backoff sleeps. ``max_attempts`` counts the first try, so the default
    of 3 means one initial call plus at most two retries.
    """

    max_attempts: int = DEFAULT_LLM_MAX_ATTEMPTS
    base_delay_seconds: float = DEFAULT_LLM_RETRY_BASE_DELAY_SECONDS
    max_delay_seconds: float = DEFAULT_LLM_RETRY_MAX_DELAY_SECONDS
    deadline_seconds: float = DEFAULT_LLM_REQUEST_DEADLINE_SECONDS

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("LLM retry policy requires max_attempts >= 1")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("LLM retry delays must be non-negative")
        if self.deadline_seconds <= 0:
            raise ValueError("LLM request deadline must be positive")

    def backoff_delay(
        self,
        attempt: int,
        remaining_seconds: float,
        rand: Callable[[float, float], float] = random.uniform,
    ) -> Optional[float]:
        """Return a jittered delay, or ``None`` if no retry is allowed.

        ``None`` means either the attempt budget is exhausted or the backoff
        would consume the remaining deadline, in which case the caller must
        surface the failure instead of starting another attempt.
        """
        if attempt >= self.max_attempts or remaining_seconds <= 0:
            return None
        ceiling = min(
            self.max_delay_seconds,
            self.base_delay_seconds * (2 ** (attempt - 1)),
        )
        if ceiling <= 0:
            return 0.0
        delay = rand(0.0, ceiling)
        if delay >= remaining_seconds:
            return None
        return delay


def _normalize_thinking_level(level: Optional[str]) -> Optional[str]:
    """Validate and upper-case a Gemini thinking level; ``None`` disables it.

    The Gemini REST API expects the canonical enum name (``LOW``/``MEDIUM``/
    ``HIGH``/``MINIMAL``). An empty value means "let the provider decide".
    """
    if level is None:
        return None
    normalized = str(level).strip().lower()
    if not normalized or normalized in {"none", "off", "default"}:
        return None
    if normalized not in SUPPORTED_THINKING_LEVELS:
        allowed = ", ".join(sorted(SUPPORTED_THINKING_LEVELS))
        raise GeneratorConfigurationError(
            f"Unsupported LLM_GEMINI_THINKING_LEVEL '{level}'; expected one of: {allowed}"
        )
    return normalized.upper()


def _log_retry(
    provider: str,
    model: str,
    attempt: int,
    policy: LLMRetryPolicy,
    delay: float,
    detail: str,
) -> None:
    """Record a retry decision without logging prompts, payloads, or API keys."""
    logger.warning(
        "Retrying LLM request: provider=%s model=%s %s attempt=%d/%d delay=%.2fs",
        provider,
        model,
        detail,
        attempt,
        policy.max_attempts,
        delay,
    )


def _post_json_with_retries(
    *,
    provider: str,
    model: str,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
    policy: LLMRetryPolicy,
    client: Optional[httpx.Client],
    sleep: Callable[[float], None],
    rand: Callable[[float, float], float],
) -> httpx.Response:
    """POST JSON with bounded retries inside a hard overall deadline.

    Retries only transient failures (429 and retryable 5xx, plus connect/pool
    timeouts). Permanent client errors (400/401/403/404) and read/write
    timeouts fail immediately. When the deadline or attempt budget is spent,
    the last provider error is raised so external diagnostics stay intact.
    """
    deadline_at = time.monotonic() + policy.deadline_seconds
    attempt = 0

    while True:
        attempt += 1
        remaining = deadline_at - time.monotonic()
        if remaining <= 0:
            raise GeneratorTimeoutError(
                f"LLM request deadline of {policy.deadline_seconds:g}s exceeded "
                f"before attempt {attempt}",
                provider=provider,
                model=model,
                error_category="timeout",
                timeout_phase="deadline",
                attempts=attempt - 1,
            )

        # Never let one attempt outlive the shared deadline.
        attempt_timeout = max(min(timeout, remaining), 0.001)
        try:
            if client is not None:
                response = client.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=attempt_timeout,
                )
            else:
                with httpx.Client(timeout=attempt_timeout) as owned_client:
                    response = owned_client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            phase = _timeout_phase(exc)
            timeout_error = GeneratorTimeoutError(
                f"LLM request timed out after {attempt_timeout:g} seconds "
                f"(phase={phase}, attempt={attempt}/{policy.max_attempts})",
                provider=provider,
                model=model,
                error_category="timeout",
                timeout_phase=phase,
                attempts=attempt,
            )
            if phase not in RETRYABLE_TIMEOUT_PHASES:
                raise timeout_error from exc
            delay = policy.backoff_delay(
                attempt,
                deadline_at - time.monotonic(),
                rand,
            )
            if delay is None:
                raise timeout_error from exc
            _log_retry(provider, model, attempt, policy, delay, f"timeout phase={phase}")
            sleep(delay)
            continue
        except httpx.HTTPError as exc:
            raise GeneratorProviderError(
                f"LLM request failed: {type(exc).__name__}",
                provider=provider,
                model=model,
                error_category="network_error",
                attempts=attempt,
            ) from exc

        if response.status_code in RETRYABLE_STATUS_CODES:
            delay = policy.backoff_delay(
                attempt,
                deadline_at - time.monotonic(),
                rand,
            )
            if delay is not None:
                _log_retry(
                    provider,
                    model,
                    attempt,
                    policy,
                    delay,
                    f"status={response.status_code}",
                )
                sleep(delay)
                continue

        if response.status_code >= 400:
            _raise_for_provider_error(response, provider, model, attempts=attempt)
        return response


SYSTEM_PROMPT = """You are an expert Incident Timeline Investigator. Your duty is to analyze software incident evidence with extreme rigor, fidelity, and precision.

RULES:
1. ONLY make claims directly substantiated by the provided EVIDENCE RECORDS.
2. For EVERY factual claim you make, immediately append the citation token: [SOURCE_ID].
3. If multiple records support a claim, cite each: [SOURCE_ID_1] [SOURCE_ID_2].
4. NEVER invent, infer, or hallucinate a source ID.
5. CHRONOLOGY: Respect the timestamps provided in the evidence records. Do not alter or assume the sequence of events.
6. ROOT CAUSE & UNPROVEN HYPOTHESES:
   - Clearly distinguish proven facts (supported by metrics/logs/code changes) from human hypotheses or unverified conjectures in chat.
   - If an engineer speculated something was the root cause, but no metrics confirm it, explicitly label it as "Unverified Hypothesis by [Actor] ([SOURCE_ID])".
7. CONTRADICTIONS: If two pieces of evidence contradict each other, highlight the discrepancy explicitly.
8. INSUFFICIENT EVIDENCE: If the records do not contain enough evidence to answer a question, state: "Based on the retrieved incident records, there is insufficient evidence to answer this question." and cite nothing.
"""


class CitationRecord:
    """Structured citation record."""
    def __init__(
        self,
        source_id: str,
        source_type: str,
        timestamp: str,
        author_or_actor: str,
        channel_or_service: str,
        summary: str,
        snippet: str,
    ):
        self.source_id = source_id
        self.source_type = source_type
        self.timestamp = timestamp
        self.author_or_actor = author_or_actor
        self.channel_or_service = channel_or_service
        self.summary = summary
        self.snippet = snippet

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "timestamp": self.timestamp,
            "author_or_actor": self.author_or_actor,
            "channel_or_service": self.channel_or_service,
            "summary": self.summary,
            "snippet": self.snippet,
        }


class QueryResponse:
    """Structured query response."""
    def __init__(
        self,
        answer: str,
        citations: list[dict[str, Any]],
        unverified_citations: list[str],
        retrieved_events: list[dict[str, Any]],
    ):
        self.answer = answer
        self.citations = citations
        self.unverified_citations = unverified_citations
        self.retrieved_events = retrieved_events

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "citations": self.citations,
            "unverified_citations": self.unverified_citations,
            "retrieved_events": self.retrieved_events,
        }


class LLMProvider:
    """Base LLM provider."""
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError


class OpenAILLMProvider(LLMProvider):
    """OpenAI LLM provider."""
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_OPENAI_LLM_MODEL,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = DEFAULT_LLM_TIMEOUT,
        client: Optional[httpx.Client] = None,
        retry_policy: Optional[LLMRetryPolicy] = None,
        sleep: Callable[[float], None] = time.sleep,
        rand: Callable[[float, float], float] = random.uniform,
    ):
        self.api_key = api_key.strip()
        self.model = model.strip() or DEFAULT_OPENAI_LLM_MODEL
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = client
        self.retry_policy = retry_policy or LLMRetryPolicy()
        self._sleep = sleep
        self._rand = rand

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise GeneratorConfigurationError("LLM_API_KEY is required for OpenAI")

        # OpenAI has no Gemini thinking settings; this payload stays unchanged.
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
        }
        response = _post_json_with_retries(
            provider="openai",
            model=self.model,
            url=f"{self.base_url}/chat/completions",
            payload=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
            policy=self.retry_policy,
            client=self._client,
            sleep=self._sleep,
            rand=self._rand,
        )

        try:
            body = response.json()
            return body["choices"][0]["message"]["content"]
        except Exception as exc:
            raise GeneratorProviderError(
                f"Invalid LLM response format: {type(exc).__name__}",
                provider="openai",
                model=self.model,
                error_category="invalid_response",
            ) from exc


def _build_gemini_payload(
    system_prompt: str,
    user_prompt: str,
    thinking_level: Optional[str] = None,
) -> dict[str, Any]:
    """Build a Gemini ``generateContent`` payload using the documented schema.

    The system prompt is sent through ``systemInstruction`` rather than being
    concatenated into the user turn. This keeps instruction hierarchy explicit
    and matches the current Gemini REST API.

    ``thinking_level`` is only emitted for Gemini (never for OpenAI). Omitting
    it leaves the provider default, which for ``gemini-3.8-flash`` is medium
    thinking and adds avoidable latency for citation-grounded extraction.
    """
    payload: dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_prompt}],
            }
        ],
        # Gemini 3 models are tuned for the default temperature of 1.0;
        # Google recommends against lowering it, so only thinking is configured.
    }
    if thinking_level:
        payload["generationConfig"] = {
            "thinkingConfig": {"thinkingLevel": thinking_level}
        }
    return payload


def _extract_gemini_text(body: Any) -> str:
    """Extract the visible answer text from a Gemini response body.

    Gemini can return multiple parts, including internal ``thought`` parts for
    thinking models and parts that contain no text. Only visible text parts are
    concatenated. Safety blocks and empty candidates raise provider errors.
    """
    if not isinstance(body, dict):
        raise GeneratorProviderError("Invalid LLM response format: response body is not an object")

    prompt_feedback = body.get("promptFeedback")
    if isinstance(prompt_feedback, dict) and prompt_feedback.get("blockReason"):
        raise GeneratorProviderError(
            f"Gemini blocked the prompt: {prompt_feedback['blockReason']}"
        )

    candidates = body.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise GeneratorProviderError("Invalid LLM response format: missing candidates")

    candidate = candidates[0]
    if not isinstance(candidate, dict):
        raise GeneratorProviderError("Invalid LLM response format: malformed candidate")

    content = candidate.get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list) or not parts:
        finish_reason = candidate.get("finishReason") or "unknown"
        raise GeneratorProviderError(
            f"Invalid LLM response format: no content parts (finishReason={finish_reason})"
        )

    text_parts: list[str] = []
    for part in parts:
        if not isinstance(part, dict) or part.get("thought") is True:
            continue
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            text_parts.append(text)

    answer = "\n".join(text_parts).strip()
    if not answer:
        raise GeneratorProviderError("Invalid LLM response format: empty answer text")
    return answer


class GeminiLLMProvider(LLMProvider):
    """Google Gemini LLM provider using the direct REST API via httpx."""
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_GEMINI_LLM_MODEL,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout: float = DEFAULT_LLM_TIMEOUT,
        client: Optional[httpx.Client] = None,
        thinking_level: Optional[str] = DEFAULT_GEMINI_THINKING_LEVEL,
        retry_policy: Optional[LLMRetryPolicy] = None,
        sleep: Callable[[float], None] = time.sleep,
        rand: Callable[[float, float], float] = random.uniform,
    ):
        self.api_key = api_key.strip()
        self.model = model.strip() or DEFAULT_GEMINI_LLM_MODEL
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = client
        self.thinking_level = _normalize_thinking_level(thinking_level)
        self.retry_policy = retry_policy or LLMRetryPolicy()
        self._sleep = sleep
        self._rand = rand

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise GeneratorConfigurationError("LLM_API_KEY is required for Gemini")

        model_name = self.model.removeprefix("models/")
        url = f"{self.base_url}/models/{model_name}:generateContent"
        payload = _build_gemini_payload(
            system_prompt,
            user_prompt,
            thinking_level=self.thinking_level,
        )
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        response = _post_json_with_retries(
            provider="gemini",
            model=self.model,
            url=url,
            payload=payload,
            headers=headers,
            timeout=self.timeout,
            policy=self.retry_policy,
            client=self._client,
            sleep=self._sleep,
            rand=self._rand,
        )

        try:
            body = response.json()
        except ValueError as exc:
            raise GeneratorProviderError(
                "Invalid LLM response format: response was not valid JSON",
                provider="gemini",
                model=self.model,
                error_category="invalid_response",
            ) from exc

        return _extract_gemini_text(body)


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for testing."""
    def __init__(self, response: str = None):
        self.response = response or INSUFFICIENT_EVIDENCE_PHRASE
        self.calls = []
    
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.response


def _config_number(cfg: Any, name: str, default: float) -> float:
    """Read a numeric setting, falling back when the config object omits it."""
    value = getattr(cfg, name, None)
    return default if value is None else float(value)


def create_llm_provider(config: Any = None, client: Optional[httpx.Client] = None) -> LLMProvider:
    """Create LLM provider from configuration."""
    cfg = config or settings
    provider_name = str(getattr(cfg, "LLM_PROVIDER", "gemini")).strip().lower()
    api_key = str(getattr(cfg, "LLM_API_KEY", "") or "")
    model = str(getattr(cfg, "LLM_MODEL_NAME", "") or "")
    retry_policy = LLMRetryPolicy(
        max_attempts=int(_config_number(cfg, "LLM_MAX_ATTEMPTS", DEFAULT_LLM_MAX_ATTEMPTS)),
        base_delay_seconds=_config_number(
            cfg, "LLM_RETRY_BASE_DELAY_SECONDS", DEFAULT_LLM_RETRY_BASE_DELAY_SECONDS
        ),
        max_delay_seconds=_config_number(
            cfg, "LLM_RETRY_MAX_DELAY_SECONDS", DEFAULT_LLM_RETRY_MAX_DELAY_SECONDS
        ),
        deadline_seconds=_config_number(
            cfg, "LLM_REQUEST_DEADLINE_SECONDS", DEFAULT_LLM_REQUEST_DEADLINE_SECONDS
        ),
    )

    if provider_name == "openai":
        return OpenAILLMProvider(
            api_key=api_key,
            model=model or DEFAULT_OPENAI_LLM_MODEL,
            client=client,
            retry_policy=retry_policy,
        )
    if provider_name in {"gemini", "google"}:
        thinking_level = getattr(
            cfg, "LLM_GEMINI_THINKING_LEVEL", DEFAULT_GEMINI_THINKING_LEVEL
        )
        if thinking_level is None:
            thinking_level = DEFAULT_GEMINI_THINKING_LEVEL
        return GeminiLLMProvider(
            api_key=api_key,
            model=model or DEFAULT_GEMINI_LLM_MODEL,
            client=client,
            thinking_level=thinking_level,
            retry_policy=retry_policy,
        )

    raise GeneratorConfigurationError(f"Unsupported LLM_PROVIDER '{provider_name}'")


def format_evidence_context(events: list[EventRecord]) -> str:
    """Format retrieved events as evidence context for the LLM."""
    if not events:
        return ""
    
    # Sort chronologically
    sorted_events = sorted(events, key=lambda e: (e.timestamp, e.source_id))
    
    context_parts = []
    for event in sorted_events:
        iso_ts = event.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ") if hasattr(event.timestamp, 'strftime') else str(event.timestamp)
        context_parts.append(
            f"[EVIDENCE RECORD {event.source_id}]\n"
            f"Source ID: {event.source_id}\n"
            f"Timestamp: {iso_ts}\n"
            f"Type: {event.source_type.value if hasattr(event.source_type, 'value') else event.source_type} | "
            f"Service: {event.channel_or_service} | Actor: {event.author_or_actor}\n"
            f"Summary: {event.summary}\n"
            f"Content: {event.raw_content}"
        )
    
    return "\n\n".join(context_parts)


def validate_citations(answer: str, retrieved_events: list[EventRecord]) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Extract and validate citations against retrieved events.
    
    Returns (cleaned_answer, verified_citations, unverified_citations)
    """
    valid_ids = {event.source_id for event in retrieved_events}
    event_map = {event.source_id: event for event in retrieved_events}
    
    # Extract all citations
    found_citations = CITATION_PATTERN.findall(answer)
    
    verified = []
    unverified = []
    
    for cid in found_citations:
        if cid in valid_ids and cid not in [c["source_id"] for c in verified]:
            event = event_map[cid]
            iso_ts = event.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ") if hasattr(event.timestamp, 'strftime') else str(event.timestamp)
            # Create snippet (first 100 chars of raw content)
            snippet = event.raw_content[:100].strip()
            if len(event.raw_content) > 100:
                snippet += "..."
            
            verified.append({
                "source_id": event.source_id,
                "source_type": event.source_type.value if hasattr(event.source_type, 'value') else str(event.source_type),
                "timestamp": iso_ts,
                "author_or_actor": event.author_or_actor,
                "channel_or_service": event.channel_or_service,
                "summary": event.summary,
                "snippet": snippet,
            })
        elif cid not in valid_ids:
            if cid not in unverified:
                unverified.append(cid)
    
    # Check if answer indicates insufficient evidence
    if INSUFFICIENT_EVIDENCE_PHRASE in answer:
        # If citing insufficient evidence, ensure no citations
        if verified or found_citations:
            # Clean citations if present
            cleaned_answer = INSUFFICIENT_EVIDENCE_PHRASE
            verified = []
            unverified = list(set(found_citations))  # All found are invalid in this context
        else:
            cleaned_answer = INSUFFICIENT_EVIDENCE_PHRASE
    else:
        cleaned_answer = answer
    
    return cleaned_answer, verified, unverified


def generate_answer(
    query: str,
    retrieved_events: list[EventRecord],
    llm_provider: Optional[LLMProvider] = None,
    system_prompt: Optional[str] = None,
) -> QueryResponse:
    """Generate grounded answer from retrieved events."""
    if not retrieved_events:
        return QueryResponse(
            answer=INSUFFICIENT_EVIDENCE_PHRASE,
            citations=[],
            unverified_citations=[],
            retrieved_events=[],
        )
    
    provider = llm_provider or create_llm_provider()
    sys_prompt = system_prompt or SYSTEM_PROMPT
    
    context = format_evidence_context(retrieved_events)
    user_prompt = f"EVIDENCE RECORDS:\n{context}\n\nQUESTION: {query}\n\nProvide a precise answer grounded only in the evidence above."
    
    try:
        raw_answer = provider.generate(sys_prompt, user_prompt)
    except GeneratorError:
        # Preserve type and diagnostic metadata (provider, model, status,
        # category) so the API layer can log the real cause. Rewrapping here
        # used to hide the upstream HTTP status behind a generic message.
        raise
    except Exception as exc:
        raise GeneratorProviderError(
            f"Unexpected LLM provider failure: {type(exc).__name__}",
            error_category="unexpected_error",
        ) from exc
    
    cleaned_answer, verified_citations, unverified_citations = validate_citations(raw_answer, retrieved_events)
    
    # Format retrieved events for response
    retrieved_formatted = []
    for event in retrieved_events:
        iso_ts = event.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ") if hasattr(event.timestamp, 'strftime') else str(event.timestamp)
        retrieved_formatted.append({
            "source_id": event.source_id,
            "timestamp": iso_ts,
            "source_type": event.source_type.value if hasattr(event.source_type, 'value') else str(event.source_type),
            "summary": event.summary,
            "score": getattr(event, 'score', 0.0),
        })
    
    return QueryResponse(
        answer=cleaned_answer,
        citations=verified_citations,
        unverified_citations=unverified_citations,
        retrieved_events=retrieved_formatted,
    )


class Generator:
    """High-level generator service."""
    def __init__(self, retrieval_service: Optional[RetrievalService] = None, llm_provider: Optional[LLMProvider] = None):
        self.retrieval_service = retrieval_service or get_retrieval_service()
        self.llm_provider = llm_provider or create_llm_provider()
    
    def query(
        self,
        incident_id: str,
        query: str,
        limit: int = 10,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> QueryResponse:
        """Full RAG pipeline: retrieve -> generate -> validate."""
        try:
            # Retrieve relevant events
            retrieved_events = self.retrieval_service.search_events(
                incident_id=incident_id,
                query=query,
                limit=limit,
                start_time=start_time,
                end_time=end_time,
            )
            
            # Generate answer
            response = generate_answer(query, retrieved_events, llm_provider=self.llm_provider)
            return response
        except Exception as exc:
            logger.error(f"Generation pipeline failed: {exc}")
            raise


def get_generator() -> Generator:
    """Get generator instance."""
    return Generator()


# Module aliases
generate_grounded_answer = generate_answer
validate_citations_against_retrieved = validate_citations
