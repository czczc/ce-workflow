import math
from collections import Counter

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
