import json
from types import SimpleNamespace

import pytest

from devfolio.embeddings import GoogleEmbeddings
from devfolio.retrieval import ProjectRetrieval


class Reader:
    def __init__(self, hits):
        self.hits = hits

    def search(self, vector, limit, repo_name):
        assert len(vector) == 768
        self.request = (limit, repo_name)
        return self.hits


class Embeddings:
    def query(self, query):
        return [1.0] + [0.0] * 767


def hit(name="project-one", path="README.md", index=0, content="Python Postgres architecture"):
    return {
        "content": content,
        "metadata": {
            "name": name,
            "url": "https://github.com/a/b",
            "path": path,
            "content_hash": str(index),
            "chunk_id": str(index),
        },
        "score": 0.8,
    }


def test_retrieval_sources_bounded_and_deduplicated(settings):
    hits = [
        hit(index=0),
        hit(index=1),
        hit(index=2, content="Python framework"),
        hit(index=3, content="Another section"),
        hit(name="project-two", index=4, content="Distinct project"),
    ]
    reader = Reader(hits)
    result = json.loads(
        ProjectRetrieval(reader, Embeddings(), settings).invoke("Python architecture", "project-one")
    )
    assert result["sources"][0]["metadata"]["name"] == "project-one"
    assert result["sources"][0]["metadata"]["path"] == "README.md"
    assert len(result["sources"]) <= settings.top_k
    assert len(result["sources"]) == 3
    assert reader.request == (12, "project-one")


def test_empty_or_unavailable_evidence(settings):
    retrieval = ProjectRetrieval(Reader([]), Embeddings(), settings)
    assert "Do not infer" in retrieval.invoke("unknown")

    def broken(*args):
        raise RuntimeError("postgres://secret-password")

    retrieval.reader.search = broken
    result = retrieval.invoke("unknown")
    assert "unavailable" in result and "password" not in result
    assert "required" in retrieval.invoke("")


@pytest.mark.parametrize("model", ["gemini-embedding-2", "gemini-embedding-001"])
def test_google_adapter_dimension_and_task_format(settings, model):
    from dataclasses import replace

    settings = replace(settings, model=model)
    calls = []

    def embed_content(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[1.0] + [0.0] * 767)])

    client = SimpleNamespace(models=SimpleNamespace(embed_content=embed_content))
    adapter = GoogleEmbeddings(settings, "unused", client)
    adapter.documents(["one", "two"])
    adapter.query("query")
    assert len(calls) == 3 and adapter.requests == 3
    assert calls[0]["config"].output_dimensionality == 768
    if model.endswith("-2"):
        assert calls[0]["contents"] == "title: none | text: one"
        assert calls[-1]["contents"] == "task: search result | query: query"
        assert calls[-1]["config"].task_type is None
    else:
        assert calls[0]["config"].task_type == "RETRIEVAL_DOCUMENT"
        assert calls[-1]["config"].task_type == "RETRIEVAL_QUERY"


def test_google_adapter_rejects_bad_response(settings):
    client = SimpleNamespace(
        models=SimpleNamespace(
            embed_content=lambda **kw: SimpleNamespace(embeddings=[SimpleNamespace(values=[1.0])])
        )
    )
    with pytest.raises(ValueError):
        GoogleEmbeddings(settings, "unused", client).query("query")
