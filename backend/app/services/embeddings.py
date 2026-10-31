"""Vector embedding generation for canonical incident event text.

The module keeps provider-specific HTTP details isolated behind small provider
classes so the rest of the application can depend on a stable embedding API.
It never fabricates vectors: configuration problems, empty inputs, provider
failures, and malformed provider responses all raise explicit exceptions.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.models.event import EventRecord

DEFAULT_BATCH_SIZE = 64
DEFAULT_EMBEDDING_TIMEOUT = 10.0

DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_GEMINI_EMBEDDING_MODEL = "gemini-embedding-2"

# The Atlas vector index is fixed at 1536 dimensions. Gemini Embedding 2 and
# Gemini Embedding 001 both support Matryoshka output truncation, so we request
# exactly this size instead of storing their 3072-dimension default.
DEFAULT_GEMINI_OUTPUT_DIMENSIONS = 1536
GEMINI_MIN_OUTPUT_DIMENSIONS = 128
GEMINI_MAX_OUTPUT_DIMENSIONS = 3072
GEMINI_DIMENSION_CONFIGURABLE_MODELS = frozenset(
    {"gemini-embedding-2", "gemini-embedding-001"}
)

# Default output dimensions for the models documented in spec.md. Unknown
# models are still validated for non-empty, finite, and consistent dimensions.
MODEL_DIMENSIONS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
    "text-embedding-004": 768,
    "embedding-001": 768,
    "gemini-embedding-001": 3072,
    "gemini-embedding-2": 3072,
}


class EmbeddingError(Exception):
    """Base exception for embedding generation failures."""


class EmbeddingConfigurationError(EmbeddingError):
    """Raised when embedding provider configuration is missing or unsupported."""


class EmbeddingInputError(EmbeddingError, ValueError):
    """Raised when embedding input text is empty, malformed, or unsupported."""


class EmbeddingProviderError(EmbeddingError):
    """Raised when an upstream embedding provider fails or returns bad data."""


class EmbeddingTimeoutError(EmbeddingProviderError):
    """Raised when an embedding provider request exceeds its timeout."""


class EmbeddingRateLimitError(EmbeddingProviderError):
    """Raised when an embedding provider rejects a request due to rate limits."""


class EmbeddingDimensionError(EmbeddingError):
    """Raised when a vector dimension does not match the Atlas index contract."""


def validate_embedding_dimension(
    vector: list[float],
    expected_dimension: int,
    context: str = "embedding",
) -> list[float]:
    """Validate one vector against the configured Atlas vector index dimension.

    Args:
        vector: Numeric embedding vector to validate.
        expected_dimension: Required dimension (for example 1536).
        context: Human-readable label used in error messages.

    Returns:
        The validated vector, unchanged.

    Raises:
        EmbeddingConfigurationError: If ``expected_dimension`` is invalid.
        EmbeddingDimensionError: If the vector length differs from the index.
    """
    if not isinstance(expected_dimension, int) or isinstance(expected_dimension, bool) or expected_dimension < 1:
        raise EmbeddingConfigurationError("expected_dimension must be a positive integer")
    if not isinstance(vector, (list, tuple)):
        raise EmbeddingProviderError(f"{context} is not a list of numbers")
    if len(vector) != expected_dimension:
        raise EmbeddingDimensionError(
            f"{context} has dimension {len(vector)}, but the Atlas vector index "
            f"requires {expected_dimension}; refusing to persist an incompatible vector"
        )
    return list(vector)


class EmbeddingProvider(ABC):
    """Provider interface for generating embedding vectors from text."""

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate one embedding vector for each input text.

        Args:
            texts: Non-empty text strings to embed.

        Returns:
            A list of float vectors in the same order as ``texts``.

        Raises:
            EmbeddingError: If the provider is misconfigured or fails.
        """


def _normalize_texts(texts: list[str]) -> list[str]:
    """Validate and normalize embedding inputs without changing their meaning."""
    if not isinstance(texts, list):
        raise EmbeddingInputError("Embedding input must be a list of strings")

    normalized: list[str] = []
    for index, text in enumerate(texts):
        if not isinstance(text, str):
            raise EmbeddingInputError(
                f"Embedding input at index {index} must be a string, got {type(text).__name__}"
            )
        stripped = text.strip()
        if not stripped:
            raise EmbeddingInputError(f"Embedding input at index {index} cannot be empty")
        normalized.append(stripped)
    return normalized


