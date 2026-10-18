# DevFolio reliability upgrade — engineering report

Date: 2026-10-18, India time. This is an implemented and locally tested upgrade on feature branches. It is **not a verified production deployment**.

## A. Executive summary

Replaced import-time GitHub cloning/full FAISS embedding with lazy persistent Postgres retrieval and a separate incremental ingestion command. Added atomic repository updates, durable embedding reuse, explicit model profiles, database access controls, scheduled/manual workflows, session isolation, bounded requests, incremental Streamlit rendering, safe failures, health checks, reproducible dependencies, and automated tests. Preserved the six existing portfolio/contact tools, Gemini/Gemma model defaults, Streamlit entry point and Next.js iframe integration.

Production cutover is blocked by missing Supabase connection configuration and rejected Google credentials. The existing production release must stay in place until staging acceptance is complete.

## B. Repository changes

Backend, `deveshyaara/devfolio-agent`:

| Files | Purpose |
| --- | --- |
| agent.py | Safe import, lazy compatibility facade and explicit session CLI; no startup ingestion |
| app.py | Existing Streamlit UI entry point, session-owned graph, incremental rendering and safe failures |
| devfolio/config.py | Validated account/topic/profile/TLS configuration |
| devfolio/chunking.py | Explicit documentation allowlist, credential/binary/size screening, normalized Markdown, heading/fence-aware stable chunks, multilingual byte limits |
| devfolio/embeddings.py | Current Google SDK adapter, explicit dimensions, model-specific retrieval format, finite/nonzero checks, counters and bounded retries |
| devfolio/github.py | Complete public topic discovery and immutable tree/blob retrieval with limits/timeouts |
| devfolio/store.py | One Psycopg repository abstraction, durable vector cache, transactional publication, advisory lock, scoped pruning, read-only retrieval |
| devfolio/sync.py | Independent incremental sync CLI, structured reports, explicit activation/deletion controls |
| devfolio/runtime.py | Six preserved tools, grounding policy, graph construction, transient-only model fallback, shared lazy clients |
| devfolio/sessions.py | Session ownership, TTL/turn bounds, validation/rate/concurrency limits, deadlines and generator cleanup |
| devfolio/logging.py | Sanitized JSON performance/correlation logging |
| health.py | Optional FastAPI liveness/readiness sidecar, generic failure responses |
| migrations/001_knowledge.sql | Private normalized pgvector schema, cosine function, constraints and RLS/roles |
| .github/workflows/sync.yml | Daily/manual ingestion, queued writers, protected secret injection and report artifact |
| .github/workflows/test.yml | Offline tests plus real disposable pgvector CI service |
| tests/ | 69 deterministic tests across chunking, sync, retrieval, sessions, tools, UI, SQL, configuration and workflows |
| scripts/audit_secrets.py | Tracked-file/Git-history pattern scan without printing matches |
| scripts/live_probe.py | Deliberately invoked, billable embedding and tool-roundtrip smoke test; excluded from test suite/startup |
| pyproject.toml, uv.lock, requirements.txt, .python-version | Python 3.12 environment, compatible SDK resolution, hash-pinned production export; removes unused ML/FAISS runtime dependencies |
| .env.example, .gitignore | Sanitized configuration, excludes generated state and local environments |
| .streamlit/config.toml | One-megabyte transport/upload payload bounds before input validation |
| .devcontainer/devcontainer.json | Python 3.12; restores normal CORS/XSRF defaults |
| README.md, docs/AUDIT.md, docs/OPERATIONS.md, this report | Actual architecture, audit, installation, deployment, maintenance and rollback |

Root live diagnostic scripts and existing local FAISS caches remain untouched. Their historical assumptions are not used by the new offline suite.

Frontend, `deveshyaara/devfolio`:

- Inspected package manifest, history, Next config, application/components and environment references.
- `src/components/contact-section.tsx`: escaped a JSX apostrophe to resolve the pre-existing ESLint failure; rendered content stays equivalent.
- Existing chatbot iframe URL, widget behavior and public configuration remain compatible. There is no custom fetch/SSE chat contract, public thread-ID API, or browser-side Gemini/Supabase credential to migrate.

