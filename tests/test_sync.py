import json

import pytest

from devfolio.store import SyncBusy
from devfolio.sync import synchronize


def test_initial_and_unchanged_sync(pipeline):
    source, store, embed, settings = pipeline
    first = synchronize(*pipeline)
    assert first["status"] == "success"
    assert first["files_added"] == 2 and embed.requests == 2
    assert store.active == settings.index_id
    before = embed.requests
    second = synchronize(*pipeline)
    assert second["status"] == "success" and second["files_unchanged"] == 2
    assert second["embedding_requests"] == 0
    assert embed.requests == before and source.reads == 2
    assert len(store.snapshot(1)["files"]) == 2


def test_only_changed_chunks_are_embedded(pipeline):
    source, store, embed, settings = pipeline
    source.content["README.md"] = b"# Introduction\nOriginal text.\n# Architecture\nPostgres and Python."
    synchronize(*pipeline)
    original = store.snapshot(1)
    source.content["README.md"] = b"# Introduction\nChanged text.\n# Architecture\nPostgres and Python."
    source.sha = "revision-two"
    previous = embed.requests
    report = synchronize(*pipeline)
    assert embed.requests - previous == 1
    assert report["files_changed"] == 1 and report["files_unchanged"] == 1
    assert report["chunks_reused"] == 2
    assert original["files"]["docs/design.md"] == store.snapshot(1)["files"]["docs/design.md"]


def test_add_delete_files_and_no_duplicates(pipeline):
    source, store, embed, settings = pipeline
    synchronize(*pipeline)
    del source.content["docs/design.md"]
    source.content["docs/new.md"] = b"# New\nA new document."
    source.sha = "revision-two"
    report = synchronize(*pipeline)
    assert report["files_added"] == report["files_deleted"] == 1
    assert "docs/design.md" not in store.snapshot(1)["files"]
    synchronize(*pipeline)
    all_ids = [c["id"] for f in store.snapshot(1)["files"].values() for c in f["chunks"]]
    assert len(all_ids) == len(set(all_ids))


def test_removed_repository_empty_guard(pipeline):
    source, store, embed, settings = pipeline
    synchronize(*pipeline)
    source.repos = []
    assert synchronize(*pipeline)["status"] == "failed"
    assert store.snapshot(1)["revision"]
    assert synchronize(*pipeline, allow_empty=True)["repositories_removed"] == 1


def test_removed_repository_in_nonempty_discovery(pipeline):
    source, store, embed, settings = pipeline
    source.repos.append({**source.repos[0], "id": 2, "name": "two"})
    synchronize(*pipeline)
    source.repos = source.repos[1:]
    assert synchronize(*pipeline)["repositories_removed"] == 1
    assert store.snapshot(1)["revision"] is None


@pytest.mark.parametrize("failure", ["embedding", "database", "discovery"])
def test_failures_preserve_checkpoint_and_retry(pipeline, failure):
    source, store, embed, settings = pipeline
    synchronize(*pipeline)
    original = store.snapshot(1)
    source.sha = "revision-two"
    source.content["README.md"] = b"# Updated\nNew content."
    embed.fail = failure == "embedding"
    store.fail = failure == "database"
    source.fail_discovery = failure == "discovery"
    report = synchronize(*pipeline)
    assert report["status"] == "failed"
    assert "secret" not in json.dumps(report)
    assert store.snapshot(1) == original
    before = embed.requests
    embed.fail = store.fail = source.fail_discovery = False
    assert synchronize(*pipeline)["status"] == "success"
    if failure == "database":
        assert embed.requests == before  # Durable vector cache survives failed publication.


def test_failed_repo_blocks_pruning_and_initial_activation(pipeline):
    source, store, embed, settings = pipeline
    embed.fail = True
    assert synchronize(*pipeline)["status"] == "failed"
    assert store.active is None


def test_concurrent_sync_rejected(pipeline):
    source, store, embed, settings = pipeline
    with store.lock():
        with pytest.raises(SyncBusy):
            synchronize(*pipeline)
    assert synchronize(*pipeline)["status"] == "success"


def test_new_model_profile_requires_complete_explicit_activation(pipeline):
    source, store, embed, settings = pipeline
    synchronize(*pipeline)
    original_index = store.active
    new_settings = store.new_profile()
    before = embed.requests
    synchronize(source, store, embed, new_settings)
    assert embed.requests == before + 2 and store.active == original_index
    synchronize(source, store, embed, new_settings, activate=True)
    assert store.active == new_settings.index_id


def test_duplicate_chunk_content_embeds_once(pipeline):
    source, store, embed, settings = pipeline
    source.content = {"README.md": b"# Same\nContent.\n# Same\nContent."}
    synchronize(*pipeline)
    assert embed.requests == 1
    assert len(store.snapshot(1)["files"]["README.md"]["chunks"]) == 2


def test_secret_document_does_not_replace_good_snapshot(pipeline):
    source, store, embed, settings = pipeline
    synchronize(*pipeline)
    original = store.snapshot(1)
    source.sha = "bad-revision"
    source.content["README.md"] = b"-----BEGIN PRIVATE KEY-----"
    report = synchronize(*pipeline)
    assert report["status"] == "failed" and store.snapshot(1) == original
