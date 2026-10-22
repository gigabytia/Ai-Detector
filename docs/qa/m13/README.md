# M13 evidence

Read ../../AUDIT_REPORT.md first. Accepted proof: full-pipeline-proof.json; immutable raw/load-4.jsonl and load-8.jsonl, events.csv and sse-events.json. One row = ~5s probe sample, not a frame. Profiler output/warnings and evidence.json document grain, null/constant-field interpretation and independent numeric checks. No before/after performance claim.

265 Python unit/46 isolated PG-Valkey integration/134 frontend PASS; supporting logs and dependency scans retained. Migration roundtrip only in a new empty test DB. OpenAPI parity log. Browser production28 layouts/download/retry/storage fallback; screenshots saved but no expert visual review (helper unavailable).

Sandbox scenario files end in .txt intentionally: they contain environment-specific isolated ports/DB names and destructive test-only outage/restore actions. They are evidence, not a portable production runbook. private runtime/env.json is deliberately absent; generate a fresh WORKER_API_TOKEN for reruns. Never run these outage/SQL scripts against a user database or shared Redis instance.

Preliminary proof is explicitly not accepted preview validation and demonstrates the old snapshot gap; PLAN records retries. Accepted pipeline uses correct 4-byte header length + JSON + JPEG framing. Uploaded video/weights source provenance recorded; runtime video omitted. Test scripts require equivalent QA environment/fixtures, not just blind copy/paste.

Git archive verification and remotely downloaded ZIP SHA are external to the commit to avoid recursive hashes. Latest handoff page records HEAD and archive hash. Local cold dump and image copies are not source artifacts; restore-proof records count/hash comparisons only.

Profile interpretation: ISO timestamps validated after UTC parsing. CSV empty line_id is expected for zone-only scenarios; empty note/ack/false-positive timestamps and constant NEW are expected with no operator edits. track_id is an identifier, not additive; processed_total is cumulative, not a daily amount. Profiler sum/day hints are inapplicable and rejected; rates use counter differences and monotonic elapsed time. Nested CPU/RSS/status fields remain JSON in raw and are unpacked by the analysis script. No null is imputed as zero. source_diff_sha256 describes the tracked diff at run start; final tested-source-manifest hashes establish unchanged runtime source despite later documentation/evidence additions.
