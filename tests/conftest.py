import copy
import threading
from contextlib import contextmanager
from dataclasses import replace

import pytest

from devfolio.config import Settings
from devfolio.store import SyncBusy


@pytest.fixture
def settings():
    return Settings("portfolio-owner")


class FakeEmbeddings:
    def __init__(self):
        self.requests = self.failures = self.retries = 0
        self.fail = False

    def documents(self, texts):
        self.requests += len(texts)
        if self.fail:
            self.failures += 1
            raise RuntimeError("secret must never appear in report")
        return [[1.0] + [0.0] * 767 for _ in texts]


class FakeSource:
    def __init__(self):
        self.retries = self.skipped = 0
        self.repos = [
            {
                "id": 1,
                "name": "project-one",
                "url": "https://github.com/owner/project-one",
                "description": "Project",
                "language": "Python",
            }
        ]
        self.sha = "revision-one"
        self.content = {
            "README.md": b"# Project\nA Python portfolio application.",
            "docs/design.md": b"# Design\nPostgres architecture.",
        }
        self.blobs = {}
        self.reads = 0
        self.fail_discovery = False

    def discover(self):
        if self.fail_discovery:
            raise RuntimeError("discovery error")
        return self.repos

    def revision(self, repo):
        return self.sha

    def files(self, repo, sha):
        from devfolio.chunking import digest

        result = {}
        for path, text in self.content.items():
            blob = digest(text.decode())
            result[path] = blob
            self.blobs[blob] = text
        return result

    def read(self, repo, blob):
        self.reads += 1
        return self.blobs[blob]


class FakeStore:
    """State-machine test double. SQL semantics are covered separately on PostgreSQL."""

    def __init__(self, settings):
        self.settings = settings
        self.index = settings.index_id
        self.snapshots = {}
        self.vectors = set()
        self.active = None
        self.fail = False
        self.mutex = threading.Lock()
        self.reports = []

    @contextmanager
    def lock(self):
        if not self.mutex.acquire(False):
            raise SyncBusy()
        try:
            yield
        finally:
            self.mutex.release()

    def initialize(self):
        pass

    def begin_run(self, run_id):
        pass

    def finish_run(self, report):
        self.reports.append(report)

    def snapshot(self, repo_id):
        return copy.deepcopy(self.snapshots.get((self.index, repo_id), {"revision": None, "files": {}}))

    def cached(self, hashes):
        return {h for h in hashes if (self.index, h) in self.vectors}

    def cache(self, chunks, vectors):
        self.vectors.update((self.index, c["content_hash"]) for c in chunks)

    def publish(self, repo, sha, changes, deleted):
        if self.fail:
            raise RuntimeError("db failed with secret")
        previous = self.snapshot(repo["id"])
        for path in deleted:
            previous["files"].pop(path, None)
        previous["files"].update(copy.deepcopy(changes))
        previous["revision"] = sha
        self.snapshots[(self.index, repo["id"])] = previous

    def finalize(self, eligible_ids, activate=False, allow_empty=False):
        if not eligible_ids and not allow_empty:
            raise ValueError("empty")
        removed = [key for key in self.snapshots if key[0] == self.index and key[1] not in eligible_ids]
        for key in removed:
            del self.snapshots[key]
        if self.active is None or activate:
            self.active = self.index
        return len(removed)

    def new_profile(self):
        self.settings = replace(self.settings, version="next-model-version")
        self.index = self.settings.index_id
        return self.settings


@pytest.fixture
def pipeline(settings):
    return FakeSource(), FakeStore(settings), FakeEmbeddings(), settings
