# Configuration, deployment and operations

## Server configuration

Use `.env.example` for variable names and placeholders. Never commit credentials or paste them into logs. Prefer the host/Actions secret manager. Streamlit also supports root-level secrets that are exported as environment variables; keep secrets out of nested sections if using this configuration path.

| Variable | Where | Purpose |
| --- | --- | --- |
| GOOGLE_API_KEY | Streamlit host and Actions secrets | Gemini chat/query embeddings or document ingestion |
| SUPABASE_DB_URL | Streamlit/optional health host only | TLS reader login, granted devfolio_reader |
| SUPABASE_SYNC_DB_URL | Actions secrets / trusted sync shell only | TLS writer login, granted devfolio_writer |
| GITHUB_USERNAME | Host and Actions repository variable | Source account and knowledge scope |
| PORTFOLIO_TOPIC | Host and Actions variable, default portfolio | Public repository eligibility |
| GITHUB_TOKEN | Ingestion only, optional | Public API quota; workflow uses github.token by default |
| PORTFOLIO_GITHUB_TOKEN | Optional Actions secret | Override token when public API quota requires it |
| EMBEDDING_MODEL | Host and Actions variable | gemini-embedding-2 (default) or gemini-embedding-001 |
| EMBEDDING_VERSION | Host and Actions variable | Operator-controlled release marker, default 2026-04 |
| EMBEDDING_DIMENSIONS | Host and Actions variable | 768 (default), 1536 or 3072 |
| CHAT_MODEL | Host only | Existing gemini-3.5-flash default |
| FALLBACK_CHAT_MODEL | Host only | Existing gemma-4-26b-a4b-it default; empty disables fallback |
| RETRIEVAL_TOP_K / RETRIEVAL_MIN_SCORE | Host only | Defaults 4 / 0.5; evaluate with real portfolio questions |
| MY_NAME, MY_LINKEDIN_URL, MY_RESUME_URL, MY_CALENDLY_LINK, MY_PROFILE_PIC_URL | Host only | Existing public portfolio/contact configuration |
| TEST_DATABASE_URL | Tests only | Disposable migrated PostgreSQL database ending in _test |

The frontend has no backend API variable because it embeds the existing Streamlit URL. Keep its browser bundle free of all variables above. Supabase does not run this Python backend. Vercel runs the frontend; it does not keep the Streamlit agent warm.

## Safe initial deployment

1. Keep the current production deployment serving until this sequence completes. Record its branch/commit and configuration. Retain local FAISS caches; the new release does not read or delete them.
2. Create a Supabase project, take a database backup, and apply `migrations/001_knowledge.sql` using SQL Editor or psql as database owner. This is a one-time versioned migration, not a startup operation. Extension installation assumes pgvector is in `extensions`, as on Supabase. If already installed elsewhere, plan and test an extension schema migration before applying this SQL.
3. The migration creates NOLOGIN roles. Create two distinct LOGIN users with strong passwords through a secure administrative session. Grant `devfolio_reader` to the runtime login and `devfolio_writer` to the ingestion login. Do not grant admin, BYPASSRLS, anon or authenticated privileges to those users. They must not own the tables. Set connection/statement/idle transaction timeouts appropriate to the hosting plan. Never commit the password-setting commands.
4. Use the dashboard's direct connection or **session-mode** pooler for the writer, because PostgreSQL session advisory locks require a stable connection. Transaction-mode pooling is unsupported for ingestion. Use TLS. If the runner lacks IPv6, use the session-mode pooler IPv4 endpoint. This code does not need SUPABASE_URL or a service-role/secret HTTP key.
5. Install `uv sync --frozen`. Set the Actions secrets/variables above. Run `uv run python -m devfolio.sync --activate-index` in a trusted environment. A nonzero exit or report status failed must be investigated. Rerun safely after correcting the cause.
6. Verify repository/file/chunk counts, inspect source metadata, run representative query embeddings and retrieval, and verify a second unchanged run reports `embedding_requests: 0`. The script validates returned vector dimensions; local tests use synthetic vectors, so live dimension verification remains mandatory.
7. Deploy this backend **feature branch first to a staging app**, with only reader and Google credentials plus public configuration. Entry point stays `app.py`; install using the exported `requirements.txt` or `uv sync --frozen --no-dev`. Startup initializes clients only. Confirm `/_stcore/health` and a real project conversation. When the host supports a second process, run `uvicorn health:app` for `/health` and `/ready`; Community Cloud does not expose this separate sidecar automatically.
8. Test the iframe against the staging backend, then promote the backend on the existing production URL after acceptance. Frontend iframe and deployment configuration stay compatible. Deploy the frontend lint-only change through its normal PR/Vercel flow.
9. Exercise project list/search, all four contact tools, multi-turn conversation, separate browser sessions, Stop during generation, provider outage, empty index, and page reload. Verify incremental token rendering, safe errors, and no cross-session history. A stopped response is not automatically retried; start a fresh conversation if a tool turn was interrupted.
10. Merge through repository policy. Scheduled workflows run only on backend default branch **master**. Monitor first successful scheduled run before retiring the prior release.

