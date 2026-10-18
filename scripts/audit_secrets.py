"""Best-effort tracked-file/history scan. Prints object/path only, never matched values."""

import argparse
import re
import subprocess

PATTERN = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s+[A-Za-z0-9+/=]{30,}|"
    rb"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})|"
    rb"AIza[0-9A-Za-z_-]{30,}|AKIA[0-9A-Z]{16}|"
    rb"(?:sk-proj-|sb_secret_)[A-Za-z0-9_-]{16,}"
)


def git(*args):
    return subprocess.check_output(["git", *args])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    findings, checked = [], 0
    paths = git("ls-files", "-z").decode().split("\0")
    from pathlib import Path

    for path in filter(None, paths):
        file = Path(path)
        if file.is_file() and file.stat().st_size <= 2_000_000:
            checked += 1
            if PATTERN.search(file.read_bytes()):
                findings.append({"path": path})
    if args.history:
        entries = git("rev-list", "--objects", "--all").decode().splitlines()
        batch = subprocess.Popen(
            ["git", "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE
        )
        try:
            for entry in entries:
                sha = entry.split(" ", 1)[0]
                batch.stdin.write((sha + "\n").encode())
                batch.stdin.flush()
                header = batch.stdout.readline().split()
                if len(header) != 3:
                    continue
                size = int(header[2])
                content = batch.stdout.read(size)
                batch.stdout.read(1)
                if header[1] == b"blob":
                    checked += 1
                    if PATTERN.search(content):
                        findings.append({"object": sha})
        finally:
            batch.stdin.close()
            batch.wait(timeout=10)
    import json

    print(json.dumps({"checked": checked, "findings": findings}))
    return bool(findings)


if __name__ == "__main__":
    raise SystemExit(main())
