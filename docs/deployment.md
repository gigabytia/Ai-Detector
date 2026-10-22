# Deployment gate after the M13 audit

## Decision

The tested Linux CPU build is suitable for **continued isolated/local validation**, not an unqualified production release. A public or shared-network production deployment is **NO-GO** until the following gates are resolved. Passing tests does not establish absence of defects or confer compliance certification.

1. **Access control:** public operator REST, SSE, WS preview, snapshots and metrics do not implement user authentication/authorization. CORS/origin checks and UUID paths are not authorization. Put every route behind a tested authenticated TLS gateway or implement coordinated app auth, including EventSource/WebSocket/browser downloads. Internal worker routes separately require a unique `WORKER_API_TOKEN`. Never publish the example token.
2. **Target validation:** real RTSP cameras, moving-person accuracy, network outages/reconnect, target GPU/VRAM/CUDA, Windows and the complete container stack have not been certified. Short CPU local-file runs cannot prove 24/7 stability or 10 FPS per camera. Docker was unavailable in the audit environment; static Dockerfile/Compose checks do not replace a clean-volume container smoke test.
3. **Durability and capacity:** bounded RAM outboxes can lose records on crash/full queues; Redis AOF everysec has a loss window; snapshot files and database metadata are not a distributed transaction. Coordinate backups, restore drills, disk alarms, Stream/pending/dead-letter monitoring, and an explicit policy for analytics growth. Observations/track sessions have no automatic retention; uploaded files have no automatic orphan cleanup/quota.
4. **Dependencies/licensing:** review `THIRD_PARTY_NOTICES.md` and the AGPL model/runtime obligations. The Python advisory scan skips local `+cpu` torch/torchvision builds; native codecs and container OS packages need separate scanning. A known braces advisory remains in the npm lint-only chain without a patched release at audit time; do not run tooling against untrusted glob patterns/repositories.

## Local Docker defaults

All Compose-published ports now bind `127.0.0.1`, including frontend 8080, API 8000, worker 8001, PostgreSQL 15432, Redis 6379 and optional MediaMTX ports. Container-to-container networking is unaffected. Remote operator access needs an explicit secure gateway; do not change every bind to `0.0.0.0` as a shortcut. RTSP ingestion is outbound and does not require publishing the camera database or worker port.

Both application images create `/data/snapshots` and `/data/uploads` owned by UID 10001 before switching to that user. Fresh named volumes should inherit those permissions. **Existing volumes/bind mounts do not get repaired by rebuilding an image**: verify ownership/ACLs on the dedicated data directories after backup, and correct them as an operator. Do not give world-write permissions or recursively change unrelated host paths.

Nginx allows 2049 MiB request bodies for the default 2 GiB file limit plus 1 MiB multipart overhead. The API independently enforces both the whole request body (including chunked multipart and ignored parts) and the file limit. If `UPLOAD_MAX_BYTES` is customized, adjust nginx's cap intentionally. Use a bounded temporary filesystem, disk quotas, upload timeouts/rate limits and an access-controlled endpoint. Oversize API responses are JSON 413; a proxy may return its own error page, which the UI handles generically.

## Snapshot burst budget and alerts

The writer accepts at most **32 jobs and 128 MiB conservative raw-frame reservations**, with two encode/write workers. Reservations count each job even if several alarms reference the same underlying array. This is not a total RSS cap: JPEG buffers, temporary encoder allocations, inference, previews and storage caches are additional. Large-resolution/high-person-count bursts can still exceed the budget; alarms remain deliverable without an image.

Monitor worker metrics:

- `ai_detector_snapshot_jobs`, `ai_detector_snapshot_retained_bytes`;
- `ai_detector_snapshot_results{result="written|busy|failed|disabled"}`: cumulative local outcomes since worker start, exposed as gauges, not durability ACKs;
- RAM outbox drops/health and inference errors; Streams/pending/dead letters and filesystem capacity separately.

Alert on an increase in `busy` or `failed`, not just on alarm delivery. A successful local load with every snapshot saved is not a guarantee under arbitrary overload.

## CSV resource limits

The output is still an all-or-nothing attachment, **not a partially streamed HTTP file**. PostgreSQL rows are now read using one server-side cursor in 100-row batches; incremental CSV encoding enforces 50000 rows/20 MiB before the response is published. At most two exports run concurrently **per API process**, including database reading; a busy request gets JSON 503 and can retry. Multiple API processes multiply that limit. Size/row rejection is JSON 422 with no attachment. Keep reverse-proxy timeouts and database resources consistent with these bounded synchronous exports.

## Backup and restore checklist

Stop writes (worker/camera processing and operator updates), drain both Streams or account for pending data, then back up PostgreSQL, snapshot/upload files, Redis persistence/config and the private environment separately. Do not put credentials or production videos into a source archive. Restore into an isolated environment first; compare database row counts and referenced-file SHA-256, then validate API/JPEG/history/CSV and resume writes. A snapshot-only backup is not a database backup, and a database-only backup cannot recreate JPEG files. See the M13 QA restore proof for the scope of the performed local drill.
