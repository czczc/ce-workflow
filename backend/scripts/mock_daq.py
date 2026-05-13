#!/usr/bin/env python3
"""Mock DAQ — mirror an existing QC run dir into a fresh one, drip-feeding
report files at a configurable interval so the /monitor watcher has something
to react to without a real DAQ running.

Usage:
    python backend/scripts/mock_daq.py \\
        [--source DIR] [--dest NAME] [--interval N] \\
        [--inject-fail t3,t7] [--single-femb S0] [--qc-root DIR]
"""

import argparse
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

REPORT_RE = re.compile(r"^report_FEMB_\d+_t(\d+)_[PF]_S\d+\.md$")
FINAL_RE = re.compile(r"^Final_Report_FEMB_.*\.md$")

DEFAULT_QC_ROOT = "/Users/chaozhang/tmp/FEMB_QC"
DEFAULT_SOURCE_REL = (
    "Report/Time_2026_05/"
    "10_02_58_23_CTS_BNL_CTS_01_S0BNL_FEMB_IO-1865-1L_00016_S1BNL_FEMB_IO-1865-1L_00010_LN_QC"
)


def discover_femb_subdirs(source: Path) -> list[Path]:
    return sorted(p for p in source.iterdir() if p.is_dir() and p.name.startswith("FEMB"))


def collect_reports(femb_dir: Path) -> dict[int, Path]:
    out: dict[int, Path] = {}
    for f in femb_dir.iterdir():
        m = REPORT_RE.match(f.name)
        if m:
            out[int(m.group(1))] = f
    return out


def find_final_report(femb_dir: Path) -> Path | None:
    for f in femb_dir.iterdir():
        if FINAL_RE.match(f.name):
            return f
    return None


def parse_inject_fail(spec: str) -> set[int]:
    ids: set[int] = set()
    for tok in spec.split(","):
        tok = tok.strip().lstrip("t")
        if tok.isdigit():
            ids.add(int(tok))
    return ids


_INJECT_BANNER = (
    "> **[Mock DAQ — injected failure]** This report was synthesized from a "
    "passing run with pass/fail markers flipped, for testing the /monitor "
    "watcher and diagnostic agent.\n\n"
)


def flip_to_fail(text: str) -> str:
    """Flip pass markers in a passing-test markdown so it reads as failing."""
    text = text.replace("PASS", "FAIL")
    text = text.replace("< Pass >", "< Fail >")
    text = text.replace("color: green", "color: red")
    text = text.replace("color : green", "color : red")
    return _INJECT_BANNER + text


def write_report(src: Path, dst_dir: Path, inject_fail: bool) -> Path:
    name = src.name.replace("_P_", "_F_") if inject_fail else src.name
    dst = dst_dir / name
    if inject_fail:
        dst.write_text(flip_to_fail(src.read_text(encoding="utf-8")), encoding="utf-8")
    else:
        shutil.copy2(src, dst)
    return dst


def default_dest_name() -> str:
    now = datetime.now()
    return f"{now.day:02d}_{now.hour:02d}_{now.minute:02d}_{now.second:02d}_MOCK_LN_QC"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", help="Existing real QC run dir to mirror (default: built-in example under $QC_ROOT)")
    parser.add_argument("--dest", help="Destination dir name under Time_<YYYY>_<MM>/, or absolute path (default: auto-named with current timestamp)")
    parser.add_argument("--interval", type=float, default=10.0, help="Seconds between reports (default: 10)")
    parser.add_argument("--inject-fail", default="", help="Comma-separated test IDs to flip _P_ to _F_ (e.g. t3,t7)")
    parser.add_argument("--single-femb", default="", help="Only mirror one FEMB subdir whose name contains this substring (e.g. S0)")
    parser.add_argument("--qc-root", default=os.environ.get("QC_ROOT", DEFAULT_QC_ROOT))
    args = parser.parse_args()

    qc_root = Path(args.qc_root).resolve()
    source = Path(args.source).resolve() if args.source else (qc_root / DEFAULT_SOURCE_REL).resolve()
    if not source.is_dir():
        print(f"error: source dir does not exist: {source}", file=sys.stderr)
        sys.exit(1)

    dest_arg = args.dest or default_dest_name()
    dest_path = Path(dest_arg)
    if dest_path.is_absolute():
        dest = dest_path
    else:
        now = datetime.now()
        dest = qc_root / "Report" / f"Time_{now.year}_{now.month:02d}" / dest_arg

    if dest.exists():
        print(f"error: destination already exists: {dest}", file=sys.stderr)
        sys.exit(1)

    inject_ids = parse_inject_fail(args.inject_fail)

    femb_subdirs = discover_femb_subdirs(source)
    if args.single_femb:
        femb_subdirs = [d for d in femb_subdirs if args.single_femb in d.name]
        if not femb_subdirs:
            print(f"error: no FEMB subdir matches '{args.single_femb}'", file=sys.stderr)
            sys.exit(1)
    if not femb_subdirs:
        print(f"error: no FEMB subdirs found in {source}", file=sys.stderr)
        sys.exit(1)

    dest.mkdir(parents=True)
    print(f"mock DAQ -> {dest}")
    print(f"source:    {source}")

    plan: list[tuple[Path, dict[int, Path], Path | None]] = []
    all_test_ids: set[int] = set()
    for sd in femb_subdirs:
        reports = collect_reports(sd)
        final = find_final_report(sd)
        dst_sub = dest / sd.name
        dst_sub.mkdir()
        plan.append((dst_sub, reports, final))
        all_test_ids.update(reports.keys())
        print(f"  femb: {sd.name} ({len(reports)} reports, final={'yes' if final else 'no'})")

    print(f"interval: {args.interval}s, inject-fail: {sorted(inject_ids) or '[]'}")
    print()

    for t in sorted(all_test_ids):
        time.sleep(args.interval)
        injected = t in inject_ids
        for dst_sub, reports, _ in plan:
            src = reports.get(t)
            if src is None:
                continue
            out = write_report(src, dst_sub, injected)
            tag = "FAIL (injected)" if injected else "pass" if "_P_" in out.name else "fail"
            print(f"  + {out.relative_to(dest)}  [{tag}]")

    time.sleep(args.interval)
    for dst_sub, _, final in plan:
        if final is None:
            continue
        out = dst_sub / final.name
        shutil.copy2(final, out)
        print(f"  + {out.relative_to(dest)}  [FINAL]")

    print("\ndone.")


if __name__ == "__main__":
    main()
