import hashlib
import re
import unicodedata
from pathlib import PurePosixPath


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def allowed_path(path):
    parts = PurePosixPath(path).parts
    if not parts or path.startswith("/") or "\\" in path:
        return False
    lowered = [p.lower() for p in parts]
    if any(
        p.startswith(".") or p in {"..", "node_modules", "vendor", "build", "dist", "generated", "coverage"}
        for p in lowered
    ):
        return False
    if any(re.search(r"secret|credential|token|password|private[-_]?key", p) for p in lowered):
        return False
    if len(parts) == 1:
        return lowered[0] in {"readme.md", "readme.markdown", "readme.txt"}
    return lowered[0] == "docs" and PurePosixPath(path).suffix.lower() in {".md", ".markdown", ".txt"}


SECRET = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})|"
    r"AIza[0-9A-Za-z_-]{30,}|AKIA[0-9A-Z]{16}|"
    r"(?:sk-proj-|sb_secret_)[A-Za-z0-9_-]{16,}|"
    r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|"
    r"(?:postgres(?:ql)?://)[^\s:]+:[^\s@]+@"
)


def normalize(raw, max_bytes):
    if len(raw) > max_bytes or b"\x00" in raw:
        raise ValueError("Unsupported document size or binary content")
    text = unicodedata.normalize("NFC", raw.decode("utf-8-sig")).replace("\r\n", "\n").replace("\r", "\n")
    if SECRET.search(text):
        raise ValueError("Potential credential detected; document rejected")
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def chunk_document(repo, path, text, sha, settings):
    """Heading-aware bounded windows; content IDs survive unrelated section edits."""
    sections, lines, fence = [], [], None
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            value = marker.group(1)
            if fence is None:
                fence = value
            elif value[0] == fence[0] and len(value) >= len(fence):
                fence = None
        if fence is None and not marker and re.match(r"^#{1,6} ", line) and lines:
            sections.append("".join(lines))
            lines = []
        lines.append(line)
    if lines:
        sections.append("".join(lines))
    chunks, occurrences, headings = [], {}, []
    for section in sections:
        if not section.strip():
            continue
        first = section.splitlines()[0]
        if first.startswith("#"):
            depth = len(first) - len(first.lstrip("#"))
            headings = [(d, h) for d, h in headings if d < depth] + [(depth, first)]
        prefix = "\n".join(h for _, h in headings[:-1])
        # Reserve room for bounded heading context. All content remains bounded.
        prefix = prefix[-200:]
        start = 0
        while start < len(section):
            if start:
                prefix = "\n".join(h for _, h in headings)[-200:]
            width = settings.chunk_size - len(prefix) - 1
            end = min(start + width, len(section))
            # A conservative UTF-8 byte ceiling also bounds multilingual token
            # inputs below the models' documented 2048 / 8192 token limits.
            byte_limit = (1800 if settings.model.endswith("001") else 7200) - len(prefix.encode()) - 1
            segment = section[start:end].encode()
            if len(segment) > byte_limit:
                end = start + len(segment[:byte_limit].decode("utf-8", errors="ignore"))
            if end < len(section):
                boundary = section.rfind("\n", start + (end - start) // 2, end)
                if boundary > start:
                    end = boundary
            content = ((prefix + "\n") if prefix else "") + section[start:end].strip()
            content = content.strip()
            if content:
                content_hash = digest(content)
                occurrence = occurrences.get(content_hash, 0)
                occurrences[content_hash] = occurrence + 1
                chunks.append(
                    {
                        "id": digest(f"{repo['id']}:{path}:{content_hash}:{occurrence}"),
                        "content": content,
                        "content_hash": content_hash,
                        "chunk_index": len(chunks),
                        "path": path,
                        "commit_sha": sha,
                        "name": repo["name"],
                        "url": repo["url"],
                        "model_version": settings.version,
                    }
                )
            if end == len(section):
                break
            start = max(start + 1, end - settings.overlap)
    return chunks
