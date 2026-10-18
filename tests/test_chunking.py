import pytest

from devfolio.chunking import allowed_path, chunk_document, normalize
from devfolio.embeddings import validate_vector


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        "docs/.env.md",
        "docs/private_key.md",
        "docs/secrets.md",
        "node_modules/README.md",
        "dist/README.md",
        "docs/image.png",
        "src/main.py",
        "../README.md",
        "docs/../README.md",
        "/README.md",
        "docs\\README.md",
        "docs/.git/config.md",
    ],
)
def test_unsafe_files_excluded(path):
    assert not allowed_path(path)


@pytest.mark.parametrize(
    "path", ["README.md", "readme.markdown", "README.txt", "docs/design.md", "docs/guides/setup.txt"]
)
def test_allowlist(path):
    assert allowed_path(path)


def test_chunk_limits_heading_context_and_stability(settings):
    repo = {"id": 5, "name": "project", "url": "https://github.com/a/b"}
    text = "# Project\n## Design\n" + "architecture and decisions\n" * 300
    chunks = chunk_document(repo, "README.md", text, "sha", settings)
    assert len(chunks) > 3
    assert all(0 < len(c["content"]) <= settings.chunk_size for c in chunks)
    assert "# Project" in chunks[1]["content"]
    assert chunks == chunk_document(repo, "README.md", text, "sha", settings)
    assert len({c["id"] for c in chunks}) == len(chunks)


def test_binary_invalid_utf8_size_and_secrets():
    for raw in [b"\x00", b"\xff", b"a" * 1001, b"-----BEGIN RSA PRIVATE KEY-----", b"ghp_" + b"x" * 30]:
        with pytest.raises((ValueError, UnicodeError)):
            normalize(raw, 1000)
    assert normalize(b"# Header\r\nText  \r\n", 100) == "# Header\nText"


def test_dimension_validation():
    for vector in [[0.0] * 768, [1.0], [float("nan")] * 768, [float("inf")] * 768]:
        with pytest.raises(ValueError):
            validate_vector(vector, 768)
    vector = validate_vector([2.0] + [0.0] * 767, 768)
    assert vector[0] == 1.0


def test_database_examples_redacted_but_unknown_passwords_rejected():
    for password in ["password", "[YOUR-PASSWORD]", "[YOUR_PASSWORD]"]:
        raw = f"Setup: postgresql://example:{password}@localhost:5432/app".encode()
        text = normalize(raw, 1000)
        assert text == "Setup: postgresql://[credentials omitted]@localhost:5432/app"
        assert "example:" not in text
    with pytest.raises(ValueError, match="Potential credential"):
        normalize(b"postgresql://app:unrecognized-value@database.example/app", 1000)
    with pytest.raises(ValueError, match="Potential credential"):
        normalize(b"postgresql://app:password@localhost/app\nghp_" + b"x" * 30, 1000)


def test_fenced_headings_and_multilingual_byte_limits(settings):
    from dataclasses import replace

    repo = {"id": 1, "name": "one", "url": "https://github.com/a/b"}
    text = "# Project\n```sh\n# shell comment\necho hi\n```\n"
    chunks = chunk_document(repo, "README.md", text, "sha", settings)
    assert len(chunks) == 1 and "# shell comment" in chunks[0]["content"]
    settings = replace(settings, model="gemini-embedding-001")
    chunks = chunk_document(repo, "README.md", "# Unicode\n" + "漢字🙂" * 2000, "sha", settings)
    assert len(chunks) > 5
    assert all(len(c["content"].encode()) <= 1800 for c in chunks)