## C. Final architecture

GitHub Actions discovers public repositories for GITHUB_USERNAME/PORTFOLIO_TOPIC, obtains immutable revisions, reads only eligible documentation, normalizes/chunks it, and requests missing Gemini embeddings. Postgres stores reusable vectors and repository/file/chunk snapshots. Each successful repository transaction publishes all its replacements/deletions and revision together. A separate reader login performs parameterized cosine search for LangGraph's project tool. Gemini uses bounded source-labelled evidence alongside the existing personal/contact tools. Streamlit renders output incrementally inside the existing Next.js iframe.

Application import/startup never discovers repositories, clones/pulls, reads corpus files, embeds documents or mutates the knowledge database. Optional readiness checks connect to the database and verify the configured profile. A paid query embedding is generated only for a project search.

Conversation checkpoints are separate, anonymous and temporary: one MemorySaver per Streamlit session with no public global thread lookup. Restart intentionally loses conversation history; it does not lose project knowledge. No authentication/account system or persistent conversation database was added.

## D. Database implementation

`001_knowledge.sql` enables pgvector in `extensions` and creates private schema `devfolio`:

- `indexes`: immutable profile ID, model/preprocessing metadata, dimensions and creation time.
- `scopes`: account/topic identity and active index pointer.
- `repositories`: composite scope/profile/GitHub ID identity, name, canonical URL, metadata, successful revision and sync time.
- `files`: path, Git blob SHA, normalized content hash and update time, cascading from repository.
- `embeddings`: profile/content-hash unique cache, vector, constrained dimensions and creation time; no source plaintext.
- `chunks`: stable ID, position, source path, content/hash, commit and creation time, foreign keys to file/vector.
- `sync_runs`: run UUID, timestamps, final status and structured report.

Composite primary/unique/foreign keys prevent duplicates and cross-profile references. File/repository deletions cascade chunk references. File and run-time indexes support common operations. Exact cosine search deliberately avoids HNSW overhead for a small portfolio. `match_chunks` checks active profile/dimensions, supports repository filtering, enforces a bounded result limit and returns content/source metadata/score. SQL parameters carry all application values.

RLS is enabled on every table. NOLOGIN `devfolio_reader` and `devfolio_writer` roles have separate policies/grants; runtime logins must inherit only reader access, ingestion only writer access. Anonymous/authenticated browser roles have no schema/table/function access. The schema is not exposed through Supabase HTTP APIs. No service-role HTTP key is needed. Tests exercised writer access, reader SELECT/search, denied reader DELETE, denied anon access and dimension constraints on real PostgreSQL 16/pgvector.

## E. Incremental synchronization

Unchanged repository revision: no tree download or document embedding. Changed revision: compare allowlisted tree blob SHAs against the successful snapshot, download only changed/new files, normalize and hash content, retain stable IDs for unchanged sections, and embed only content absent from that profile's durable cache. Each embedding success is saved immediately. Changes/deletions are committed atomically per repository, including its checkpoint; failures preserve previous content.

Transient failures use bounded backoff/jitter; permanent auth/validation errors fail immediately. Partial repository failures make the run failed and block pruning/activation. Complete successful discovery authorizes removed-repository pruning only within its scope/profile. A completely empty set additionally requires `--allow-empty`. Files/chunks disappear from search through cascading references; unused vector cache records remain available for rollback/reuse and require deliberate administrative cleanup when no longer wanted.

New model/version/dimensions/preprocessing creates a separate profile. Build it first; activate only after every source repository succeeds, then deploy matching runtime settings. Runtime readiness fails on mismatches. There is no vector fallback that silently mixes models. A crash between a provider response and its DB cache commit can repeat that one API call; exactly-once external billing is not guaranteed.

## F. Configuration and external prerequisites

See `.env.example` and the complete variable table in [operations](OPERATIONS.md). Required server-only Google key and TLS reader DB URL belong on the Python host; writer DB URL belongs in Actions/trusted ingestion only. Account/topic and embedding profile settings must match on both sides. Existing MY_* public contact settings remain supported. The frontend requires no new privileged configuration.

