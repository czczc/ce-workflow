"""
Canonical definition of FEMB QC test items and their fault types.

Shared by the mock data factory (daq_agent.py) and the LLM system prompt
(diagnostic_agent.py). Adding a new test item here automatically propagates
to both the mock and the agent's knowledge.

Granularity levels:
  "channel" — fault affects individual channels independently
  "chip"    — fault affects all 16 channels of one LArASIC chip together
  "board"   — fault affects the whole FEMB (all 128 channels / all chips)
"""

from typing import TypedDict


class FaultSpec(TypedDict):
    description: str           # what the fault means in plain English
    action: str                # recommended operator action


class TestItem(TypedDict):
    name: str
    description: str
    granularity: str           # "channel" | "chip" | "board"
    fault_types: dict[str, FaultSpec]


TEST_ITEMS: dict[int, TestItem] = {
    1: {
        "name": "pwr_consumption",
        "description": "Power consumption per rail (VCD, VFE, VADC) in both SE and differential modes",
        "granularity": "board",
        "fault_types": {
            "overcurrent": {
                "description": "Current draw exceeds rail limit — possible short or damaged component",
                "action": "Power off immediately; inspect FEMB for visible damage or short circuit",
            },
            "undercurrent": {
                "description": "Current draw below expected minimum — possible open circuit or failed power domain",
                "action": "Check connector seating and power cable; inspect solder joints on power rails",
            },
        },
    },
    2: {
        "name": "pwr_cycle",
        "description": "Power cycling stability — rails must recover to nominal within spec after each cycle",
        "granularity": "board",
        "fault_types": {
            "power_cycle_fail": {
                "description": "Rail voltages do not recover to nominal after power cycle",
                "action": "Retry power cycle; if persistent, inspect decoupling capacitors and voltage regulators",
            },
        },
    },
    3: {
        "name": "leakage_current",
        "description": "Per-channel leakage current measured via cold pulse injection",
        "granularity": "channel",
        "fault_types": {
            "leakage_high": {
                "description": "Channel leakage current exceeds 5 nA spec",
                "action": "Identify affected chip/channel; likely damaged input protection diode or contamination",
            },
        },
    },
    4: {
        "name": "check_pulse",
        "description": "Warm check pulse — verifies gain and peaking time response of each LArASIC channel",
        "granularity": "channel",
        "fault_types": {
            "dead_channel": {
                "description": "No pulse response detected — channel is non-responsive",
                "action": "Check wire-bond continuity; if entire chip is dead, suspect COLDATA I2C config failure",
            },
            "gain_error": {
                "description": "Pulse amplitude outside ±20% of expected value for the configured gain setting",
                "action": "Re-run wib_fe_configure.py for the affected chip; if persistent, LArASIC may need replacement",
            },
        },
    },
    5: {
        "name": "rms_noise",
        "description": "Per-channel RMS noise in ADC counts — pedestal run with no pulse injection",
        "granularity": "channel",
        "fault_types": {
            "high_noise": {
                "description": "Channel RMS exceeds 2.5× median of all 128 channels",
                "action": "Check cable shielding and ground connections; verify ADC bias settings via wib_cfgs",
            },
            "dead_channel": {
                "description": "Channel RMS effectively zero — no ADC activity",
                "action": "Check wire-bond continuity; re-run wib_adc_autocali.py for the affected chip",
            },
        },
    },
    6: {
        "name": "calibration_1",
        "description": "Gain curve: 200 mV baseline, 4.7 mV/fC gain, 0.5 µs peaking (snc=1, sg0=1, sg1=1, st0=0, st1=1)",
        "granularity": "channel",
        "fault_types": {
            "gain_error": {
                "description": "Measured charge response deviates >20% from expected 4.7 mV/fC curve",
                "action": "Re-configure LArASIC registers; compare with adjacent channels on same chip",
            },
            "dead_channel": {
                "description": "No calibration response — channel unresponsive to injected charge",
                "action": "Check wire-bond and I2C register write; re-run COLDATA reset sequence",
            },
        },
    },
    7: {
        "name": "calibration_2",
        "description": "Gain curve: 200 mV baseline, 7.8 mV/fC gain, 1.0 µs peaking (snc=1, sg0=1, sg1=0, st0=1, st1=0)",
        "granularity": "channel",
        "fault_types": {
            "gain_error": {
                "description": "Measured charge response deviates >20% from expected 7.8 mV/fC curve",
                "action": "Re-configure LArASIC registers; compare with adjacent channels on same chip",
            },
            "dead_channel": {
                "description": "No calibration response",
                "action": "Check wire-bond and I2C register write; re-run COLDATA reset sequence",
            },
        },
    },
    8: {
        "name": "calibration_3",
        "description": "Gain curve: 200 mV baseline, 14 mV/fC gain, 2.0 µs peaking (snc=1, sg0=0, sg1=0, st0=1, st1=1)",
        "granularity": "channel",
        "fault_types": {
            "gain_error": {
                "description": "Measured charge response deviates >20% from expected 14 mV/fC curve",
                "action": "Re-configure LArASIC registers; compare with adjacent channels on same chip",
            },
            "dead_channel": {
                "description": "No calibration response",
                "action": "Check wire-bond and I2C register write; re-run COLDATA reset sequence",
            },
        },
    },
    9: {
        "name": "calibration_4",
        "description": "Gain curve: 200 mV baseline, 25 mV/fC gain, 3.0 µs peaking (snc=1, sg0=0, sg1=1, st0=1, st1=1)",
        "granularity": "channel",
        "fault_types": {
            "gain_error": {
                "description": "Measured charge response deviates >20% from expected 25 mV/fC curve",
                "action": "Re-configure LArASIC registers; compare with adjacent channels on same chip",
            },
            "dead_channel": {
                "description": "No calibration response",
                "action": "Check wire-bond and I2C register write; re-run COLDATA reset sequence",
            },
        },
    },
    10: {
        "name": "fe_monitor",
        "description": "Front-end voltage monitoring — reads LTC2990/LTC2991 power monitors on WIB",
        "granularity": "board",
        "fault_types": {
            "rail_voltage_error": {
                "description": "VFE or VCD rail voltage outside ±5% of nominal",
                "action": "Check power supply output and cable resistance; inspect WIB power delivery path",
            },
        },
    },
    11: {
        "name": "fe_dac_monitor",
        "description": "Front-end DAC output monitoring — verifies LArASIC internal DAC voltages",
        "granularity": "board",
        "fault_types": {
            "dac_error": {
                "description": "FE DAC output deviates >10% from programmed value",
                "action": "Re-write LArASIC DAC registers; if persistent, suspect LArASIC damage",
            },
        },
    },
    12: {
        "name": "coldata_dac_monitor",
        "description": "ColdADC DAC output monitoring — verifies COLDATA internal reference voltages",
        "granularity": "board",
        "fault_types": {
            "dac_error": {
                "description": "COLDATA DAC output deviates >10% from expected reference",
                "action": "Re-run wib_adc_autocali.py; if persistent, inspect COLDATA chip",
            },
        },
    },
    13: {
        "name": "calibration_5",
        "description": "Gain curve: 900 mV baseline, 4.7 mV/fC gain, 0.5 µs peaking (snc=0, sg0=1, sg1=1, st0=0, st1=1)",
        "granularity": "channel",
        "fault_types": {
            "gain_error": {
                "description": "Measured charge response deviates >20% from expected 4.7 mV/fC curve at 900 mV baseline",
                "action": "Compare with t6 result; baseline-dependent gain error suggests LArASIC bias issue",
            },
            "dead_channel": {
                "description": "No calibration response at 900 mV baseline",
                "action": "Check wire-bond and I2C register write",
            },
        },
    },
    14: {
        "name": "calibration_6",
        "description": "Gain curve: 900 mV baseline, 14 mV/fC gain, 2.0 µs peaking (snc=0, sg0=0, sg1=0, st0=1, st1=1)",
        "granularity": "channel",
        "fault_types": {
            "gain_error": {
                "description": "Measured charge response deviates >20% from expected 14 mV/fC curve at 900 mV baseline",
                "action": "Compare with t8 result; if both fail, LArASIC gain path is damaged",
            },
            "dead_channel": {
                "description": "No calibration response at 900 mV baseline",
                "action": "Check wire-bond and I2C register write",
            },
        },
    },
    15: {
        "name": "adc_sync_pattern",
        "description": "ADC synchronization pattern — all 16 channels of each chip must lock to the COLDATA sync pattern",
        "granularity": "chip",
        "fault_types": {
            "adc_sync_loss": {
                "description": "One or more chips fail to lock ADC data lanes to sync pattern — all 16 ch of the chip affected",
                "action": "Run wib_coldata_reset.py for the affected chip slot; if persistent, re-run wib_adc_autocali.py",
            },
        },
    },
    16: {
        "name": "pll_scan",
        "description": "PLL frequency scan — COLDATA PLL must lock across the full frequency range for each chip",
        "granularity": "chip",
        "fault_types": {
            "pll_lock_fail": {
                "description": "COLDATA PLL fails to lock at one or more scan frequencies — all 16 ch of the chip affected",
                "action": "Run wib_coldata_reset.py; check clock signal integrity; if persistent, COLDATA chip may need replacement",
            },
        },
    },
}

