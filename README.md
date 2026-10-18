# DevFolio Agent

LangGraph + Gemini portfolio assistant, served through Streamlit and embedded by the Next.js portfolio. Project knowledge lives in Supabase Postgres/pgvector. GitHub ingestion is an explicit scheduled/manual job; importing the agent or sending a message never starts ingestion.

```text
GitHub public repositories with configured topic
  → paginated discovery → immutable commit/tree/blob snapshots
  → allowlisted Markdown → stable heading-aware chunks
  → reusable Gemini embeddings → atomic Postgres publication
  → bounded cosine retrieval → LangGraph tools → Gemini → Streamlit iframe
```

## Development

Python 3.12, [uv](https://docs.astral.sh/uv/), and a Supabase database with pgvector are required. No database is needed for the offline tests.

```sh
uv sync --frozen
cp .env.example .env
# Fill server-side configuration; do not commit .env.
uv run pytest -m 'not postgres'
uv run ruff check .
uv run ruff format --check .
```

Apply `migrations/001_knowledge.sql` as database owner and provision separate reader/writer login users as described in [operations](docs/OPERATIONS.md). Then:

```sh
uv run python -m devfolio.sync --activate-index
uv run streamlit run app.py
# Optional health sidecar on a host that supports it:
uv run uvicorn health:app --host 0.0.0.0 --port 8000
```

Use `SUPABASE_SYNC_DB_URL` only in ingestion. Runtime `SUPABASE_DB_URL` should belong to a user granted `devfolio_reader`; it cannot write knowledge. Every connection to a remote database must require TLS. No Supabase HTTP key is used.

`requirements.txt` is the hash-pinned production export for Streamlit Community Cloud; `pyproject.toml` and `uv.lock` are the dependency source of truth. Regenerate the export after deliberate upgrades:

```sh
uv export --frozen --no-dev --no-emit-project --format requirements-txt --output-file requirements.txt
```

## Behavior

- Preserves the six tools: projects, project search, personal info, scheduling, LinkedIn, resume.
- Defaults to the existing Gemini chat model and Gemma fallback. Fallback handles transient failures only. Configure an empty `FALLBACK_CHAT_MODEL` to disable it.
- Gemini Embedding 2 defaults to explicitly requested **768 dimensions**, validated on every response. Its search/document prefixes follow [Google's embedding documentation](https://ai.google.dev/gemini-api/docs/embeddings). Model 001 is also supported with its own task types and isolated profile.
- Root READMEs and documentation under `docs/` only; no source code, dependencies, hidden files, symlinks, or secret paths. Suspected credentials or unsupported document sizes fail that repository update and preserve its last snapshot.
- Unchanged revisions cause zero document embedding calls. Changed documents reuse existing content hashes. Removed repositories are pruned only after complete discovery and successful processing of every eligible repository; an empty source set needs explicit `--allow-empty`.
- New model/version/chunk profiles build separately. `--activate-index` publishes a complete profile; deploy matching runtime settings only afterward.
- Conversation checkpoints are **anonymous, session-owned, temporary**. They reset after inactivity, a turn limit, interruption, or restart. Project knowledge survives restart. There is no account system or public thread lookup endpoint.
- Streamlit incrementally renders model output. Closing a generator releases limits and clears interrupted checkpoint state. Provider calls have transport timeouts; cancellation is cooperative while a provider call is blocked.
- Health sidecar: `/health` checks process liveness; `/ready` checks database accessibility and the active profile. Standard Streamlit liveness remains `/_stcore/health`.

## Verification and deployment

See [audit](docs/AUDIT.md), [operations and rollback](docs/OPERATIONS.md), and [engineering/test report](docs/ENGINEERING_REPORT.md). Tests use mocks except those explicitly marked `postgres`; use only a disposable database ending in `_test` for those. Root `test_*.py` files are preserved manual, live-service diagnostics and are deliberately excluded from offline pytest collection.

Local tests cannot establish live Gemini answer quality, production Supabase availability, or deployed iframe/Stop behavior. Complete the deployment acceptance checks before switching production away from the previous FAISS release.
