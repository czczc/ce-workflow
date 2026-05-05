from femb_test_schema import ALL_FAULT_SPECS

# Backward-compatible mapping used by catalog_agent._build_summary
SUGGESTED_ACTIONS: dict[str, str] = {
    fault: spec["action"] for fault, spec in ALL_FAULT_SPECS.items()
}
