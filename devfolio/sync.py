"""Run explicitly: python -m devfolio.sync [--activate-index] [--allow-empty]."""

import argparse
import json
import os
import time
import uuid
from datetime import datetime, timezone

from devfolio.chunking import chunk_document, digest, normalize
from devfolio.config import Settings, database_url, required
from devfolio.embeddings import GoogleEmbeddings
from devfolio.github import GitHubSource
from devfolio.store import PostgresStore


def now():
    return datetime.now(timezone.utc).isoformat()


def synchronize(source, store, embeddings, settings, activate=False, allow_empty=False):
    report = {
        "run_id": str(uuid.uuid4()),
        "started_at": now(),
        "status": "running",
        "repositories": 0,
        "files_added": 0,
        "files_changed": 0,
        "files_deleted": 0,
        "files_unchanged": 0,
        "chunks_added": 0,
        "chunks_changed": 0,
        "chunks_removed": 0,
        "chunks_reused": 0,
        "repositories_removed": 0,
        "errors": [],
        "revisions": {},
        "index_id": settings.index_id,
    }
    start = time.monotonic()
    baseline = (embeddings.requests, embeddings.failures, embeddings.retries + source.retries, source.skipped)
    with store.lock():
        store.initialize()
        store.begin_run(report["run_id"])
        try:
            repos = source.discover()  # Must finish before any deletion decision.
            report["repositories"] = len(repos)
            for repo in repos:
                phase = "snapshot"
                old = None
                try:
                    old = store.snapshot(repo["id"])
                    phase = "revision"
                    sha = source.revision(repo)
                    changes, counts = (
                        {},
                        {k: 0 for k in report if k.startswith("files_") or k.startswith("chunks_")},
                    )
                    if old["revision"] == sha:
                        counts["files_unchanged"] = len(old["files"])
                        counts["chunks_reused"] = sum(len(f["chunks"]) for f in old["files"].values())
                        deleted = []
                    else:
                        phase = "tree"
                        files = source.files(repo, sha)
                        deleted = sorted(set(old["files"]) - set(files))
                        counts["files_deleted"] = len(deleted)
                        counts["chunks_removed"] = sum(len(old["files"][p]["chunks"]) for p in deleted)
                        for path, blob_sha in files.items():
                            previous = old["files"].get(path)
                            if previous and previous["blob_sha"] == blob_sha:
                                counts["files_unchanged"] += 1
                                counts["chunks_reused"] += len(previous["chunks"])
                                continue
                            phase = "read_document"
                            text = normalize(source.read(repo, blob_sha), settings.max_file_bytes)
                            chunks = chunk_document(repo, path, text, sha, settings)
                            missing = {c["content_hash"]: c for c in chunks}
                            cached = store.cached(missing)
                            fresh = [c for h, c in missing.items() if h not in cached]
                            # Embedding 2 requires one request per vector. Persist each
                            # success immediately so a later failure can resume cheaply.
                            for chunk in fresh:
                                phase = "embedding"
                                vectors = embeddings.documents([chunk["content"]])
                                phase = "cache"
                                store.cache([chunk], vectors)
                            counts["chunks_reused"] += sum(c["content_hash"] in cached for c in chunks)
                            old_ids = {c["id"] for c in previous["chunks"]} if previous else set()
                            new_ids = {c["id"] for c in chunks}
                            counts["chunks_removed"] += len(old_ids - new_ids)
                            counts["chunks_changed" if previous else "chunks_added"] += len(new_ids - old_ids)
                            counts["files_changed" if previous else "files_added"] += 1
                            changes[path] = {
                                "blob_sha": blob_sha,
                                "content_hash": digest(text),
                                "chunks": chunks,
                            }
                    # Each repository's files and successful revision commit together.
                    phase = "publish"
                    store.publish(repo, sha, changes, deleted)
                    for key, value in counts.items():
                        report[key] += value
                    report["revisions"][str(repo["id"])] = sha
                except Exception as exc:
                    # No external exception strings: they can contain URLs/credentials.
                    report["errors"].append(
                        {
                            "repository_id": repo["id"],
                            "error_type": type(exc).__name__,
                            "stage": phase,
                            "last_successful_revision": old["revision"] if old else None,
                        }
                    )
            if not report["errors"]:
                report["repositories_removed"] = store.finalize(
                    [r["id"] for r in repos], activate, allow_empty
                )
        except Exception as exc:
            report["errors"].append({"error_type": type(exc).__name__, "stage": "discovery_or_finalize"})
        report.update(
            {
                "ended_at": now(),
                "duration_seconds": round(time.monotonic() - start, 3),
                "status": "failed" if report["errors"] else "success",
                "embedding_requests": embeddings.requests - baseline[0],
                "embedding_failures": embeddings.failures - baseline[1],
                "api_retries": embeddings.retries + source.retries - baseline[2],
                "skipped_files": source.skipped - baseline[3],
            }
        )
        store.finish_run(report)
    return report


def main():
    import psycopg
    from dotenv import load_dotenv
    from psycopg.rows import dict_row

    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--activate-index", action="store_true", help="Activate a completely built model/index profile"
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Permit confirmed empty discovery to delete the scope's repositories",
    )
    parser.add_argument("--report", default="sync-report.json")
    args = parser.parse_args()
    source = embeddings = None
    try:
        settings = Settings.from_env()
        source = GitHubSource(settings, os.getenv("GITHUB_TOKEN"))
        embeddings = GoogleEmbeddings(settings, required("GOOGLE_API_KEY"))
        with psycopg.connect(
            database_url("SUPABASE_SYNC_DB_URL"),
            autocommit=True,
            row_factory=dict_row,
            connect_timeout=10,
            options="-c statement_timeout=30000 -c lock_timeout=5000",
        ) as conn:
            report = synchronize(
                source,
                PostgresStore(conn, settings),
                embeddings,
                settings,
                args.activate_index,
                args.allow_empty,
            )
        with open(args.report, "w", encoding="utf-8") as output:
            json.dump(report, output, indent=2)
        print(json.dumps(report))
        return 0 if report["status"] == "success" else 1
    except Exception as exc:
        report = {
            "status": "failed",
            "error_type": type(exc).__name__,
            "stage": "configuration_or_database_or_lock",
        }
        with open(args.report, "w", encoding="utf-8") as output:
            json.dump(report, output, indent=2)
        print(json.dumps(report))
        return 1
    finally:
        if source:
            source.close()
        if embeddings:
            embeddings.close()


if __name__ == "__main__":
    raise SystemExit(main())
