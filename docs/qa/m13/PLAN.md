# Final audit plan

Scope: local Linux CPU environment; no physical cameras, target host access, GPU or Docker daemon. Do not call a local file load RTSP certification.

1. Baseline lint/types/unit/integration/frontend/build, isolated Redis *instances* and PostgreSQL databases.
2. Source review: input validation, secrets and storage, transactions/concurrency, event/analytics delivery/recovery, capture/scheduler lifecycle, limits, HTTP/WS/SSE, migrations/contracts/dependencies, deployment and licenses.
3. Reproduce defects, fix and add regression tests.
4. CPU real YOLO full pipeline on 4 and 8 local video streams, 15 s warm + 180 s (4 cameras) / 300 s (8 cameras), WS previews/SSE/CSV/snapshots/analytics; separate PostgreSQL and Redis outages/recovery, graceful stop. Raw data immutable. No throughput target pass claim. First partial run superseded after security-dependency upgrade; retained separately.
5. Repeat all automated gates after final changes. Empty DB/migration reversibility in test-only DB, OpenAPI/lock parity, dependency advisory scans, scoped secret scan, backup+restore drill. Browser smoke if available.
6. Document evidence, severity, residual/unverified items and deployment GO/NO-GO, commit and publish a complete Git archive with weights, verify downloaded hash.

Browser retries: Vite was initially launched from the wrong cwd, then dev-only Vue devtools failed when all Storage calls were blocked. The accepted smoke uses the production build served by vite preview with the same API/WS proxies. Layout/DOM and pageerror checks passed; screenshot view helper was unavailable, so no human/expert image review is claimed.

A preview-enabled attempt stopped after 75 s at an idle HTTP keep-alive boundary: httpx RemoteProtocolError, while API/worker stayed alive, with no matching endpoint error. Preserved raw/logs. Final REST probe client uses keepalive_expiry=2 s, below uvicorn idle5 s, avoiding idle-connection reuse at the exact5 s polling interval. This is not a server restart or a throughput pass for the aborted attempt.