def _normalize_model_name(model: str) -> str:
    """Return a provider model name without a ``models/`` prefix."""
    normalized_model = model.strip().lower()
    if normalized_model.startswith("models/"):
        normalized_model = normalized_model.removeprefix("models/")
    return normalized_model


def _resolve_expected_dimension(
    model: str, expected_dimension: Optional[int]
) -> Optional[int]:
    """Resolve the expected vector dimension for a provider model."""
    if expected_dimension is not None:
        return expected_dimension
    return MODEL_DIMENSIONS.get(_normalize_model_name(model))


def _resolve_gemini_dimensions(
    model: str,
    expected_dimension: Optional[int],
    output_dimensions: Optional[int],
) -> Optional[int]:
    """Resolve the requested Gemini output size and enforce API limits."""
    normalized_model = _normalize_model_name(model)

    requested = expected_dimension if expected_dimension is not None else output_dimensions
    if requested is None and normalized_model in GEMINI_DIMENSION_CONFIGURABLE_MODELS:
        requested = DEFAULT_GEMINI_OUTPUT_DIMENSIONS

    if requested is None:
        return MODEL_DIMENSIONS.get(normalized_model)

    if (
        not isinstance(requested, int)
        or isinstance(requested, bool)
        or requested < GEMINI_MIN_OUTPUT_DIMENSIONS
        or requested > GEMINI_MAX_OUTPUT_DIMENSIONS
    ):
        raise EmbeddingConfigurationError(
            f"Gemini embedding dimension must be an integer between "
            f"{GEMINI_MIN_OUTPUT_DIMENSIONS} and {GEMINI_MAX_OUTPUT_DIMENSIONS}, got {requested!r}"
        )

    if (
        normalized_model not in GEMINI_DIMENSION_CONFIGURABLE_MODELS
        and MODEL_DIMENSIONS.get(normalized_model) not in {None, requested}
    ):
        raise EmbeddingConfigurationError(
            f"Gemini model '{model}' has a fixed dimension of "
            f"{MODEL_DIMENSIONS[normalized_model]} and cannot emit {requested}"
        )

    return requested


def _validate_vectors(
    vectors: Any,
    expected_count: int,
    expected_dimension: Optional[int] = None,
) -> list[list[float]]:
    """Validate provider vectors for count, numeric type, finiteness, and dimensions."""
    if not isinstance(vectors, (list, tuple)):
        raise EmbeddingProviderError("Embedding provider returned a non-list vector payload")
    if len(vectors) != expected_count:
        raise EmbeddingProviderError(
            f"Embedding provider returned {len(vectors)} vectors for {expected_count} inputs"
        )

    validated: list[list[float]] = []
    dimension = expected_dimension

    for vector_index, vector in enumerate(vectors):
        if not isinstance(vector, (list, tuple)):
            raise EmbeddingProviderError(
                f"Embedding at index {vector_index} is not a list of numbers"
            )
        if not vector:
            raise EmbeddingProviderError(f"Embedding at index {vector_index} is empty")

        converted: list[float] = []
        for value in vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise EmbeddingProviderError(
                    f"Embedding at index {vector_index} contains a non-numeric value"
                )
            numeric_value = float(value)
            if not math.isfinite(numeric_value):
                raise EmbeddingProviderError(
                    f"Embedding at index {vector_index} contains a non-finite value"
                )
            converted.append(numeric_value)

        if dimension is None:
            dimension = len(converted)
        elif len(converted) != dimension:
            raise EmbeddingProviderError(
                f"Embedding at index {vector_index} has dimension {len(converted)}, "
                f"expected {dimension}"
            )

        validated.append(converted)

    return validated


def _l2_normalize(vector: list[float]) -> list[float]:
    """Return an L2-normalized copy of a vector, leaving zero vectors unchanged.

    ``gemini-embedding-2`` auto-normalizes truncated Matryoshka dimensions, but
    ``gemini-embedding-001`` requires the caller to normalize output smaller
    than its native 3072 dimensions. Atlas uses cosine similarity, which is
    scale invariant, but normalizing keeps stored vectors consistent with
    Google's documented usage and with any future dot-product consumers.
    """
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0 or not math.isfinite(norm):
        return list(vector)
    return [value / norm for value in vector]