# Derived: fault type → list of test items that detect it
FAULT_TO_TEST_ITEMS: dict[str, list[int]] = {}
for _t, _spec in TEST_ITEMS.items():
    for _fault in _spec["fault_types"]:
        FAULT_TO_TEST_ITEMS.setdefault(_fault, []).append(_t)

# Flat dict of all fault type → FaultSpec (for catalog / summary use)
ALL_FAULT_SPECS: dict[str, FaultSpec] = {
    fault: spec
    for item in TEST_ITEMS.values()
    for fault, spec in item["fault_types"].items()
}


def build_llm_reference() -> str:
    """Return a compact Markdown table of all test items for inclusion in system prompts."""
    lines = [
        "## FEMB QC Test Items\n",
        "| # | Name | Granularity | Measures | Fault types |",
        "|---|------|-------------|----------|-------------|",
    ]
    for t_num, spec in TEST_ITEMS.items():
        faults = ", ".join(f"`{f}`" for f in spec["fault_types"])
        lines.append(
            f"| t{t_num} | {spec['name']} | {spec['granularity']} "
            f"| {spec['description']} | {faults} |"
        )
    lines += [
        "\n## Fault Type Reference\n",
        "| Fault type | Granularity | Description | Action |",
        "|------------|-------------|-------------|--------|",
    ]
    seen: set[str] = set()
    for t_num, spec in TEST_ITEMS.items():
        gran = spec["granularity"]
        for fault, fspec in spec["fault_types"].items():
            if fault not in seen:
                seen.add(fault)
                lines.append(
                    f"| `{fault}` | {gran} | {fspec['description']} | {fspec['action']} |"
                )
    return "\n".join(lines)
