import logging
import math
import time

from devfolio.retry import retry

log = logging.getLogger(__name__)


def validate_vector(values, dimensions):
    if len(values) != dimensions or not all(math.isfinite(v) for v in values):
        raise ValueError("Embedding dimension or values do not match index profile")
    norm = math.sqrt(sum(v * v for v in values))
    if not norm:
        raise ValueError("Zero embedding vector")
    return [v / norm for v in values]


class GoogleEmbeddings:
    def __init__(self, settings, api_key, client=None):
        from google import genai
        from google.genai import types

        self.settings = settings
        self.client = client or genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=20000, retry_options=types.HttpRetryOptions(attempts=1)),
        )
        self.requests = 0
        self.failures = 0
        self.retries = 0

    def _retry(self):
        self.retries += 1

    def _embed(self, text, query=False):
        from google.genai import types

        config = {"output_dimensionality": self.settings.dimensions}
        if self.settings.model == "gemini-embedding-2":
            text = f"task: search result | query: {text}" if query else f"title: none | text: {text}"
        else:
            config["task_type"] = "RETRIEVAL_QUERY" if query else "RETRIEVAL_DOCUMENT"

        def call():
            self.requests += 1
            try:
                result = self.client.models.embed_content(
                    model=self.settings.model, contents=text, config=types.EmbedContentConfig(**config)
                )
                if not result.embeddings or len(result.embeddings) != 1:
                    raise ValueError("Expected exactly one embedding")
                return validate_vector(result.embeddings[0].values, self.settings.dimensions)
            except Exception:
                self.failures += 1
                raise

        return retry(call, self._retry)

    def documents(self, texts):
        # Embedding 2 aggregates list inputs; request one vector per chunk explicitly.
        return [self._embed(text) for text in texts]

    def query(self, text):
        start = time.monotonic()
        try:
            return self._embed(text, query=True)
        finally:
            log.info("query_embedding", extra={"duration_ms": round((time.monotonic() - start) * 1000)})

    def close(self):
        self.client.close()
