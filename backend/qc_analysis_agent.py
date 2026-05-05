# Real LArASIC thresholds (200 mV baseline mode, SE configuration)
_EXPECTED_BASELINE = 820.0
_BASELINE_TOLERANCE = 100.0
_NOISE_RMS_MAX_FACTOR = 2.5   # flag if channel RMS > 2.5× median of passing channels
_DEAD_RMS_MAX = 0.1            # effectively zero noise → dead or sync-lost channel


def flag_anomalous_channels(channels: list[dict]) -> list[dict]:
    """
    Given a list of pre-computed per-channel dicts, return only anomalous channels
    with an 'issues' list using the fault vocabulary from femb_test_schema.

    Reads the pre-computed fault_kind when available (mock data). When real hardware
    data arrives without fault_kind, falls back to threshold-based detection.
    """
    good_rms = [
        ch["rms"] for ch in channels
        if ch["rms"] > _DEAD_RMS_MAX
        and abs(ch["pedestal"] - _EXPECTED_BASELINE) <= _BASELINE_TOLERANCE
    ]
    median_rms = sorted(good_rms)[len(good_rms) // 2] if good_rms else 1.5
    rms_threshold = median_rms * _NOISE_RMS_MAX_FACTOR

    anomalies = []
    for ch in channels:
        fault_kind = ch.get("fault_kind")

        if fault_kind:
            issues = [fault_kind]
        else:
            issues = []
            if ch["rms"] <= _DEAD_RMS_MAX:
                issues.append("dead_channel")
            elif ch["rms"] > rms_threshold:
                issues.append("high_noise")
            if abs(ch["pedestal"] - _EXPECTED_BASELINE) > _BASELINE_TOLERANCE:
                if "dead_channel" not in issues:
                    issues.append("leakage_high")

        if issues:
            anomalies.append({
                "channel": ch["channel"],
                "chip": ch["chip"],
                "baseline": ch["pedestal"],
                "noise_rms": ch["rms"],
                "issues": issues,
            })

    return anomalies
