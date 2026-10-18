# Reliability audit — 2026-10-18

Inspected local code, tracked files, dependencies, recent history and GitHub repository metadata before implementation. Backend default branch is **master** at `e88d5605d4a0a063a91bd744dfc3d57f8f721a90`; local branch was main, clean. Frontend default branch is **main** at `9b5011f80e0bc0406749d0524ae258a9de13e05f`, clean when checked outside the filesystem sandbox.

| Finding | Root cause / affected files | Verification required |
| --- | --- | --- |
| Startup clones/pulls every project and embeds complete READMEs into new FAISS | `agent.py`, module-level `create_project_retriever`; no persistence or chunking | Import/startup with network denied; incremental sync tests |
| Discovery only handles first search page, catches failures and mutates global metadata | `fetch_and_load_projects`; no timeout, unsafe clone deletion, stale caches | Paginated authoritative discovery, failure and deletion tests |
| README claims nonexistent all-context and HuggingFace fallback tools | README diverged from six actual tools | Preserve actual contact, scheduling, resume, LinkedIn, listing, retrieval tools |
| Shared process MemorySaver has no retention or ownership validation | `agent.py`; Streamlit supplies random UUID but global graph accepts arbitrary IDs | Session-owned graph, validation, expiry, isolation tests |
| No REST chat route or custom token streaming exists | `app.py` uses blocking invoke; frontend `src/components/chatbot-card.tsx` embeds Streamlit URL | Preserve iframe contract; add streaming inside Streamlit and cancellation |
| Raw exceptions exposed to visitors; no request limits | `app.py`, `run_chat`; no rate/concurrency/time budget | Safe errors, size, timeout, cancellation and rate tests |
| Incompatible/obsolete heavyweight dependency snapshot | requirements includes unused Torch/HuggingFace/FAISS and old Google transport | Clean isolated install, resolver check, regression suite |
| Existing test_*.py are live diagnostic scripts, execute on import, and sometimes pass history where thread ID is expected | Root scripts require secrets/network; print success without assertions | Preserve as manual diagnostics; separate deterministic offline pytest suite |
| Devcontainer disables CORS and XSRF | `.devcontainer/devcontainer.json` | Restore framework security defaults |

Frontend is Next.js 16 (package manifest), React 18, Vercel-compatible, **not** a custom chat API client. It contains no backend credentials or session IDs; iframe lifecycle and WebSocket transport belong to Streamlit. No chat integration change is required for a compatible backend upgrade. Existing iframe explicitly grants media capabilities the agent does not use. Frontend write access is outside this task's writable roots. Validation later found a pre-existing JSX apostrophe lint failure in `src/components/contact-section.tsx`; an approved, rendering-preserving entity escape fixes it on a separate feature branch.

## Intended changes and compatibility

Add one direct Psycopg/pgvector repository layer, private schema migrations, explicit Google embedding adapter, safe Markdown chunker, incremental GitHub snapshot sync command, workflows, offline tests and deployment runbook. Replace import-time ingestion with lazy runtime setup. Retain `app.py` entry point, tool names, public personal configuration names, and iframe URL. Leave old FAISS data and diagnostic scripts intact for rollback via previous release; do not deserialize old pickle caches.

Required external prerequisites: Supabase Postgres with pgvector; TLS-capable direct/session-mode pooler access; separate reader and ingestion database roles; Google embedding/chat access; GitHub Actions secret configuration; Streamlit host deployment access. Available local configuration has Google/GitHub/personal names but **no Supabase database URL**. Values were not printed. Development uses mocks; the later explicit live probe rejected the configured Google credentials and did not establish model readiness.

Configuration: GOOGLE_API_KEY, GITHUB_USERNAME, PORTFOLIO_TOPIC, SUPABASE_DB_URL (runtime reader), SUPABASE_SYNC_DB_URL (Actions writer), EMBEDDING_MODEL, EMBEDDING_VERSION, EMBEDDING_DIMENSIONS, CHAT_MODEL, optional FALLBACK_CHAT_MODEL, existing MY_* variables. No Supabase HTTP service-role key or browser key is needed with direct Postgres.

Backwards compatibility risks: switching the deployment before migration and first sync makes project evidence unavailable; new model profiles require an explicit full build and activation; anonymous conversations deliberately expire and are not recovered after restarts. Real LLM grounding and hosting behavior require live acceptance, beyond deterministic policy tests.
