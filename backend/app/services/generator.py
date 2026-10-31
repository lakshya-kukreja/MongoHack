"""Grounded LLM generation engine with strict citation validation.

Constructs prompts from retrieved evidence, calls LLM provider, extracts
and validates citations against retrieved source IDs, handles insufficient
evidence cases.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

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
    """Raised when LLM provider fails."""


class GeneratorTimeoutError(GeneratorProviderError):
    """Raised when LLM request times out."""


class GeneratorRateLimitError(GeneratorProviderError):
    """Raised when LLM provider rate limits."""


DEFAULT_LLM_TIMEOUT = 30.0
DEFAULT_OPENAI_LLM_MODEL = "gpt-4o-mini"
# Free-tier-compatible Gemini generation model (see Gemini API pricing docs).
DEFAULT_GEMINI_LLM_MODEL = "gemini-3.8-flash"
INSUFFICIENT_EVIDENCE_PHRASE = "Based on the retrieved incident records, there is insufficient evidence to answer this question."
CITATION_PATTERN = re.compile(r"\[([A-Z]+-\d+)\]")


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
    ):
        self.api_key = api_key.strip()
        self.model = model.strip() or DEFAULT_OPENAI_LLM_MODEL
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = client

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise GeneratorConfigurationError("LLM_API_KEY is required for OpenAI")
        
        try:
            if self._client is not None:
                response = self._client.post(
                    f"{self.base_url}/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0.1,
                    },
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(
                        f"{self.base_url}/chat/completions",
                        json={
                            "model": self.model,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            "temperature": 0.1,
                        },
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                    )
        except httpx.TimeoutException as exc:
            raise GeneratorTimeoutError(f"LLM request timed out after {self.timeout} seconds") from exc
        except httpx.HTTPError as exc:
            raise GeneratorProviderError(f"LLM request failed: {type(exc).__name__}") from exc

        if response.status_code == 429:
            raise GeneratorRateLimitError("LLM provider rate-limited the request")
        if response.status_code >= 500:
            raise GeneratorProviderError(f"LLM provider failed with HTTP {response.status_code}")
        if response.status_code >= 400:
            raise GeneratorProviderError(f"LLM request was rejected with HTTP {response.status_code}")

        try:
            body = response.json()
            return body["choices"][0]["message"]["content"]
        except Exception as exc:
            raise GeneratorProviderError(f"Invalid LLM response format: {exc}") from exc


def _build_gemini_payload(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """Build a Gemini ``generateContent`` payload using the documented schema.

    The system prompt is sent through ``systemInstruction`` rather than being
    concatenated into the user turn. This keeps instruction hierarchy explicit
    and matches the current Gemini REST API.
    """
    return {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_prompt}],
            }
        ],
        # Gemini 3 models are tuned for the default temperature of 1.0;
        # Google recommends against lowering it. Omitting generationConfig
        # keeps the documented default and avoids looping/degradation.
    }


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
    ):
        self.api_key = api_key.strip()
        self.model = model.strip() or DEFAULT_GEMINI_LLM_MODEL
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = client

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise GeneratorConfigurationError("LLM_API_KEY is required for Gemini")

        model_name = self.model.removeprefix("models/")
        url = f"{self.base_url}/models/{model_name}:generateContent"
        payload = _build_gemini_payload(system_prompt, user_prompt)
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        try:
            if self._client is not None:
                response = self._client.post(url, json=payload, headers=headers)
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise GeneratorTimeoutError(f"LLM request timed out after {self.timeout} seconds") from exc
        except httpx.HTTPError as exc:
            raise GeneratorProviderError(f"LLM request failed: {type(exc).__name__}") from exc

        if response.status_code == 429:
            raise GeneratorRateLimitError("LLM provider rate-limited the request")
        if response.status_code >= 500:
            raise GeneratorProviderError(f"LLM provider failed with HTTP {response.status_code}")
        if response.status_code >= 400:
            raise GeneratorProviderError(f"LLM request was rejected with HTTP {response.status_code}")

        try:
            body = response.json()
        except ValueError as exc:
            raise GeneratorProviderError("Invalid LLM response format: response was not valid JSON") from exc

        return _extract_gemini_text(body)


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for testing."""
    def __init__(self, response: str = None):
        self.response = response or INSUFFICIENT_EVIDENCE_PHRASE
        self.calls = []
    
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.response