def _post_embedding_request(
    provider_name: str,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    client: Optional[httpx.Client],
    timeout: float,
) -> httpx.Response:
    """Execute an isolated embedding HTTP request and map transport errors."""
    try:
        if client is not None:
            response = client.post(url, json=payload, headers=headers)
        else:
            with httpx.Client(timeout=timeout) as request_client:
                response = request_client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        raise EmbeddingTimeoutError(
            f"{provider_name} embedding request timed out after {timeout} seconds"
        ) from exc
    except httpx.HTTPError as exc:
        raise EmbeddingProviderError(
            f"{provider_name} embedding request failed: {type(exc).__name__}"
        ) from exc

    if response.status_code == 429:
        raise EmbeddingRateLimitError(
            f"{provider_name} embedding provider rate-limited the request"
        )
    if response.status_code >= 500:
        raise EmbeddingProviderError(
            f"{provider_name} embedding provider failed with HTTP {response.status_code}"
        )
    if response.status_code >= 400:
        raise EmbeddingProviderError(
            f"{provider_name} embedding request was rejected with HTTP {response.status_code}"
        )
    return response


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI embeddings provider using the direct REST API via httpx."""

    provider_name = "OpenAI"

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_OPENAI_EMBEDDING_MODEL,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = DEFAULT_EMBEDDING_TIMEOUT,
        client: Optional[httpx.Client] = None,
        expected_dimension: Optional[int] = None,
    ):
        """Initialize the OpenAI embedding provider.

        Args:
            api_key: OpenAI API key from settings.
            model: OpenAI embedding model name.
            base_url: OpenAI API base URL (overrideable for tests/proxies).
            timeout: Request timeout in seconds.
            client: Optional injected httpx client for offline tests.
            expected_dimension: Optional dimension override; otherwise inferred.
        """
        self.api_key = api_key.strip()
        self.model = model.strip() or DEFAULT_OPENAI_EMBEDDING_MODEL
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = client
        self.expected_dimension = _resolve_expected_dimension(
            self.model, expected_dimension
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings through OpenAI's ``/embeddings`` endpoint."""
        normalized = _normalize_texts(texts)
        if not normalized:
            return []
        if not self.api_key:
            raise EmbeddingConfigurationError(
                "EMBEDDING_API_KEY is required for the OpenAI embedding provider"
            )

        response = _post_embedding_request(
            provider_name=self.provider_name,
            url=f"{self.base_url}/embeddings",
            payload={"model": self.model, "input": normalized},
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            client=self._client,
            timeout=self.timeout,
        )

        try:
            body = response.json()
        except ValueError as exc:
            raise EmbeddingProviderError(
                "OpenAI embedding response was not valid JSON"
            ) from exc

        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            raise EmbeddingProviderError(
                "OpenAI embedding response is missing a valid 'data' list"
            )
        if len(data) != len(normalized):
            raise EmbeddingProviderError(
                f"OpenAI embedding response returned {len(data)} vectors for "
                f"{len(normalized)} inputs"
            )

        if all(isinstance(item, dict) and isinstance(item.get("index"), int) for item in data):
            data = sorted(data, key=lambda item: item["index"])
            if [item["index"] for item in data] != list(range(len(data))):
                raise EmbeddingProviderError(
                    "OpenAI embedding response contained invalid or duplicate indexes"
                )

        vectors = []
        for item in data:
            if not isinstance(item, dict) or "embedding" not in item:
                raise EmbeddingProviderError(
                    "OpenAI embedding response item is missing the 'embedding' field"
                )
            vectors.append(item["embedding"])

        return _validate_vectors(vectors, len(normalized), self.expected_dimension)


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Google Gemini embeddings provider using the direct REST API via httpx."""

    provider_name = "Gemini"

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_GEMINI_EMBEDDING_MODEL,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout: float = DEFAULT_EMBEDDING_TIMEOUT,
        client: Optional[httpx.Client] = None,
        expected_dimension: Optional[int] = None,
        output_dimensions: Optional[int] = None,
    ):
        """Initialize the Gemini embedding provider.

        Args:
            api_key: Gemini API key from settings.
            model: Gemini embedding model name. Defaults to the current stable
                ``gemini-embedding-2`` model.
            base_url: Gemini API base URL (overrideable for tests/proxies).
            timeout: Request timeout in seconds.
            client: Optional injected httpx client for offline tests.
            expected_dimension: Optional validated dimension override.
            output_dimensions: Optional requested ``outputDimensionality``.
                Defaults to 1536 for Matryoshka-capable Gemini models so vectors
                match the Atlas vector index.
        """
        self.api_key = api_key.strip()
        self.model = model.strip() or DEFAULT_GEMINI_EMBEDDING_MODEL
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = client
        self.expected_dimension = _resolve_gemini_dimensions(
            self.model, expected_dimension, output_dimensions
        )
        self.request_dimensions = (
            self.expected_dimension
            if _normalize_model_name(self.model) in GEMINI_DIMENSION_CONFIGURABLE_MODELS
            else None
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings through Gemini's ``batchEmbedContents`` endpoint."""
        normalized = _normalize_texts(texts)
        if not normalized:
            return []
        if not self.api_key:
            raise EmbeddingConfigurationError(
                "EMBEDDING_API_KEY is required for the Gemini embedding provider"
            )

        model_name = _normalize_model_name(self.model)
        requests: list[dict[str, Any]] = []
        for text in normalized:
            item: dict[str, Any] = {
                "model": f"models/{model_name}",
                "content": {"parts": [{"text": text}]},
            }
            if self.request_dimensions is not None:
                # Gemini Embedding models support Matryoshka truncation, so we
                # must ask for the Atlas index size explicitly. The
                # ``batchEmbedContents`` endpoint reads the per-request
                # ``EmbedContentRequest.outputDimensionality`` field; the
                # nested ``embedContentConfig`` object is only honored by
                # ``models.embedContent`` and is silently ignored here, which
                # makes ``gemini-embedding-001`` return its native 3072 dims.
                item["outputDimensionality"] = self.request_dimensions
            requests.append(item)

        response = _post_embedding_request(
            provider_name=self.provider_name,
            url=f"{self.base_url}/models/{model_name}:batchEmbedContents",
            payload={"requests": requests},
            headers={
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            client=self._client,
            timeout=self.timeout,
        )

        try:
            body = response.json()
        except ValueError as exc:
            raise EmbeddingProviderError(
                "Gemini embedding response was not valid JSON"
            ) from exc

        embeddings = body.get("embeddings") if isinstance(body, dict) else None
        if not isinstance(embeddings, list):
            raise EmbeddingProviderError(
                "Gemini embedding response is missing a valid 'embeddings' list"
            )
        if len(embeddings) != len(normalized):
            raise EmbeddingProviderError(
                f"Gemini embedding response returned {len(embeddings)} vectors for "
                f"{len(normalized)} inputs"
            )

        vectors = []
        for item in embeddings:
            if not isinstance(item, dict) or "values" not in item:
                raise EmbeddingProviderError(
                    "Gemini embedding response item is missing the 'values' field"
                )
            vectors.append(item["values"])

        # Validate the raw provider vectors *before* normalization so an
        # ignored/unsupported dimension flag fails loudly instead of being
        # silently truncated or rescaled.
        validated = _validate_vectors(
            vectors, len(normalized), self.expected_dimension
        )
        if (
            model_name == "gemini-embedding-001"
            and self.expected_dimension is not None
            and self.expected_dimension != GEMINI_MAX_OUTPUT_DIMENSIONS
        ):
            validated = [_l2_normalize(vector) for vector in validated]
        return validated


def create_embedding_provider(
    config: Any = None,
    client: Optional[httpx.Client] = None,
) -> EmbeddingProvider:
    """Build the configured embedding provider without performing network I/O.

    Args:
        config: Settings-like object. Defaults to the application settings.
        client: Optional injected httpx client for offline tests.

    Returns:
        A concrete embedding provider.

    Raises:
        EmbeddingConfigurationError: If the provider name is unsupported.
    """
    cfg = config or settings
    provider_name = str(getattr(cfg, "EMBEDDING_PROVIDER", "gemini")).strip().lower()
    api_key = str(getattr(cfg, "EMBEDDING_API_KEY", "") or "")
    model = str(getattr(cfg, "EMBEDDING_MODEL_NAME", "") or "")
    dimensions = getattr(cfg, "EMBEDDING_DIMENSIONS", None)

    if provider_name == "openai":
        return OpenAIEmbeddingProvider(
            api_key=api_key,
            model=model or DEFAULT_OPENAI_EMBEDDING_MODEL,
            client=client,
        )
    if provider_name in {"gemini", "google"}:
        return GeminiEmbeddingProvider(
            api_key=api_key,
            model=model or DEFAULT_GEMINI_EMBEDDING_MODEL,
            client=client,
            output_dimensions=dimensions,
        )

    raise EmbeddingConfigurationError(
        f"Unsupported EMBEDDING_PROVIDER '{provider_name}'; expected 'openai' or 'gemini'"
    )


def get_embedding_provider(
    config: Any = None,
    client: Optional[httpx.Client] = None,
) -> EmbeddingProvider:
    """Return the configured embedding provider (factory alias for integration)."""
    return create_embedding_provider(config=config, client=client)


def generate_embedding(
    text: str,
    provider: Optional[EmbeddingProvider] = None,
    config: Any = None,
) -> list[float]:
    """Generate a single embedding vector for canonical incident text.

    Args:
        text: Non-empty text to embed.
        provider: Optional provider instance, primarily for offline tests.
        config: Optional settings-like object used when no provider is supplied.

    Returns:
        A validated list of floats.

    Raises:
        EmbeddingInputError: If ``text`` is not a non-empty string.
        EmbeddingError: If the provider is misconfigured or fails.
    """
    vectors = generate_embeddings_batch(
        [text], batch_size=1, provider=provider, config=config
    )
    return vectors[0]


def generate_embeddings_batch(
    texts: list[str],
    batch_size: int = DEFAULT_BATCH_SIZE,
    provider: Optional[EmbeddingProvider] = None,
    config: Any = None,
) -> list[list[float]]:
    """Generate embeddings for many texts in provider-safe batches.

    Args:
        texts: Non-empty text strings to embed.
        batch_size: Maximum number of texts sent per provider call.
        provider: Optional provider instance, primarily for offline tests.
        config: Optional settings-like object used when no provider is supplied.

    Returns:
        Validated vectors in the same order as ``texts``. Empty input returns ``[]``.

    Raises:
        EmbeddingInputError: If inputs or ``batch_size`` are invalid.
        EmbeddingError: If the provider is misconfigured or fails.
    """
    active_batch_size: Any = batch_size
    active_provider = provider
    if active_provider is None and hasattr(active_batch_size, "embed_texts"):
        active_provider = active_batch_size
        active_batch_size = DEFAULT_BATCH_SIZE

    normalized = _normalize_texts(texts)
    if not normalized:
        return []
    if (
        not isinstance(active_batch_size, int)
        or isinstance(active_batch_size, bool)
        or active_batch_size < 1
    ):
        raise EmbeddingInputError("batch_size must be a positive integer")

    active_provider = active_provider or get_embedding_provider(config=config)
    all_vectors: list[list[float]] = []

    for start in range(0, len(normalized), active_batch_size):
        chunk = normalized[start : start + active_batch_size]
        vectors = _validate_vectors(
            active_provider.embed_texts(chunk),
            expected_count=len(chunk),
        )
        all_vectors.extend(vectors)

    logger.debug(
        "Generated %s embeddings in %s batch(es)",
        len(all_vectors),
        math.ceil(len(normalized) / active_batch_size),
    )
    return all_vectors


def get_event_embedding_text(event: EventRecord) -> str:
    """Return the canonical embedding text for an incident event.

    Args:
        event: Canonical event record produced by ingestion.

    Returns:
        The event's non-empty ``embedding_text``.

    Raises:
        EmbeddingInputError: If the event has no canonical embedding text.
    """
    embedding_text = (event.embedding_text or "").strip()
    if not embedding_text:
        raise EmbeddingInputError(
            f"Event '{event.source_id}' has no canonical embedding_text"
        )
    return embedding_text


def generate_event_embedding(
    event: EventRecord,
    provider: Optional[EmbeddingProvider] = None,
    config: Any = None,
) -> list[float]:
    """Generate an embedding from an event's canonical text representation."""
    return generate_embedding(
        get_event_embedding_text(event), provider=provider, config=config
    )


def generate_event_embeddings(
    events: list[EventRecord],
    batch_size: int = DEFAULT_BATCH_SIZE,
    provider: Optional[EmbeddingProvider] = None,
    config: Any = None,
) -> list[list[float]]:
    """Generate embeddings for events using their canonical embedding text."""
    active_batch_size: Any = batch_size
    active_provider = provider
    if active_provider is None and hasattr(active_batch_size, "embed_texts"):
        active_provider = active_batch_size
        active_batch_size = DEFAULT_BATCH_SIZE

    texts = [get_event_embedding_text(event) for event in events]
    return generate_embeddings_batch(
        texts,
        batch_size=active_batch_size,
        provider=active_provider,
        config=config,
    )


# Module-contract aliases documented in AGENTS.md.
get_embedding = generate_embedding
get_embeddings_batch = generate_embeddings_batch
