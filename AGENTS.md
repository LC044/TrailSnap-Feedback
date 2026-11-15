# Agent instructions

This repository owns the TrailSnap feedback platform. The photo application lives in `LC044/TrailSnap`.

- Read `README.md` before changes. Preserve database migrations and the existing MCP delivery protocol.
- Run relevant checks through `tests/scripts/run-tests.ps1`. Test configuration is `tests/.env.test` (template: `tests/.env.test.example`; CI: `tests/.env.test.ci`).
- New HTTP APIs return `{code, msg, data}`. Authorize every conversation and subscription on the server; public requirement visibility never grants private conversation access.
- Vue components use `<script setup lang="ts">`, Pinia for shared state, and `web/src/api/*` for HTTP. Reuse `--rp-*` style tokens. Check narrow screens and loading/error states.
- Use the official DSH SDK. Public conversations may use only the application-owned readonly knowledge plugin (fixed latest release source and official documentation). Never enable shell, generic filesystem/URL tools, third-party plugins, user profiles or telemetry. Privileged coding must run in an isolated environment and must not receive platform credentials or production data.
- Never publish `.env`, SQLite files, uploads, private conversation contents, edit receipts or tokens.
- Do not create or change TrailSnap GitHub Issues directly; use the requirement platform/MCP. Do not merge or deploy without user authorization.
