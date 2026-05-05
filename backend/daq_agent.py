import json
import random
from datetime import datetime, timezone
from pathlib import Path

from femb_test_schema import FAULT_TO_TEST_ITEMS, TEST_ITEMS

N_CHANNELS = 128   # 8 LArASIC chips × 16 channels each
N_CHIPS = 8
CHANNELS_PER_CHIP = N_CHANNELS // N_CHIPS

_BASELINE = 820.0
_BASELINE_SIGMA = 8.0
_NOISE_RMS = 1.5
_NOISE_RMS_SIGMA = 0.3

_DATA_DIR = Path(__file__).parent / "data" / "daq"

_DEFAULT_CONFIG = {
    "mode": "SE",
    "snc": 1, "snc_label": "200mV",
    "sg0": 0, "sg1": 0, "gain_label": "14mV/fC",
    "st0": 1, "st1": 1, "peaking_label": "2us",
    "dac": "0x00",
}

_DEFAULT_FEMB_SERIAL = "IO-1865-1L_00042"


def _faults_by_granularity(gran: str) -> list[str]:
    seen: dict[str, None] = {}
    for spec in TEST_ITEMS.values():
        if spec["granularity"] == gran:
            for f in spec["fault_types"]:
                seen[f] = None
    return list(seen)

_CHANNEL_FAULTS = _faults_by_granularity("channel")
_CHIP_FAULTS    = _faults_by_granularity("chip")
_BOARD_FAULTS   = _faults_by_granularity("board")


def _chip_of(ch: int) -> int:
    return ch // CHANNELS_PER_CHIP


def _make_channel(ch: int, fault_kind: str | None) -> dict:
    pedestal = _BASELINE + random.gauss(0, _BASELINE_SIGMA)
    rms = max(0.05, _NOISE_RMS + random.gauss(0, _NOISE_RMS_SIGMA))

    if fault_kind == "high_noise":
        rms = _NOISE_RMS * random.uniform(4.0, 8.0)
    elif fault_kind == "dead_channel":
        pedestal = 0.0
        rms = 0.0
    elif fault_kind == "leakage_high":
        pedestal += random.uniform(30, 60)
    elif fault_kind == "gain_error":
        rms = max(0.05, _NOISE_RMS * random.uniform(0.5, 0.8))
    elif fault_kind in ("adc_sync_loss", "pll_lock_fail"):
        rms = _NOISE_RMS * random.uniform(10.0, 30.0)
        pedestal = random.uniform(0, 4096)
    # board-level faults don't alter per-channel waveform values

    return {
        "channel": ch,
        "chip": _chip_of(ch),
        "pedestal": round(pedestal, 2),
        "rms": round(rms, 3),
        "fault_kind": fault_kind,
    }


def generate_ce_agent_data(
    inject_faults: bool = True,
    slot: int = 0,
    femb_serial: str = _DEFAULT_FEMB_SERIAL,
    config: dict | None = None,
    num_samples: int = 10,
    operator: str = "",
    env: str = "RT",
) -> dict:
    """Return a CE_Agent-format QC dataset for one FEMB slot (no I/O)."""
    if config is None:
        config = _DEFAULT_CONFIG.copy()

    channel_fault_map: dict[int, str] = {}
    chip_fault_map: dict[int, str] = {}
    board_faults: list[str] = []

    if inject_faults:
        if random.random() < 0.25:
            board_faults.append(random.choice(_BOARD_FAULTS))

        n_chip_faults = random.choices([0, 1, 2], weights=[0.6, 0.3, 0.1])[0]
        for chip in random.sample(range(N_CHIPS), min(n_chip_faults, N_CHIPS)):
            chip_fault_map[chip] = random.choice(_CHIP_FAULTS)

        n_ch_faults = random.randint(0, 6)
        for ch in random.sample(range(N_CHANNELS), n_ch_faults):
            channel_fault_map[ch] = random.choice(_CHANNEL_FAULTS)

    channels = []
    for ch in range(N_CHANNELS):
        fault = channel_fault_map.get(ch) or chip_fault_map.get(_chip_of(ch))
        channels.append(_make_channel(ch, fault))

    fault_test_items: set[int] = set()
    for fault in board_faults:
        fault_test_items.update(FAULT_TO_TEST_ITEMS.get(fault, []))
    for fault in chip_fault_map.values():
        fault_test_items.update(FAULT_TO_TEST_ITEMS.get(fault, []))
    for fault in channel_fault_map.values():
        fault_test_items.update(FAULT_TO_TEST_ITEMS.get(fault, []))

    all_test_items = set(TEST_ITEMS.keys())
    config_label = f"{config['snc_label']}_{config['gain_label']}_{config['peaking_label']}"

    return {
        "slot": slot,
        "femb_serial": femb_serial,
        "config": config,
        "config_label": config_label,
        "num_samples": num_samples,
        "operator": operator,
        "env": env,
        "channels": channels,
        "channel_faults": {str(k): v for k, v in channel_fault_map.items()},
        "chip_faults": {str(k): v for k, v in chip_fault_map.items()},
        "board_faults": board_faults,
        "fault_test_items": sorted(fault_test_items),
        "pass_test_items": sorted(all_test_items - fault_test_items),
        "slot_passed": len(fault_test_items) == 0,
    }


def save_ce_agent_run(data: dict) -> Path:
    """Write CE_Agent directory layout and return the run directory path."""
    base = _DATA_DIR / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    run_dir, n = base, 0
    while run_dir.exists():
        n += 1
        run_dir = base.parent / f"{base.name}_{n}"
    run_dir.mkdir(parents=True)

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    slot, serial = data["slot"], data["femb_serial"]

    manifest = {
        "created_at": now_str,
        "pc_data_dir": str(run_dir),
        "fembs": [slot],
        "operator": data["operator"],
        "env": data["env"],
        "acquisitions": [{
            "file": f"RMS_SE_{data['config_label'].replace('/', '_').replace(' ', '')}_0x00.bin",
            "config": data["config"],
            "num_samples": data["num_samples"],
            "timestamp": now_str,
        }],
    }
    (run_dir / "acquisition_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    analysis = {
        "femb_serial": serial,
        "slot": slot,
        "config_label": data["config_label"],
        "n_channels": N_CHANNELS,
        "channels": data["channels"],
        "channel_faults": data["channel_faults"],
        "chip_faults": data["chip_faults"],
        "board_faults": data["board_faults"],
        "slot_passed": data["slot_passed"],
        "fault_test_items": data["fault_test_items"],
        "pass_test_items": data["pass_test_items"],
    }
    (run_dir / "channel_analysis.json").write_text(json.dumps(analysis, indent=2), encoding="utf-8")

    for t in data["pass_test_items"]:
        (run_dir / f"FEMB_{serial}_P_S{slot}_t{t}.md").write_text(
            f"# PASS — slot {slot}, test item t{t}\n\nFEMB: {serial}\nConfig: {data['config_label']}\n",
            encoding="utf-8",
        )
    for t in data["fault_test_items"]:
        (run_dir / f"FEMB_{serial}_F_S{slot}_t{t}.md").write_text(
            f"# FAULT — slot {slot}, test item t{t}\n\nFEMB: {serial}\nConfig: {data['config_label']}\n",
            encoding="utf-8",
        )

    return run_dir
