# Live setup verification — 2026-10-18

Both original implementation PRs are merged: backend #1 and frontend #7.
This record supplements the pre-deployment findings in ENGINEERING_REPORT.md.

## Supabase and provider checks

- Applied the persistent knowledge migration to the devfolio-agent project.
- Created separate restricted reader and ingestion logins, using the IPv4 session pooler with client TLS verified through Psycopg.
- Reader can SELECT and search but cannot INSERT; ingestion has writer access. Neither login is a superuser or bypasses RLS. All seven private tables have RLS enabled.
- Supabase security advisor reported no findings. Performance advisor noted unindexed foreign keys and initially unused indexes; no additional indexes were added without workload evidence.
- Live Google probes passed: 768-dimensional gemini-embedding-2, and native tool call/result round trips with gemini-3.5-flash and gemma-4-26b-a4b-it. Checks were repeated successfully after credential rotation.
- The first ingestion rejected three READMEs containing example database connection strings. Normalization now removes the complete userinfo from narrowly recognized password placeholders before credential screening. Unrecognized passwords and other credential patterns still reject the document; regression coverage verifies both behaviors.
- Successful initial corpus: 9 repositories, 9 files, 199 chunks. Initial attempts made 127 + 72 successful embedding requests; durable cache reuse avoided repeating the first 127.
- Unchanged follow-up run: success, 9 unchanged files, 199 reused chunks, zero embedding requests/failures/retries, 12.625 seconds.
- Runtime reader readiness passed. A representative WealthWise query returned two README sources with cosine scores 0.730 and 0.707.

## Hosting and automation

GitHub Actions has encrypted GOOGLE_API_KEY and SUPABASE_SYNC_DB_URL secrets, with account/topic/profile configuration variables. The account repository variable is PORTFOLIO_GITHUB_USERNAME: GitHub reserves configuration variable names beginning with GITHUB_. The workflow maps this allowed variable to the application's GITHUB_USERNAME environment variable.

Streamlit runtime settings include the reader URL and Google key, excluding writer credentials. The hosted app started from master on Python 3.12.7 and answered a real project-list question with repository links. Hosted startup logged runtime initialization without corpus ingestion. Hosting uses uv.lock automatically.

A browser input error echoed credentials into the private tool transcript. The reader password was rotated; the owner replaced the Google key. Updated values are loaded from ignored local files and never included in this record or Git history.

## Validation and remaining acceptance

After the ingestion/workflow fixes: 68 offline tests passed, two PostgreSQL tests deselected locally (already exercised against disposable pgvector during implementation). Ruff checks passed. The first sandboxed test attempt stalled on localhost network restrictions; the unsandboxed rerun passed.

The new workflow must pass a manual GitHub run after merge. A future daily scheduled run, multi-user load and hosted Stop/disconnect behavior remain separate observations; they cannot be inferred from a successful manual run. No live public database deletion or destructive acceptance test was performed.

See [operations](OPERATIONS.md) for deployment settings and rollback.