Local inspection found Google/GitHub/personal configuration names but no SUPABASE_DB_URL or SUPABASE_SYNC_DB_URL. Values were not displayed. Live Google requests rejected the configured credentials. Supply a valid appropriately restricted Google key and verify access to both configured chat models and the embedding model.

## G. Observed test and audit results

| Command/check | Observed result |
| --- | --- |
| git status, branch/log/remote, ls-remote --symref origin HEAD; GitHub repository metadata | Both initial trees clean; backend default master at e88d5605d4a0a063a91bd744dfc3d57f8f721a90, frontend main at 9b5011f80e0bc0406749d0524ae258a9de13e05f; push permissions available |
| uv lock; uv sync --frozen | Initial flat-package discovery and incompatible tentative pins failed; corrected explicit dependency metadata/resolution installed successfully; lockfile committed |
| uv export --frozen --no-dev --no-emit-project --format requirements-txt --output-file requirements.txt | Completed; hash-pinned production export generated |
| uv pip check | 87 installed packages checked, compatible |
| python -m pytest -q with disposable TEST_DATABASE_URL | **69 passed** in the final suite; includes real PostgreSQL 16/pgvector, not production Supabase |
| First GitHub Actions test run | Failed during collection because the pytest console entry point omitted the uninstalled repository package from sys.path. Added explicit pytest pythonpath configuration, then verified the console invocation and reran CI |
| ruff check . / ruff format --check . | Passed after formatting the final SQL test; fixes applied during implementation |
| PostgreSQL tests alone | Both passed before inclusion in final suite; writer/reader permissions, cosine filtering, transaction rollback, scope advisory lock, dimension constraint verified |
| Streamlit AppTest | Simulated chat input → real LangGraph → mocked model → incremental UI response; separate session histories and generic configuration errors verified. Initial path/harness issues corrected |
| python scripts/audit_secrets.py --history | Known credential patterns absent in original tracked backend files/history; rerun against final staged files before commit |
| Same history scanner from frontend | 432 file/blob checks, zero known-pattern findings; no matched values printed |
| Compare configured backend credential values against .next/static JS | 20 JavaScript files checked, zero matches |
| frontend npm run typecheck | Passed |
| frontend npm run lint | Initially one existing no-unescaped-entities error; entity fix applied and rerun passed |
| frontend npm run build | Passed; production routes /, /_not-found and /resume generated |
| Frontend Vercel PR checks | Automatic branch preview deployment and preview-feedback checks passed; production was not changed |
| python -m scripts.live_probe | Failed: embedding ClientError; primary Gemini and fallback Gemma GoogleAuthenticationError. Actual vector dimensions and live model tool round trips are **not verified** |
| docker info/run and PostgreSQL version query | Docker engine started; disposable pgvector/pgvector:pg16 on 127.0.0.1:55432, PostgreSQL 16.15; no production DB used |
| git diff --check / staged diff review | Run before commits; generated caches/secrets/local DBs excluded |

Sandbox interpreter-cache, local HTTP threading and localhost resolution constraints initially blocked some commands; escalated checks and explicit IPv4 resolved them. No failed or skipped intermediate run was represented as a passing acceptance test. Root live diagnostics were not run because they require valid provider credentials and some use obsolete call signatures; deterministic regression tests exercise actual supported tools and session APIs instead.

Policy tests verify system instruction placement/tool boundaries, unavailable evidence handling and absence of powerful execution/secret tools. They do not prove real LLM resistance to every prompt injection or semantic retrieval quality. Production WebSocket/Stop behavior, live end-to-end iframe rendering, provider limits and actual Supabase network/RLS operation remain staging gates.

## H. Deployment sequence

1. Retain the current deployed FAISS release.
2. Apply the versioned migration to Supabase as owner; create separate least-privilege login users and TLS connection strings.
3. Configure a valid Google credential and Actions secrets/variables.
4. Run initial ingestion with `--activate-index`; verify counts, dimensions, representative retrieval and a zero-embedding unchanged run.
5. Deploy backend to a staging Python/Streamlit host, entry point app.py; verify liveness/readiness and real chat/contact tools.
6. Verify the existing Next.js iframe, streaming, Stop, session isolation, errors and restarts against staging. Deploy through normal repository policies after acceptance.
7. Merge workflow onto backend master; observe a real manual and scheduled success before retiring the old release. Daily schedule is 03:17 UTC / 08:47 India time.