## Ingestion policy and failure recovery

The daily workflow runs at 03:17 UTC (08:47 India time), plus manual Actions → Sync portfolio knowledge → Run workflow. Set `activate_index` only when publishing a new profile. Workflow concurrency queues manual/scheduled writers; a PostgreSQL scope lock also excludes writers launched elsewhere. A killed writer's lock is released when its DB session closes; the next run marks abandoned running reports failed.

Discovery paginates the account's public repositories and filters topics. Failure or a truncated Git tree never authorizes deletion. Commit trees and blobs are fetched at immutable SHAs, avoiding a branch changing halfway through a sync. Git cloning is unnecessary. Changed revisions fetch a tree and compare blob SHAs; unchanged files are not downloaded. Normalized content hashes identify embedding reuse. Chunk IDs use repository ID, path, content hash and duplicate occurrence, so edits to one heading do not invalidate unrelated sections.

Every successful embedding is cached durably before repository publication. If a later embedding fails, previous content remains visible; cached successes can be reused. A narrow crash after the provider succeeds but before the cache commit may repeat that one billable call; exactly-once external billing is not promised. Transient HTTP/network failures retry up to four times with bounded exponential backoff and jitter; permanent authentication/validation errors do not retry. GitHub rate exhaustion is distinguished from ordinary forbidden access. Requests use connect/read timeouts.

All changed/deleted files, new chunk references, repository metadata and the successful revision publish in one repository transaction. Failed publication rolls back. Other repositories may successfully advance in the same run; the overall report is failed, and source-set pruning/activation is withheld. Reports identify repository ID, operation stage, exception class and last successful revision without raw exception strings. If DB connectivity itself fails, the process exits nonzero; a report can remain running until recovered by the next writer.

Repository removals cascade files/chunks only within the exact account/topic/index profile, after every source repository succeeds. A zero-repository discovery fails by default; after reviewing the source account/topic, explicitly run `--allow-empty` to clear that profile. Old inactive profiles and unused cached embeddings remain for rollback. Periodically review their storage; garbage collection is deliberately an administrative operation rather than automatic deletion.

## Model/index migration and rollback

Profile ID hashes model name, version marker, dimensions, chunk size/overlap and preprocessing version. Vectors from different profiles never mix. Named Google model releases are not immutable provider snapshots; bump EMBEDDING_VERSION deliberately when a provider/model change requires rebuilding.

Build the new profile with ingestion settings while runtime remains on the old settings. A successful sync without `--activate-index` stages data without changing the active profile. Validate staged counts with trusted SQL. Activate only after a completely successful pass, then immediately deploy matching runtime settings. A mismatch makes readiness fail and retrieval return unavailable, rather than silently querying incompatible vectors. There may be a brief readiness gap during rollout; schedule accordingly.

For rollback, rerun ingestion using the previous known-good configuration and `--activate-index`, then restore the runtime configuration/commit. Old profiles remain in the database. To return to the original FAISS application, redeploy commit `e88d560` and its original dependencies/configuration; it will rebuild as before. Do not remove the knowledge schema during emergency rollback.

