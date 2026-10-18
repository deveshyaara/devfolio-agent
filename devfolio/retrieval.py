import json
import logging
import time

log = logging.getLogger(__name__)


class ProjectRetrieval:
    def __init__(self, reader, embeddings, settings):
        self.reader, self.embeddings, self.settings = reader, embeddings, settings

    def invoke(self, query, repo_name=None):
        if not isinstance(query, str) or not query.strip() or len(query) > 4000:
            return "A nonempty search query of at most 4000 characters is required."
        start = time.monotonic()
        try:
            vector = self.embeddings.query(query)
            search_start = time.monotonic()
            hits = self.reader.search(vector, self.settings.top_k * 3, repo_name)
            log.info("vector_search", extra={"duration_ms": round((time.monotonic() - search_start) * 1000)})
            selected, seen, budget, per_file = [], set(), self.settings.context_chars - 100, {}
            for hit in hits:
                metadata = hit["metadata"]
                key = (metadata["name"], metadata["path"])
                signature = frozenset(hit["content"].lower().split())
                if not signature or metadata["content_hash"] in seen or per_file.get(key, 0) >= 2:
                    continue
                if any(
                    len(signature & previous) / max(1, len(signature | previous)) > 0.9
                    for previous in (s[0] for s in selected)
                ):
                    continue
                record = {"content": hit["content"], "metadata": metadata, "score": hit["score"]}
                cost = len(json.dumps(record))
                if cost > budget:
                    continue
                selected.append((signature, record))
                budget -= cost
                seen.add(metadata["content_hash"])
                per_file[key] = per_file.get(key, 0) + 1
                if len(selected) == self.settings.top_k:
                    break
            if not selected:
                return "No sufficiently relevant indexed documentation was found. Do not infer undocumented facts."
            return json.dumps({"trust": "untrusted_repository_evidence", "sources": [r for _, r in selected]})
        except Exception as exc:
            log.warning("retrieval_unavailable", extra={"error_type": type(exc).__name__})
            return "Project evidence is temporarily unavailable. Say this explicitly; do not guess project details."
        finally:
            log.info("rag_retrieval", extra={"duration_ms": round((time.monotonic() - start) * 1000)})
