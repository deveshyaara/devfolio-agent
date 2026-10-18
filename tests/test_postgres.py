"""Real schema, transaction, cosine search and role checks on a disposable database."""

import os
from pathlib import Path

import pytest

from devfolio.store import PostgresReader, PostgresStore, SyncBusy
from devfolio.sync import synchronize

pytestmark = pytest.mark.postgres


@pytest.fixture
def postgres(settings):
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    from psycopg.rows import dict_row

    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL unavailable; real PostgreSQL/pgvector check blocked")
    if not conninfo_to_dict(url).get("dbname", "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must target a disposable database ending in _test")
    with psycopg.connect(url, autocommit=True, row_factory=dict_row, connect_timeout=5) as conn:
        conn.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon; END IF; IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated; END IF; END $$;"
        )
        conn.execute("DROP SCHEMA IF EXISTS devfolio CASCADE")
        conn.execute(Path("migrations/001_knowledge.sql").read_text())
        yield conn, url


def test_real_incremental_search_and_reader_permissions(postgres, pipeline):
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    conn, url = postgres
    source, _, embed, settings = pipeline
    conn.execute("SET ROLE devfolio_writer")
    store = PostgresStore(conn, settings)
    assert synchronize(source, store, embed, settings)["status"] == "success"
    before = embed.requests
    assert synchronize(source, store, embed, settings)["status"] == "success"
    assert embed.requests == before
    with ConnectionPool(
        url, min_size=0, max_size=1, kwargs={"row_factory": dict_row, "options": "-c role=devfolio_reader"}
    ) as pool:
        reader = PostgresReader(pool, settings)
        assert reader.ready()
        hits = reader.search([1.0] + [0.0] * 767, 4)
        assert hits and hits[0]["score"] == pytest.approx(1.0)
        assert hits[0]["metadata"]["path"]
        assert reader.search([-1.0] + [0.0] * 767, 4) == []
        assert reader.projects()[0]["name"] == "project-one"
        with pool.connection() as reader_conn:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                reader_conn.execute("DELETE FROM devfolio.repositories")
    with psycopg.connect(url, autocommit=True, connect_timeout=5) as anonymous:
        anonymous.execute("SET ROLE anon")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            anonymous.execute("SELECT * FROM devfolio.chunks")


def test_postgres_lock_and_atomic_rollback(postgres, pipeline):
    import psycopg
    from psycopg.rows import dict_row

    conn, url = postgres
    source, _, embed, settings = pipeline
    store = PostgresStore(conn, settings)
    synchronize(source, store, embed, settings)
    with psycopg.connect(url, autocommit=True, row_factory=dict_row, connect_timeout=5) as second:
        with store.lock():
            with pytest.raises(SyncBusy):
                with PostgresStore(second, settings).lock():
                    pass
    previous = store.snapshot(1)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        store.publish(
            source.repos[0],
            "bad-revision",
            {
                "README.md": {
                    "blob_sha": "bad",
                    "content_hash": "bad",
                    "chunks": [
                        {"id": "bad", "content_hash": "missing-embedding", "chunk_index": 0, "content": "bad"}
                    ],
                }
            },
            [],
        )
    assert store.snapshot(1) == previous
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO devfolio.embeddings(index_id,content_hash,dimensions,embedding) VALUES (%s,'invalid-dimension',768,'[1]'::extensions.vector)",
            (settings.index_id,),
        )
