# DevFolio Agent

LangGraph + Gemini portfolio assistant, served through Streamlit and embedded by the Next.js portfolio. Project knowledge lives in Supabase Postgres/pgvector. GitHub ingestion is an explicit scheduled/manual job; importing the agent or sending a message never starts ingestion.

[Open the assistant](https://devfolio-agent.streamlit.app/) · [Portfolio](https://devfolio-taupe.vercel.app/) · [Sync workflow](https://github.com/deveshyaara/devfolio-agent/actions/workflows/sync.yml)

## Deployment status

Verified on **18 October 2026**:

| Item | Observed result |
| --- | --- |
| Knowledge store | Supabase Postgres with pgvector; 9 repositories, 9 files and 199 chunks |
| Embeddings | `gemini-embedding-2`, 768 dimensions |
| Chat models | `gemini-3.5-flash`, with `gemma-4-26b-a4b-it` as the transient-error fallback |
| Database access | Separate reader and ingestion logins, TLS connections, RLS on all seven private tables |
| Retrieval | Runtime readiness passed; a WealthWise query returned relevant README evidence |
| Hosting | Streamlit Community Cloud, `master`, entry point `app.py`, Python 3.12 with `uv.lock` |
| Manual Actions sync | Success: all 199 chunks reused, zero embedding requests, 9.959 seconds |
| CI | Dependency consistency, Ruff lint and formatting; automated tests removed |

The [verified manual sync run](https://github.com/deveshyaara/devfolio-agent/actions/runs/39098131935) completed after [setup and cleanup PR #2](https://github.com/deveshyaara/devfolio-agent/pull/2) merged. Counts and timings are a deployment snapshot, not fixed limits. Chat and new embeddings require available Google API quota; an unchanged sync can reuse the stored corpus without embedding calls.

## Architecture

```text
GitHub public repositories with configured topic
  → paginated discovery → immutable commit/tree/blob snapshots
  → allowlisted Markdown → stable heading-aware chunks
  → reusable Gemini embeddings → atomic Postgres publication
  → bounded cosine retrieval → LangGraph tools → Gemini → Streamlit iframe
```

## Development

Python 3.12, [uv](https://docs.astral.sh/uv/), and a Supabase database with pgvector are required.

```sh
uv sync --frozen --group dev
cp .env.example .env
# Fill server-side configuration; do not commit .env.
uv pip check
uv run --group dev ruff check .
uv run --group dev ruff format --check .
```

Apply `migrations/001_knowledge.sql` as database owner and provision separate reader/writer login users as described in [operations](docs/OPERATIONS.md). Then:

```sh
uv run python -m devfolio.sync --activate-index
uv run streamlit run app.py
# Optional health sidecar on a host that supports it:
uv run uvicorn health:app --host 0.0.0.0 --port 8000
```

Use `SUPABASE_SYNC_DB_URL` only in ingestion. Runtime `SUPABASE_DB_URL` should belong to a user granted `devfolio_reader`; it cannot write knowledge. Every connection to a remote database must require TLS. No Supabase HTTP key is used.

## Configuration

Copy the names and placeholders from [`.env.example`](.env.example). Store actual credentials in local `.env`, Streamlit secrets or GitHub Actions secrets.

| Setting | Streamlit / local runtime | GitHub Actions |
| --- | --- | --- |
| `GOOGLE_API_KEY` | Server secret | Repository secret |
| `SUPABASE_DB_URL` | Reader connection string; require TLS | Not needed |
| `SUPABASE_SYNC_DB_URL` | Trusted local ingestion only | Repository secret; writer connection string |
| `GITHUB_USERNAME` | Source GitHub account | Set repository variable `PORTFOLIO_GITHUB_USERNAME`; workflow maps it to `GITHUB_USERNAME` |
| `PORTFOLIO_TOPIC` | `portfolio` by default | Repository variable; same value as runtime |
| `EMBEDDING_MODEL` | `gemini-embedding-2` | Optional repository variable; must match runtime |
| `EMBEDDING_VERSION` | `2026-04` | Optional repository variable; must match runtime |
| `EMBEDDING_DIMENSIONS` | `768` | Optional repository variable; must match runtime |
| `CHAT_MODEL` / `FALLBACK_CHAT_MODEL` | Chat model overrides | Not needed for ingestion |
| `MY_*` contact settings | Owner name, LinkedIn, resume and scheduling links | Not needed |

Keep the writer URL off the Streamlit host. No privileged credentials belong in the Next.js frontend or committed configuration. GitHub reserves repository variable names starting with `GITHUB_`, so use the account variable name shown above.

## Dependencies

`pyproject.toml` and `uv.lock` define the dependencies. Streamlit Community Cloud installs from the lockfile; the default installation excludes development tools. After deliberate dependency changes:

```sh
uv lock
uv sync --frozen
```

## Knowledge synchronization

- Daily schedule: **03:17 UTC / 08:47 IST** on the default branch, `master`. GitHub may delay scheduled jobs.
- Manual run: **Actions → Sync portfolio knowledge → Run workflow**. Leave `activate_index` disabled for routine updates; enable it only when publishing a completely built new profile.
- Local incremental update: `uv run python -m devfolio.sync`.
- Reports: local `sync-report.json` is ignored by Git; Actions retains the `sync-report` artifact for 14 days.
- Writers are serialized by workflow concurrency and a database advisory lock. Failed repository updates retain their previous successful snapshot and prevent profile activation or source-set pruning.

## Behavior

- Preserves the six tools: projects, project search, personal info, scheduling, LinkedIn, resume.
- Defaults to the existing Gemini chat model and Gemma fallback. Fallback handles transient failures only. Configure an empty `FALLBACK_CHAT_MODEL` to disable it.
- Gemini Embedding 2 defaults to explicitly requested **768 dimensions**, validated on every response. Its search/document prefixes follow [Google's embedding documentation](https://ai.google.dev/gemini-api/docs/embeddings). Model 001 is also supported with its own task types and isolated profile.
- Root READMEs and documentation under `docs/` only; no source code, dependencies, hidden files, symlinks, or secret paths. Recognized database password examples have their complete credential fields removed before embedding. Other suspected credentials or unsupported document sizes fail that repository update and preserve its last snapshot.
- Unchanged revisions cause zero document embedding calls. Changed documents reuse existing content hashes. Removed repositories are pruned only after complete discovery and successful processing of every eligible repository; an empty source set needs explicit `--allow-empty`.
- New model/version/chunk profiles build separately. `--activate-index` publishes a complete profile; deploy matching runtime settings only afterward.
- Conversation checkpoints are **anonymous, session-owned, temporary**. They reset after inactivity, a turn limit, interruption, or restart. Project knowledge survives restart. There is no account system or public thread lookup endpoint.
- Streamlit incrementally renders model output. Closing a generator releases limits and clears interrupted checkpoint state. Provider calls have transport timeouts; cancellation is cooperative while a provider call is blocked.
- Health sidecar: `/health` checks process liveness; `/ready` checks database accessibility and the active profile. Standard Streamlit liveness remains `/_stcore/health`.

## Verification and deployment

See [operations and rollback](docs/OPERATIONS.md) and [live setup verification](docs/LIVE_SETUP.md). CI checks dependency consistency, lint and formatting. The automated suite and old live diagnostic scripts were removed at the owner's request; CI no longer runs tests or provisions a disposable database.

Use the deployment acceptance checks to verify live model responses, database availability and hosted chat behavior after changes.

## Repository layout

| Path | Purpose |
| --- | --- |
| `app.py` | Streamlit chat UI |
| `agent.py` | Command-line conversation and compatibility entry point |
| `devfolio/` | Runtime, tools, sessions, retrieval, ingestion and database access |
| `migrations/001_knowledge.sql` | Private pgvector schema, roles, policies and search function |
| `health.py` | Optional liveness/readiness sidecar |
| `.github/workflows/` | Code checks and daily/manual synchronization |
| `scripts/audit_secrets.py` | Credential-pattern audit of tracked files and Git history |
| `docs/OPERATIONS.md` | Configuration, deployment, recovery and rollback |
