import hashlib
import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    username: str
    topic: str = "portfolio"
    model: str = "gemini-embedding-2"
    version: str = "2026-04"
    dimensions: int = 768
    chunk_size: int = 1800
    overlap: int = 180
    max_file_bytes: int = 262144
    max_files: int = 100
    top_k: int = 4
    min_score: float = 0.5
    context_chars: int = 8000

    def __post_init__(self):
        import re

        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", self.username):
            raise ValueError("GITHUB_USERNAME must be a GitHub account name")
        if not re.fullmatch(r"[a-z0-9-]{1,50}", self.topic):
            raise ValueError("PORTFOLIO_TOPIC is invalid")
        if self.model not in {"gemini-embedding-2", "gemini-embedding-001"}:
            raise ValueError("Unsupported EMBEDDING_MODEL: implement and version its input format first")
        if self.dimensions not in {768, 1536, 3072}:
            raise ValueError("EMBEDDING_DIMENSIONS must be 768, 1536 or 3072")
        if (
            not self.version
            or not 400 <= self.chunk_size <= 2400
            or not 0 <= self.overlap < self.chunk_size // 2
        ):
            raise ValueError("Invalid embedding version or chunk limits")
        if (
            not 1 <= self.top_k <= 10
            or not -1 <= self.min_score <= 1
            or not 1000 <= self.context_chars <= 20000
        ):
            raise ValueError("Invalid retrieval limits")

    @classmethod
    def from_env(cls):
        return cls(
            username=os.getenv("GITHUB_USERNAME", ""),
            topic=os.getenv("PORTFOLIO_TOPIC", "portfolio"),
            model=os.getenv("EMBEDDING_MODEL", "gemini-embedding-2").removeprefix("models/"),
            version=os.getenv("EMBEDDING_VERSION", "2026-04"),
            dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", "768")),
            top_k=int(os.getenv("RETRIEVAL_TOP_K", "4")),
            min_score=float(os.getenv("RETRIEVAL_MIN_SCORE", "0.5")),
        )

    @property
    def profile(self):
        return {
            "model": self.model,
            "version": self.version,
            "dimensions": self.dimensions,
            "chunk_size": self.chunk_size,
            "overlap": self.overlap,
            "preprocessing": "markdown-v1-retrieval-prefix-v1",
        }

    @property
    def index_id(self):
        return hashlib.sha256(json.dumps(self.profile, sort_keys=True).encode()).hexdigest()

    @property
    def scope(self):
        return f"{self.username.lower()}:{self.topic}"


def required(name):
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} is required; see .env.example")
    return value


def database_url(name):
    from urllib.parse import parse_qs, urlsplit

    value = required(name)
    parsed = urlsplit(value)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError(f"{name} must be a PostgreSQL URL")
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"} and parse_qs(parsed.query).get(
        "sslmode", [""]
    )[0] not in {"require", "verify-ca", "verify-full"}:
        raise ValueError(f"{name} must require TLS (sslmode=require or verify-full)")
    return value
