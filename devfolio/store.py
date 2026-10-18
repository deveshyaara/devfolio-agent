from contextlib import contextmanager


class SyncBusy(RuntimeError):
    pass


def vector_literal(vector):
    # Only validated finite floats reach this adapter; still passed as an SQL parameter.
    return "[" + ",".join(str(float(v)) for v in vector) + "]"


class PostgresStore:
    def __init__(self, connection, settings):
        self.conn = connection
        self.settings = settings
        self.scope = settings.scope
        self.index = settings.index_id

    @contextmanager
    def lock(self):
        # A dedicated session (not a transaction-mode pooler) holds this until cleanup.
        locked = self.conn.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS locked", ("devfolio:" + self.scope,)
        ).fetchone()["locked"]
        if not locked:
            raise SyncBusy("Another synchronization owns this scope")
        try:
            yield
        finally:
            if not self.conn.closed:
                self.conn.execute(
                    "SELECT pg_advisory_unlock(hashtextextended(%s,0))", ("devfolio:" + self.scope,)
                )

    def initialize(self):
        from psycopg.types.json import Jsonb

        with self.conn.transaction():
            self.conn.execute(
                "INSERT INTO devfolio.indexes(id,profile,dimensions) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                (self.index, Jsonb(self.settings.profile), self.settings.dimensions),
            )
            self.conn.execute(
                "INSERT INTO devfolio.scopes(id) VALUES (%s) ON CONFLICT DO NOTHING", (self.scope,)
            )
            # A killed writer may leave a running record; lock acquisition proves it exited.
            self.conn.execute(
                "UPDATE devfolio.sync_runs SET status='failed',ended_at=now(),report=report || '{\"error\":\"interrupted_writer\"}'::jsonb WHERE scope=%s AND status='running'",
                (self.scope,),
            )

    def begin_run(self, run_id):
        self.conn.execute(
            "INSERT INTO devfolio.sync_runs(id,scope,index_id,status) VALUES (%s,%s,%s,'running')",
            (run_id, self.scope, self.index),
        )

    def finish_run(self, report):
        from psycopg.types.json import Jsonb

        self.conn.execute(
            "UPDATE devfolio.sync_runs SET ended_at=now(),status=%s,report=%s WHERE id=%s",
            (report["status"], Jsonb(report), report["run_id"]),
        )

    def snapshot(self, repo_id):
        row = self.conn.execute(
            "SELECT revision FROM devfolio.repositories WHERE scope=%s AND index_id=%s AND github_id=%s",
            (self.scope, self.index, repo_id),
        ).fetchone()
        files = self.conn.execute(
            "SELECT path,blob_sha,content_hash FROM devfolio.files WHERE scope=%s AND index_id=%s AND github_id=%s",
            (self.scope, self.index, repo_id),
        ).fetchall()
        for file in files:
            file["chunks"] = self.conn.execute(
                "SELECT id,content_hash FROM devfolio.chunks WHERE scope=%s AND index_id=%s AND github_id=%s AND path=%s ORDER BY chunk_index",
                (self.scope, self.index, repo_id, file["path"]),
            ).fetchall()
        return {"revision": row["revision"] if row else None, "files": {f["path"]: f for f in files}}

    def cached(self, hashes):
        if not hashes:
            return set()
        rows = self.conn.execute(
            "SELECT content_hash FROM devfolio.embeddings WHERE index_id=%s AND content_hash=ANY(%s)",
            (self.index, list(hashes)),
        ).fetchall()
        return {r["content_hash"] for r in rows}

    def cache(self, chunks, vectors):
        if len(chunks) != len(vectors):
            raise ValueError("Embedding batch length mismatch")
        with self.conn.transaction():
            with self.conn.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO devfolio.embeddings(index_id,content_hash,dimensions,embedding) VALUES (%s,%s,%s,%s::extensions.vector) ON CONFLICT DO NOTHING",
                    [
                        (self.index, c["content_hash"], self.settings.dimensions, vector_literal(v))
                        for c, v in zip(chunks, vectors)
                    ],
                )

    def publish(self, repo, sha, changes, deleted):
        from psycopg.types.json import Jsonb

        base = (self.scope, self.index, repo["id"])
        with self.conn.transaction():
            self.conn.execute(
                "INSERT INTO devfolio.repositories(scope,index_id,github_id,name,url,metadata,revision) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(scope,index_id,github_id) DO UPDATE SET name=excluded.name,url=excluded.url,metadata=excluded.metadata,revision=excluded.revision,synced_at=now()",
                (*base, repo["name"], repo["url"], Jsonb(repo), sha),
            )
            for path in deleted:
                self.conn.execute(
                    "DELETE FROM devfolio.files WHERE scope=%s AND index_id=%s AND github_id=%s AND path=%s",
                    (*base, path),
                )
            for path, file in changes.items():
                self.conn.execute(
                    "INSERT INTO devfolio.files(scope,index_id,github_id,path,blob_sha,content_hash) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(scope,index_id,github_id,path) DO UPDATE SET blob_sha=excluded.blob_sha,content_hash=excluded.content_hash,updated_at=now()",
                    (*base, path, file["blob_sha"], file["content_hash"]),
                )
                self.conn.execute(
                    "DELETE FROM devfolio.chunks WHERE scope=%s AND index_id=%s AND github_id=%s AND path=%s",
                    (*base, path),
                )
                with self.conn.cursor() as cursor:
                    cursor.executemany(
                        "INSERT INTO devfolio.chunks(scope,index_id,github_id,path,id,chunk_index,content,content_hash,commit_sha) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        [
                            (*base, path, c["id"], c["chunk_index"], c["content"], c["content_hash"], sha)
                            for c in file["chunks"]
                        ],
                    )

    def finalize(self, eligible_ids, activate=False, allow_empty=False):
        with self.conn.transaction():
            if not eligible_ids and not allow_empty:
                raise ValueError("Empty discovery requires --allow-empty to remove indexed repositories")
            # Only called after a complete discovery AND all repository publications succeed.
            removed = self.conn.execute(
                "DELETE FROM devfolio.repositories WHERE scope=%s AND index_id=%s AND NOT (github_id=ANY(%s::bigint[])) RETURNING github_id",
                (self.scope, self.index, eligible_ids),
            ).fetchall()
            row = self.conn.execute(
                "SELECT active_index FROM devfolio.scopes WHERE id=%s", (self.scope,)
            ).fetchone()
            if row["active_index"] is None or activate:
                self.conn.execute(
                    "UPDATE devfolio.scopes SET active_index=%s,updated_at=now() WHERE id=%s",
                    (self.index, self.scope),
                )
        return len(removed)


