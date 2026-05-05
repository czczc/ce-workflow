"""MCP server exposing DAQ command tools for the CE cold-electronics QC workflow.

Run:  python mcp_daq.py [--host 127.0.0.1] [--port 8002]
"""

import argparse
from typing import Any

from mcp.server.fastmcp import FastMCP

from femb_test_schema import GAIN_MAP, PEAKING_MAP, SNC_MAP

mcp = FastMCP("ce-daq")


@mcp.tool()
def take_data(
    slot: int,
    snc_label: str,
    gain_label: str,
    peaking_label: str,
    num_samples: int = 10,
) -> dict[str, Any]:
    """Validate LArASIC DAQ parameters and return resolved register bits.

    snc_label:     '200mV' or '900mV'
    gain_label:    '4.7mV/fC', '7.8mV/fC', '14mV/fC', or '25mV/fC'
    peaking_label: '0.5us', '1.0us', '2.0us', or '3.0us'
    """
    errors = []
    if slot not in range(4):
        errors.append(f"slot must be 0–3, got {slot}")
    if snc_label not in SNC_MAP:
        errors.append(f"snc_label must be one of {list(SNC_MAP)}, got {snc_label!r}")
    if gain_label not in GAIN_MAP:
        errors.append(f"gain_label must be one of {list(GAIN_MAP)}, got {gain_label!r}")
    if peaking_label not in PEAKING_MAP:
        errors.append(f"peaking_label must be one of {list(PEAKING_MAP)}, got {peaking_label!r}")
    if num_samples < 1:
        errors.append(f"num_samples must be >= 1, got {num_samples}")
    if errors:
        return {"error": "; ".join(errors)}

    sg0, sg1 = GAIN_MAP[gain_label]
    st0, st1 = PEAKING_MAP[peaking_label]
    return {
        "slot": slot,
        "snc_label": snc_label,
        "gain_label": gain_label,
        "peaking_label": peaking_label,
        "num_samples": num_samples,
        "registers": {
            "snc": SNC_MAP[snc_label],
            "sg0": sg0, "sg1": sg1,
            "st0": st0, "st1": st1,
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CE DAQ MCP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    args = parser.parse_args()
    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.run(transport="streamable-http")