The complete login provisioning, pooling constraints, model migration, rollback, retention and hosting instructions are in [OPERATIONS.md](OPERATIONS.md). Community Cloud cannot automatically expose the optional health sidecar. Vercel hosts the frontend, not the continuously running Python agent.

## I. Cost and performance

Eliminated corpus embedding and Git cloning from every cold start/restart. Unchanged syncs generate zero document embeddings. Changed files reuse unchanged section vectors; retried publication reuses already cached vectors. Remaining paid calls are query embeddings for searches, newly changed unique chunk embeddings and chat/tool model turns. Embedding 2 list inputs aggregate content, so the adapter intentionally requests each vector separately; successful results are cached immediately.

Limits bound file size/count, chunk input bytes, retrieved context, graph steps, output tokens, session lifetime, concurrency and request frequency. Performance logs measure setup, embedding/search/retrieval, first token and total response durations; sync reports track call counts/retries/duration. Actual p95 latency/cost, corpus quality tuning and Supabase capacity have not been measured against production. Process-local abuse controls do not replace edge limits across multiple replicas. Synchronous transport cancellation is cooperative and can leave an already-sent provider call billable.

## J. Remaining blockers and acceptance status

Locally verified: persistent schema and transactional retrieval on disposable PostgreSQL/pgvector; incremental state transitions; unchanged-run zero embeddings; deletion guards; failure rollback/cache reuse; concurrent-writer exclusion; dimensions/profile isolation; session isolation/expiry/intentional restart loss; six tool graph flow; input/rate/concurrency/deadline/generator cleanup; UI request path with mocked models; safe health/readiness; frontend build/type/lint; credential-pattern scans.

Not verified live: Supabase schema deployment, production login/pooler connectivity, initial production corpus, actual provider embedding length, real search relevance/answer grounding, Gemini/Gemma tool round trips, Google quota behavior, hosted Stop/disconnect behavior, end-to-end deployed iframe, manual/scheduled ingestion, production health/readiness and runtime cold-start measurements.

Required next actions: provide the two Supabase DB URLs/users and apply migration; replace/fix the rejected Google credential; configure Actions secrets/variables; follow staging/rollout acceptance steps. No production migration, deployment, default-branch merge or live ingestion was executed.

## K. Git and review delivery

Backend feature branch: `codex/persistent-rag`, initial implementation commit `a50c747f9585744d6e34a04f1d4d6f1109b58169`, based on default master at e88d560. Frontend feature branch: `codex/reliability-validation`, commit `2692255cd86129a621b055801e80ed38164821f7`, based on main at 9b5011f. Both were pushed successfully. Draft review links: [backend PR #1](https://github.com/deveshyaara/devfolio-agent/pull/1), [frontend PR #7](https://github.com/deveshyaara/devfolio/pull/7). A follow-up backend commit fixes the console test import path; its hash and final CI result are provided in the completion message. Neither protected/default branch was pushed directly; no force-push or unrelated user changes are included. The GitHub connector lacked PR-creation permission; the already-authorized local Git credential created the drafts successfully without exposing credentials.

## Official implementation references

- [Google embeddings: dimensions, input limits and model-specific retrieval formatting](https://ai.google.dev/gemini-api/docs/embeddings).
- [Gemma on the Gemini API](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api) and [Gemma 4 function calling](https://ai.google.dev/gemma/docs/capabilities/text/function-calling-gemma4).
- [LangChain Google chat integration](https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai).
- [Psycopg connection pools](https://www.psycopg.org/psycopg3/docs/advanced/pool.html).
- [Supabase row-level security](https://supabase.com/docs/guides/database/postgres/row-level-security).
- [Streamlit streaming API](https://docs.streamlit.io/develop/api-reference/write-magic/st.write_stream).
