# M14 — reproducible local startup

Base: complete M13 `c76adca`, real Git history and model weights preserved. Scope: fixes for the reported npm peer conflict and missing Redis during native Windows development. This is not a repeat of all M13 load/accuracy/production acceptance experiments.

## Changes

- Keep the already compatible M13 resolved lint trio, but pin declarations exactly: Vue TS config14.9.0 / ESLint10.12.0 / Vue plugin10.11.1. Config14.0.1 from the error log was a different incompatible tree. Do not downgrade the tested modern trio to deprecated ESLint9.
- Coherent lock + npm ci; engine-strict, no peer/force bypass; Node/preinstall guard detects wrong pins or mismatched lock declarations/resolutions. No blanket install-script approval.
- IPv4 Redis URL in example/API/worker defaults removes localhost address ambiguity; no claim that IPv6 alone caused the user's outage. More importantly, startup actually starts local Docker PG/Redis and checks Redis PING/PG SELECT1 before migrations/app readiness.
- `start.cmd` invokes the standard-library Python launcher through uv. It preserves existing .env byte-for-byte, creates only missing config with a random token, installs frozen deps, checks infrastructure/model/migrations, optionally seeds only an empty camera table, waits API/worker/frontend readiness and records separate logs. Ctrl+C stops only its own process groups/trees, not Docker volumes or unrelated processes.
- A local port probe was changed from bind to connect after a real rerun exposed TIME_WAIT false positives; regression included. A listening occupied port still fails closed without killing its owner.

## Automated gates

- 281 Python unit (265 existing +16 new launcher/preflight), 46 isolated PostgreSQL/Valkey integration, 134 frontend Vitest, 7 Node toolchain guard tests: PASS.
- Ruff format182 files; strict mypy180 files including scripts; ESLint/Prettier/vue-tsc/production build: PASS. `make check` now includes toolchain tests and script type checking.
- Full uv no-project launcher setup with installs (native local infra) also passed; Windows wrapper bytes are CRLF. Fresh npm ci on supported Node24.15.0/npm11.11.0: no ERESOLVE, checked installed trio; no force/legacy flags. Default Node24.14.1 intentionally rejected with a clear supported-version message. uv frozen lock check PASS; resolved Python dependencies unchanged from M13.
- npm production audit0; four high dev-only advisory nodes remain known/open, not silently fixed by a breaking downgrade. ECharts size warning/Starlette deprecation remain non-failing, as documented in M13.

## Live local test (accepted proof: startup-proof.json)

Linux CPU host; native isolated PostgreSQL17 on15542 and Valkey on16589, not Docker. Started launcher from a different cwd, using a private custom .env and already frozen installed deps (`--no-infra --skip-install`). Fresh DB migrated, two explicitly DEMO cameras/zones seeded; API/worker/UI readiness passed, events and JPEG API passed. Ctrl+C returned0; all owned ports18140/18141/5173 closed. Immediate second setup preserved camera records/zones and skipped seeding. Existing .env SHA unchanged. Separate real stopped-Redis preflight failed closed with sanitized diagnostic. Integration tests used a different database and a different Redis instance16590 to avoid Pub/Sub cross-talk.

The first live attempt already reached READY/events/JPEG/clean shutdown but its second setup failed due to the bind/TIME_WAIT issue. It is not the accepted final proof; a fresh DB repeat after the fix passed. Evidence preserves the preliminary failure separately.

**Not executed:** native Windows/.cmd/CTRL_BREAK_EVENT/taskkill behavior on an actual Windows OS, Docker Desktop/Compose container startup, real RTSP/GPU/24h soak. Windows cleanup command selection is unit-tested using fakes, and Docker command order/health gate is unit-tested, not a container execution claim. M13 production NO-GO/auth/durability/capacity/licensing gates remain open. `--no-infra` never substitutes a fake Redis in the live check.

## Files/privacy/reproduction

See START_WINDOWS.md for the user workflow and UPDATE_MILESTONE_14.md for backups. Runtime .env, DB/Redis persistence, service log directories, uploaded videos and snapshot files are excluded from source archives. This QA folder contains curated command logs/proofs, not user credentials or their private data. Sandbox live test script is `.txt` evidence with environment-specific ports; it is not a production runbook.

`manifest.json` hashes every QA file except itself. Archive/remote-download hashes are recorded externally on the handoff page to avoid recursive hashes. M13 report remains historical; M14 does not claim its three-/five-minute pipeline run was repeated.
