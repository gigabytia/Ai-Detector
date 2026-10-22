# Third-party notices

This inventory does not choose a license for the project's original code and is not legal advice. Review the actual licenses and the intended distribution/network-service model before deployment or redistribution.

## Person detector and model weights

- Ultralytics YOLO runtime and `yolo26n-coco` weights: **AGPL-3.0**, as recorded in the model manifest and upstream package. The unmodified runtime license text is copied to `docs/licenses/ultralytics-AGPL-3.0.txt`.
- Weight source: https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.pt
- Weight SHA-256: `9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef`.
- Upstream licensing: https://www.ultralytics.com/license . Any alternative commercial licensing is a separate agreement, not granted by this repository.
- This archive intentionally includes weights but not installed dependency packages. Model license obligations and any corresponding-source obligations still need review; a notice alone is not a compliance determination.

## Other dependencies

The exact resolved Python and JavaScript versions are in `uv.lock` and `frontend/package-lock.json`. PyTorch/torchvision, OpenCV/FFmpeg, trackers/supervision, Vue, ECharts, fonts and every transitive dependency retain their upstream licenses. The audit's package inventory is diagnostic, not a complete legal SBOM or native-code vulnerability assessment. Container/base-image licenses and advisories were not scanned in the sandbox because Docker is unavailable.
