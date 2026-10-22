# M15 — retained CPU/CUDA dependency profiles

## Scope and acceptance

Base: genuine M14 ca55552 with full Git history/model. User reported Windows RTX3060 12GiB, NVIDIA driver616.92 and torch2.14.1+cpu/torch.version.cuda None/is_available False. Those reports explain the CPU-only installation; no remote access to that hardware was available. M15 chooses official PyTorch cu130 wheels with the same base torch2.14.1/torchvision0.29.1 versions. Do not interpret this as a measured RTX3060 throughput/driver certification.

Root uv>=0.13.5, default dev+cpu groups, mutually exclusive CPU/CUDA groups and conditional explicit indexes. The versioned lock retains every M14 package version and adds21 CUDA alternatives/dependencies. No pip overlay, external runtime lock rewrite or latest upgrade. Windows cp312 x64 CUDA wheels and hashes exist in the resolved lock. Plain uv defaults to CPU. Launcher explicitly selects the saved group and overrides INFERENCE_DEVICE only in its own app children; existing .env stays byte-for-byte unchanged.

Profile persists only after successful setup or all app readiness, in ignored .runtime-profile.json. No profile means CPU; corrupt/non-string profiles fail with an explicit choice instruction. GPU failure never silently switches to CPU. --skip-install still runs exact version/build/runtime, availability and kernel preflight. CPU rollback reinstalls CPU packages. Windows .cmd entrypoint stays unchanged/CRLF.

## Accepted checks

- Final make check: **305 Python unit**, **134 frontend** (24 files), **7 Node toolchain** tests; Ruff184 files, strict mypy182 files, ESLint/Prettier/vue-tsc/production build. Python3.12.15, uv0.13.5, Node24.15.0/npm11.11.0. CUDA routing tests use explicit fakes, not physical GPU kernels.
- **46 real PostgreSQL/Valkey integration** tests passed on isolated DB15543 and separate Redis16592, not the live DB/instance. Integration collection occurred before the last additional unit-only profile tests; the tested integration source did not change. No new migration; existing b6b7cfcd87c5. OpenAPI generated JSON matches versioned frontend contract.
- Real fresh CPU sync; actual CPU matmul and torchvision NMS passed. Full launcher install/setup (uv frozen + npm ci), local PG/Redis checks and existing-camera preservation passed. Fresh native Linux live API/worker/UI readiness, DEMO zones/events/JPEG, .env hash unchanged, saved CPU profile, Ctrl+C/owned ports closed, immediate second setup without duplicate seeding passed. This is a CPU/mock startup regression, not a new real GPU/file benchmark.
- CUDA profile **actually installed in a separate Linux environment**; torch/torchvision cu130 imported. No NVIDIA GPU exists here. Actual CUDA guard and subprocess launcher exited1 with the no-usable-GPU diagnostic, no CPU fallback/app startup, prior CPU choice and existing .env preserved. This is a negative test, not successful CUDA execution.
- The separate installed CUDA environment was then synced back to CPU;21 GPU packages removed, CPU pair installed, actual CPU matmul/NMS passed. Explicit both-group request is rejected by uv; default sync remains CPU/no changes.
- Windows CUDA sync is a **dry run**, selecting torch2.14.1+cu130/torchvision0.29.1+cu130. Docker worker CPU sync is also only a **dry-run plan**. Investigation found that --package worker without explicit root cpu group would pick PyPI Linux CUDA; both worker Dockerfile sync lines now explicitly --group cpu, validated by plan and unit test. API/worker Dockerfile uv pins raised to0.13.5; no Docker build/run claimed.
- npm clean ci no ERESOLVE, production audit0. Known four high dev-only advisory nodes remain open; no breaking audit fix. ECharts chunk-size and Starlette deprecation warnings remain non-failing. No new broad Python/CUDA/OS CVE scan or license certification is claimed.

## Limits / reproduction

**Not executed:** native Windows/.cmd/driver/DLL behavior, successful physical NVIDIA GPU matmul/NMS/YOLO, GPU video decoding, Docker Desktop/GPU/container runtime, real RTSP/GPU accuracy/capacity/24h soak. The user's RTX3060 acceptance requires `start.cmd --profile cuda`, Accelerator PASS/READY and an actual YOLO file/RTSP camera (not just mock DEMO). See GPU_WINDOWS.md. No FP16/TensorRT/NVDEC or promised FPS improvement. M13 auth/durability/capacity/licensing/production NO-GO gates stay open; M13 long-run/browser/backup QA is historical and was not rerun as GPU evidence.

Logs and sandbox-only harnesses below are curated and contain no user's .env/data. Harness .txt files use isolated test paths/ports, not production runbooks. Test .env, .runtime-profile.json, .venv/node_modules, DB/Redis files and runtime uploads/JPEG/log directories are excluded from archive. manifest.json hashes every file here except itself; tested-source-hashes.json records final changed source/docs. Archive/remote-copy hashes live outside this folder on the handoff page to avoid recursive hashes.
