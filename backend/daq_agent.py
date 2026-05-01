import json
import random
from datetime import datetime, timezone
from pathlib import Path

import h5py

from qc_analysis_agent import run_qc_analysis_agent

N_CHANNELS = 32
_BASELINE = 2048  # 12-bit ADC midpoint
_NOISE_SIGMA = 15.0
_DATA_DIR = Path(__file__).parent / "data" / "daq"


def _inject_anomaly(samples: list[int], baseline: float, kind: str) -> list[int]:
    if kind == "baseline_drift":
        shift = random.choice([-1, 1]) * random.randint(50, 120)
        return [s + shift for s in samples]
    if kind == "high_noise":
        return [int(baseline + random.gauss(0, _NOISE_SIGMA * 4)) for _ in samples]
    if kind == "stuck_bit":
        stuck_val = int(baseline)
        cutoff = int(len(samples) * 0.6)
        return [stuck_val] * cutoff + samples[cutoff:]
    if kind == "shape_anomaly":
        burst_start = random.randint(0, len(samples) - 200)
        burst = [int(baseline + random.choice([-1, 1]) * _NOISE_SIGMA * 8)] * 200
        return samples[:burst_start] + burst + samples[burst_start + 200:]
    return samples


def generate_waveform_data(n_samples: int = 2300) -> dict:
    anomaly_kinds = ["baseline_drift", "high_noise", "stuck_bit", "shape_anomaly"]
    n_anomalous = random.randint(2, 5)
    anomalous_channels = random.sample(range(N_CHANNELS), n_anomalous)
    anomaly_map = {ch: random.choice(anomaly_kinds) for ch in anomalous_channels}

    channels = []
    for ch in range(N_CHANNELS):
        baseline = _BASELINE + random.gauss(0, 5)
        samples = [int(baseline + random.gauss(0, _NOISE_SIGMA)) for _ in range(n_samples)]
        if ch in anomaly_map:
            samples = _inject_anomaly(samples, baseline, anomaly_map[ch])
        channels.append({"channel": ch, "baseline": round(baseline, 1), "samples": samples})
    return {"n_channels": N_CHANNELS, "n_samples": n_samples, "channels": channels}


def save_waveforms(waveform: dict) -> Path:
    run_dir = _DATA_DIR / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    with h5py.File(run_dir / "waveforms.h5", "w") as f:
        for ch_data in waveform["channels"]:
            f.create_dataset(f"channel_{ch_data['channel']:02d}", data=ch_data["samples"])
    return run_dir


async def run_daq_agent(n_samples: int = 2300):
    yield f"data: {json.dumps({'type': 'token', 'text': '\n\n*DAQ Agent: Acquiring waveform data...*\n\n'})}\n\n"

    waveform = generate_waveform_data(n_samples)
    run_dir = save_waveforms(waveform)

    summary = {
        "n_channels": waveform["n_channels"],
        "n_samples": waveform["n_samples"],
        "channel_baselines": [ch["baseline"] for ch in waveform["channels"]],
        "run_dir": str(run_dir),
    }
    yield f"data: {json.dumps({'type': 'tool_result', 'tool': 'daq_acquire', 'result': summary})}\n\n"
    yield f"data: {json.dumps({'type': 'token', 'text': f'Acquired {N_CHANNELS}-channel ADC waveform ({n_samples} samples/channel). Saved to `{run_dir.name}`. Forwarding to QC Analysis Agent.\n'})}\n\n"

    async for event in run_qc_analysis_agent(run_dir):
        yield event