For a permanent schema uninstall, first stop every reader/writer, export/backup the private schema, confirm its tables are no longer required, then remove only `devfolio` through a reviewed administrative migration. Keep the shared vector extension and roles used elsewhere. No automated destructive down migration runs at startup.

## Conversation and request policy

Project memory is persistent Postgres data. Conversation memory is a separate MemorySaver owned by each Streamlit session, with a random internal UUID. No browser-supplied thread lookup endpoint exists. No authentication or persistent checkpoint tables are introduced for this anonymous product. Restarts intentionally lose conversations; tests verify this. New conversation, 12 turns or 30 minutes inactivity replaces graph/checkpointer state. Inactivity expiry is enforced on the next message; disconnected-session cleanup is governed by Streamlit's host settings.

Input is capped at 4000 characters / 16000 UTF-8 bytes, model output at 2048 tokens, graph recursion at 12 steps, and retrieval at four selected chunks / 8000 serialized characters. Session rate is six requests/minute, process rate 120/minute, process concurrency four, and duplicate concurrent turns in one session are rejected. These are process-local controls suitable for a single small portfolio instance. Multiple replicas or deliberate session churn require edge rate limiting on the chosen host; do not trust arbitrary client IP headers as identity.

The request budget is 60 seconds checked between stream events and before model calls. Provider calls use 20-second transport timeouts, DB acquisition five seconds, and SQL statement limits. A blocked synchronous transport can finish after cancellation/deadline; closing the generator prevents subsequent graph steps and discards interrupted conversation state. In-flight provider work may still be billed. Real hosted Stop/WebSocket behavior must be verified on deployment.

Retrieval text is untrusted, source-labelled tool data. The system policy forbids instruction-following from repositories and unsupported facts. No shell, arbitrary URL fetch, credential access or destructive tool is exposed to the agent. Policy tests are not a proof of adversarial LLM behavior; use real prompt-injection evaluation during staging. Do not log full prompts, model responses or private user messages.

## Health, metrics and hosting

`/_stcore/health` and optional `/health` are liveness. Optional `/ready` checks a readable active index matching runtime configuration and returns generic 503 on failure; empty-but-successfully-activated knowledge is operational but returns no evidence. It does not run a paid model probe. Reuse a four-connection reader pool and shared SDK clients; ingestion owns/closes its dedicated DB and HTTP sessions.

Lightweight JSON logs include runtime setup, query embedding, retrieval, first token, total request durations and correlation IDs. Sync reports include revisions/counts, embedding requests/failures, retries and duration. Actions retains report artifacts for 14 days. Restrict log/artifact access. Configure log/database report retention according to the hosting plan; no paid observability service is required.

Streamlit Community Cloud can sleep and cold-start; this upgrade removes repository cloning and corpus embedding from that path but cannot guarantee continuous availability. If always-on service is needed, run Streamlit on a Python/container host with WebSocket support and appropriate idle/request limits. Terminate TLS at the host, preserve Streamlit CORS/XSRF defaults, and restrict iframe embedding origins at the hosting layer when supported. Vercel only hosts the Next.js shell. Benchmark before adding HNSW: exact cosine search avoids approximate-index overhead for this small corpus, and untyped vectors support multiple isolated dimensions. A future HNSW index needs a dimension/profile-specific cast and measured query-plan change.

## Validation commands

```sh
uv sync --frozen
uv pip check
uv run ruff check .
uv run ruff format --check .
uv run pytest -m 'not postgres'
uv run python scripts/audit_secrets.py --history
```

For real SQL tests, create a disposable `devfolio_test` database with pgvector support and set TEST_DATABASE_URL. Tests intentionally drop/recreate **only its devfolio schema**, and refuse database names without the `_test` suffix. `uv run pytest` includes these checks. CI provisions a disposable pgvector service and runs them on pushes/PRs. Do not point tests at a production database.

The root diagnostics call live models and are not acceptance tests. Run them only deliberately, with test credentials/quota. A real Supabase migration, first ingestion, live retrieval/LLM evaluation, deployed iframe and Actions run remain separate acceptance gates.