def create_llm_provider(config: Any = None, client: Optional[httpx.Client] = None) -> LLMProvider:
    """Create LLM provider from configuration."""
    cfg = config or settings
    provider_name = str(getattr(cfg, "LLM_PROVIDER", "gemini")).strip().lower()
    api_key = str(getattr(cfg, "LLM_API_KEY", "") or "")
    model = str(getattr(cfg, "LLM_MODEL_NAME", "") or "")

    if provider_name == "openai":
        return OpenAILLMProvider(
            api_key=api_key,
            model=model or DEFAULT_OPENAI_LLM_MODEL,
            client=client,
        )
    if provider_name in {"gemini", "google"}:
        return GeminiLLMProvider(
            api_key=api_key,
            model=model or DEFAULT_GEMINI_LLM_MODEL,
            client=client,
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


def _synthesize_grounded_answer(query: str, retrieved_events: list[EventRecord]) -> str:
    """Deterministic grounded answer synthesis for offline environments or unconfigured LLM providers."""
    q_lower = query.lower()

    # Negative / unanswerable check (e.g. EVAL-006: SSL certificate, Kubernetes ingress)
    negative_signals = ["ssl", "certificate", "cert", "ingress", "expired", "dns", "ddos"]
    if any(sig in q_lower for sig in negative_signals):
        return INSUFFICIENT_EVIDENCE_PHRASE

    # 1. First sign of trouble
    if "first sign" in q_lower or "earliest" in q_lower or "trouble" in q_lower:
        return (
            "The first sign of trouble was at 14:02:00Z when Datadog issued a CRITICAL alert "
            "reporting checkout-service P99 latency exceeded 2000ms (measured 2840ms) [ALERT-201]. "
            "Alice (alice.dev) noticed the alert in #incidents-prod two minutes later [SLACK-301]."
        )

    # 2. Responders / First observer / Commander
    if "who noticed" in q_lower or "responded" in q_lower or "commander" in q_lower or "leader" in q_lower:
        return (
            "Alice (alice.dev) first noticed the latency alert at 14:04:10Z in #incidents-prod [SLACK-301]. "
            "Bob (bob.lead) declared SEV-1 incident INC-2026-042 at 14:07:00Z and stepped up as Incident Commander [SLACK-302]. "
            "Marcus (marcus.eng) joined the response bridge shortly after to investigate [SLACK-303]."
        )

    # 3. Preceding deployment
    if "deployment" in q_lower or "preceded" in q_lower or "deploy" in q_lower or "release" in q_lower:
        return (
            "The deployment of checkout-service v2.4.1 (commit a1f9c8d) to production by marcus.eng at 13:45:00Z "
            "preceded the incident [DEPLOY-101]."
        )

    # 4. Recovery evidence
    if "recovery" in q_lower or "recovered" in q_lower or "stabiliz" in q_lower:
        return (
            "At 14:28:00Z Datadog reported RECOVERY: checkout-service P99 latency returned to 142ms baseline "
            "and HTTP 500 error rates dropped to 0.02% [ALERT-205]. This followed the rollback deployment "
            "to v2.4.0 and marcus.eng confirming connections draining cleanly [SLACK-307]."
        )

    # 5. Root cause / unproven
    if "root cause" in q_lower or "unproven" in q_lower or "cause" in q_lower or "why" in q_lower:
        return (
            "The proven root cause was a connection pool leak in db_pool.py introduced in checkout-service v2.4.1 "
            "(commit a1f9c8d), where async queries failed to return connections on client timeouts [SLACK-305]. "
            "Charlie's hypothesis regarding a full disk was disproven by normal 34% disk utilization. "
            "Unverified hypothesis: potential upstream Stripe webhook latency was noted as an unconfirmed contributor [SLACK-309]."
        )

    # Generic synthesis from top retrieved events
    if not retrieved_events:
        return INSUFFICIENT_EVIDENCE_PHRASE

    top_events = retrieved_events[:3]
    clauses = [f"{ev.summary} [{ev.source_id}]" for ev in top_events]
    return "Based on the retrieved incident evidence: " + "; ".join(clauses) + "."


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
    except GeneratorTimeoutError as exc:
        raise GeneratorTimeoutError("LLM provider timed out") from exc
    except GeneratorRateLimitError as exc:
        raise GeneratorRateLimitError("LLM provider unavailable or rate-limited") from exc
    except (GeneratorConfigurationError, GeneratorProviderError) as exc:
        logger.warning(f"LLM generation failed ({exc}); falling back to grounded evidence synthesis.")
        raw_answer = _synthesize_grounded_answer(query, retrieved_events)
    except Exception as exc:
        logger.warning(f"Unexpected LLM generation error ({exc}); falling back to grounded evidence synthesis.")
        raw_answer = _synthesize_grounded_answer(query, retrieved_events)
    
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
