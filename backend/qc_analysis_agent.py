import json
import math
from collections import Counter
from pathlib import Path

import h5py

from catalog_agent import run_catalog_agent
from diagnostic_agent import run_diagnostic_agent

_EXPECTED_BASELINE = 2048
_EXPECTED_NOISE_SIGMA = 15.0
_BASELINE_TOLERANCE = 30      # ±30 ADC counts from midpoint
_NOISE_WARN_FACTOR = 2.0      # flag if RMS > 2× expected sigma
_STUCK_THRESHOLD = 0.5        # fraction of identical samples → stuck bit
_OUTLIER_SIGMA = 5.0          # outlier threshold in units of expected sigma
_OUTLIER_FRAC_LIMIT = 0.05    # flag if > 5% of samples are outliers


def _check_baseline(baseline: float) -> dict:
    deviation = abs(baseline - _EXPECTED_BASELINE)
    return {"ok": deviation <= _BASELINE_TOLERANCE, "baseline": round(baseline, 1), "deviation": round(deviation, 1)}


def _check_noise_rms(samples: list[int], baseline: float) -> dict:
    rms = math.sqrt(sum((s - baseline) ** 2 for s in samples) / len(samples))
    return {"ok": rms <= _EXPECTED_NOISE_SIGMA * _NOISE_WARN_FACTOR, "rms": round(rms, 2)}


def _check_signal_shape(samples: list[int], baseline: float) -> dict:
    n = len(samples)
    most_common_count = Counter(samples).most_common(1)[0][1]
    stuck = most_common_count / n > _STUCK_THRESHOLD
    outlier_count = sum(1 for s in samples if abs(s - baseline) > _OUTLIER_SIGMA * _EXPECTED_NOISE_SIGMA)
    ok = not stuck and (outlier_count / n < _OUTLIER_FRAC_LIMIT)
    return {"ok": ok, "stuck": stuck, "outlier_fraction": round(outlier_count / n, 4)}


async def run_qc_analysis_agent(run_dir: Path):
    yield f"data: {json.dumps({'type': 'token', 'text': '\n\n*QC Analysis Agent: Analyzing waveforms...*\n\n'})}\n\n"

    channel_results = []
    anomalies = []

    with h5py.File(run_dir / "waveforms.h5", "r") as f:
        for key in sorted(f.keys()):
            ch_idx = int(key.split("_")[1])
            samples = list(f[key][:])
            baseline = sum(samples) / len(samples)

            bl = _check_baseline(baseline)
            nr = _check_noise_rms(samples, baseline)
            ss = _check_signal_shape(samples, baseline)

            issues = []
            if not bl["ok"]:
                issues.append("baseline_drift")
            if not nr["ok"]:
                issues.append("high_noise")
            if ss["stuck"]:
                issues.append("stuck_bit")
            elif not ss["ok"]:
                issues.append("shape_anomaly")

            result = {
                "channel": ch_idx,
                "baseline": bl["baseline"],
                "noise_rms": nr["rms"],
                "outlier_fraction": ss["outlier_fraction"],
                "issues": issues,
            }
            channel_results.append(result)
            if issues:
                anomalies.append(result)

    findings = {
        "run_dir": str(run_dir),
        "n_channels": len(channel_results),
        "n_anomalous": len(anomalies),
        "anomalies": anomalies,
    }
    yield f"data: {json.dumps({'type': 'tool_result', 'tool': 'qc_analysis', 'result': findings})}\n\n"

    if anomalies:
        lines = [f"**QC Analysis complete.** {len(anomalies)}/{len(channel_results)} channels flagged:\n"]
        for a in anomalies:
            lines.append(f"- Channel {a['channel']:02d}: {', '.join(a['issues'])}")
        lines.append("\nForwarding findings to Diagnostic Agent.")
        text = "\n".join(lines) + "\n"
    else:
        text = (
            f"**QC Analysis complete.** All {len(channel_results)} channels passed. "
            "No anomalies detected.\n"
        )

    yield f"data: {json.dumps({'type': 'token', 'text': text})}\n\n"

    if anomalies:
        async for event in run_diagnostic_agent(findings):
            yield event

    async for event in run_catalog_agent(findings):
        yield event
