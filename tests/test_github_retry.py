from types import SimpleNamespace

import pytest
import requests

from devfolio.github import GitHubSource
from devfolio.retry import retry


class Response:
    def __init__(self, body, status=200, headers=None):
        self.body, self.status_code, self.headers = body, status, headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        return self.body


def test_complete_discovery_public_topics_and_pagination(settings):
    repo = {
        "id": 1,
        "name": "one",
        "full_name": "owner/one",
        "html_url": "https://github.com/owner/one",
        "topics": [settings.topic],
        "private": False,
        "default_branch": "main",
    }
    pages = [
        Response([{**repo, "id": i} for i in range(100)]),
        Response(
            [{**repo, "id": 101}, {**repo, "id": 102, "private": True}, {**repo, "id": 103, "topics": []}]
        ),
    ]
    calls = []

    def get(url, **kwargs):
        calls.append(kwargs)
        return pages.pop(0)

    source = GitHubSource(settings, session=SimpleNamespace(headers={}, get=get))
    assert len(source.discover()) == 101
    assert calls[-1]["params"]["page"] == 2 and calls[0]["timeout"] == (5, 30)


def test_truncated_tree_is_never_a_complete_snapshot(settings):
    source = GitHubSource(
        settings, session=SimpleNamespace(headers={}, get=lambda *a, **kw: Response({"truncated": True}))
    )
    with pytest.raises(RuntimeError):
        source.files({"full_name": "owner/repo"}, "sha")


def test_tree_excludes_sensitive_and_binary_paths(settings):
    entries = [
        {"type": "blob", "path": path, "mode": "100644", "sha": "sha", "size": 10}
        for path in ["README.md", ".env", "docs/secret.md", "src/file.py", "docs/design.md"]
    ]
    entries.append({"type": "blob", "path": "docs/symlink.md", "mode": "120000", "sha": "x"})
    source = GitHubSource(
        settings, session=SimpleNamespace(headers={}, get=lambda *a, **kw: Response({"tree": entries}))
    )
    assert set(source.files({"full_name": "owner/repo"}, "sha")) == {"README.md", "docs/design.md"}
    assert source.skipped == 1


def test_retry_is_bounded_and_permanent_errors_are_not_retried():
    calls, sleeps, retries = [], [], []

    def transient():
        calls.append(1)
        raise requests.HTTPError(response=Response({}, 429))

    with pytest.raises(requests.HTTPError):
        retry(transient, lambda: retries.append(1), sleep=sleeps.append)
    assert len(calls) == 4 and len(sleeps) == len(retries) == 3
    assert 0.5 <= sleeps[0] < sleeps[1] < sleeps[2] <= 2.25

    def permanent():
        calls.append(1)
        raise requests.HTTPError(response=Response({}, 401))

    calls.clear()
    with pytest.raises(requests.HTTPError):
        retry(permanent, sleep=sleeps.append)
    assert len(calls) == 1
