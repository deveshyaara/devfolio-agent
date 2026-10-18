import base64

import requests

from devfolio.chunking import allowed_path
from devfolio.retry import retry


class GitHubSource:
    """Public, immutable commit snapshots; never clones or executes repository code."""

    def __init__(self, settings, token=None, session=None):
        self.settings = settings
        self.session = session or requests.Session()
        self.session.headers.update(
            {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        )
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        self.retries = 0
        self.skipped = 0

    def _retry(self):
        self.retries += 1

    def _get(self, path, params=None):
        def call():
            response = self.session.get(f"https://api.github.com{path}", params=params, timeout=(5, 30))
            # GitHub uses 403 for rate exhaustion as well as permanent permission failures.
            if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
                response.status_code = 429
            response.raise_for_status()
            return response.json()

        return retry(call, self._retry)

    def discover(self):
        repos = []
        for page in range(1, 101):
            items = self._get(
                f"/users/{self.settings.username}/repos", {"per_page": 100, "page": page, "type": "owner"}
            )
            for item in items:
                if self.settings.topic in item.get("topics", []) and not item.get("private", True):
                    repos.append(
                        {
                            "id": item["id"],
                            "name": item["name"],
                            "full_name": item["full_name"],
                            "url": item["html_url"],
                            "description": item.get("description"),
                            "language": item.get("language"),
                            "default_branch": item["default_branch"],
                        }
                    )
            if len(items) < 100:
                return repos
        raise RuntimeError("Discovery limit reached; deletion is unsafe")

    def revision(self, repo):
        from urllib.parse import quote

        commit = self._get(f"/repos/{repo['full_name']}/commits/{quote(repo['default_branch'], safe='')}")
        return commit["sha"]

    def files(self, repo, sha):
        tree = self._get(f"/repos/{repo['full_name']}/git/trees/{sha}", {"recursive": "1"})
        if tree.get("truncated"):
            raise RuntimeError("Truncated Git tree; refusing partial snapshot")
        files = {}
        for entry in tree["tree"]:
            if entry["type"] != "blob" or not allowed_path(entry["path"]):
                continue
            if entry.get("mode") != "100644" and entry.get("mode") != "100755":
                self.skipped += 1
                continue
            if entry.get("size", 0) > self.settings.max_file_bytes:
                raise ValueError("Allowed document exceeds size limit; last snapshot retained")
            files[entry["path"]] = entry["sha"]
        if len(files) > self.settings.max_files:
            raise ValueError("Documentation file limit exceeded; last snapshot retained")
        return files

    def read(self, repo, blob_sha):
        blob = self._get(f"/repos/{repo['full_name']}/git/blobs/{blob_sha}")
        if blob.get("encoding") != "base64" or blob.get("size", 0) > self.settings.max_file_bytes:
            raise ValueError("Unsupported blob")
        return base64.b64decode(blob["content"], validate=False)

    def close(self):
        self.session.close()
