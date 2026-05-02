export const graphNodes = [
  { id: 'check_hardware',   label: 'Hardware Check' },
  { id: 'monitor_respond',  label: 'Monitor' },
  { id: 'daq_acquire',      label: 'DAQ Acquire' },
  { id: 'qc_analyze',       label: 'QC Analysis' },
  { id: 'retrieve_context', label: 'Retrieve Context' },
  { id: 'build_diagnosis',  label: 'Diagnosis' },
  { id: 'narrate',          label: 'Narrate' },
  { id: 'catalog_write',    label: 'Report' },
]

export const graphEdges = [
  { id: 'e1', source: 'check_hardware',   target: 'monitor_respond' },
  { id: 'e2', source: 'monitor_respond',  target: 'daq_acquire',      label: 'OK' },
  { id: 'e3', source: 'daq_acquire',      target: 'qc_analyze' },
  { id: 'e4', source: 'qc_analyze',       target: 'retrieve_context', label: 'anomalies' },
  { id: 'e5', source: 'qc_analyze',       target: 'catalog_write',    label: 'pass' },
  { id: 'e6', source: 'retrieve_context', target: 'build_diagnosis' },
  { id: 'e7', source: 'build_diagnosis',  target: 'narrate' },
  { id: 'e8', source: 'narrate',          target: 'catalog_write' },
]
