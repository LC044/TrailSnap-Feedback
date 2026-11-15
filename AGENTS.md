# Agent instructions

This repository owns the TrailSnap feedback platform. The photo application lives in `LC044/TrailSnap`.

- Read `README.md` before changes. Preserve database migrations and the existing MCP delivery protocol.
- Run relevant checks through `tests/scripts/run-tests.ps1`. Test configuration is `tests/.env.test` (template: `tests/.env.test.example`; CI: `tests/.env.test.ci`).
- New HTTP APIs return `{code, msg, data}`. Authorize every conversation and subscription on the server; public requirement visibility never grants private conversation access.
- Vue components use `<script setup lang="ts">`, Pinia for shared state, and `web/src/api/*` for HTTP. Reuse `--rp-*` style tokens. Check narrow screens and loading/error states.
- Use the official DSH SDK in the isolated Docker runner. Native filesystem/search/shell tools may operate on public release source, official docs and disposable workspaces. Never run these tools in the platform API/worker container or give them production volumes, real provider/SMTP/GitHub credentials, Docker sockets or host mounts. Keep role and spending controls; do not load user profiles or telemetry. User instructions explicitly authorize this native-tool architecture.
- Never publish `.env`, SQLite files, uploads, private conversation contents, edit receipts or tokens.
- Do not create or change TrailSnap GitHub Issues directly; use the requirement platform/MCP. Do not merge or deploy without user authorization.
