# ADR-040 — Audit fixes at resource and concurrency boundaries

Status: accepted for the locally tested M13 build; deployment gates remain in `docs/deployment.md`.

## Evidence

Parallel camera creates exceeded a configured limit of three (eight successes). The original quota count and insert were independent transactions. A full local CPU pipeline run also saved 1008 snapshots for 3552 events: capacity-four snapshot jobs silently fell back during multi-person alarm bursts (warnings existed, but no snapshot metrics). CSV byte checks happened after materializing all selected rows; the HTTP upload file cap happened after multipart spooling. Docker images did not prepare a writable snapshot directory and nginx's default request size was inconsistent with video uploads.

## Decisions

- Serialize API camera count+insert using the PostgreSQL transaction advisory lock `(41438, 1)`; release at commit/rollback. The lock covers the empty table and multiple API processes. All supported create paths must use it. Name uniqueness remains a database constraint. Direct SQL writers are not covered.
- Guard POST upload envelope size before multipart parsing (file cap plus 1 MiB); count streamed chunks without relying on Content-Length. Raise the parser's multipart exception so partial spool files are closed, then expose JSON 413. The existing file-specific storage cap remains independent.
- Retain all-or-nothing CSV output, a single SELECT snapshot and safe quoting. Read using a server cursor in batches of 100; encode incrementally off-loop with caps across batches. Two export slots per API lifespan/process; excess concurrency gets 503. Cursor/slot cleanup must run on cap/error/cancellation.
- Snapshot burst capacity 32 jobs, raw-frame reservations at most128 MiB, two workers. Byte accounting is conservative per job and does not claim total RSS. Add local job/byte/outcome gauges. Alarm delivery takes priority on failure; images remain optional under overload.
- Loopback Docker publications; prepare UID10001 storage paths; align proxy upload cap. Existing volumes need operator checks. No false claim of executed containers or application auth.
- Security-floor vulnerable transitive dependencies; report audit skips and unresolved lint-only advisories rather than claiming universal zero vulnerabilities.

## Validation

See `docs/qa/m13/README.md`, raw evidence and `docs/AUDIT_REPORT.md`. A first load generator incorrectly treated the structured preview packet as a bare JPEG; its results are preliminary/no-preview, not accepted preview evidence. The verified run decodes the length-prefixed JSON+JPEG protocol, requires packets from every camera and fails on consumer-task errors. Short static-file runs do not establish real-camera accuracy or 24/7 operation.