class PostgresReader:
    def __init__(self, pool, settings):
        self.pool = pool
        self.settings = settings

    def ready(self):
        with self.pool.connection(timeout=5) as conn:
            row = conn.execute(
                "SELECT active_index FROM devfolio.scopes WHERE id=%s", (self.settings.scope,)
            ).fetchone()
            return bool(row and row["active_index"] == self.settings.index_id)

    def projects(self):
        with self.pool.connection(timeout=5) as conn:
            rows = conn.execute(
                "SELECT r.name,r.url,r.metadata->>'description' AS description,r.metadata->>'language' AS language FROM devfolio.repositories r JOIN devfolio.scopes s ON s.id=r.scope AND s.active_index=r.index_id WHERE r.scope=%s AND r.index_id=%s ORDER BY r.name LIMIT 200",
                (self.settings.scope, self.settings.index_id),
            ).fetchall()
        return rows

    def search(self, vector, limit, repo_name=None):
        from devfolio.embeddings import validate_vector

        vector = validate_vector(vector, self.settings.dimensions)
        with self.pool.connection(timeout=5) as conn:
            return conn.execute(
                "SELECT * FROM devfolio.match_chunks(%s::extensions.vector,%s,%s,%s,%s,%s)",
                (
                    vector_literal(vector),
                    self.settings.index_id,
                    self.settings.scope,
                    limit,
                    self.settings.min_score,
                    repo_name,
                ),
            ).fetchall()
