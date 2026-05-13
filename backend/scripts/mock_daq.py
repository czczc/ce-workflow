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
import random
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

REPORT_RE = re.compile(r"^report_FEMB_\d+_t(\d+)_[PF]_S\d+\.md$")
FINAL_RE = re.compile(r"^Final_Report_FEMB_.*\.md$")
FEMB_SLOT_RE = re.compile(r"_S(\d+)$")
N_TESTS = 17

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


def slot_from_subdir(name: str) -> str | None:
    """Return 'S0' / 'S1' / ... extracted from a FEMB subdir name."""
    m = FEMB_SLOT_RE.search(name)
    return f"S{m.group(1)}" if m else None


def random_failures(min_count: int = 1, max_count: int = 3) -> list[int]:
    count = random.randint(min_count, max_count)
    return sorted(random.sample(range(1, N_TESTS + 1), count))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", help="Existing real QC run dir to mirror (default: built-in example under $QC_ROOT)")
    parser.add_argument("--dest", help="Destination dir name under Time_<YYYY>_<MM>/, or absolute path (default: auto-named with current timestamp)")
    parser.add_argument("--interval", type=float, default=None, help="Seconds between reports (default: 10, or 2 with --random)")
    parser.add_argument("--inject-fail", default="", help="Comma-separated test IDs to flip _P_ to _F_ for ALL fembs (e.g. t3,t7)")
    parser.add_argument("--inject-fail-s0", default=None, help="Per-slot override for S0 (overrides --inject-fail for that slot)")
    parser.add_argument("--inject-fail-s1", default=None, help="Per-slot override for S1 (overrides --inject-fail for that slot)")
    parser.add_argument("--single-femb", default="", help="Only mirror one FEMB subdir whose name contains this substring (e.g. S0)")
    parser.add_argument("--random", action="store_true", help="Quick test: random failures per FEMB (1-3 each), default interval=2s")
    parser.add_argument("--qc-root", default=os.environ.get("QC_ROOT", DEFAULT_QC_ROOT))
    args = parser.parse_args()

    qc_root = Path(args.qc_root).resolve()
    source = Path(args.source).resolve() if args.source else (qc_root / DEFAULT_SOURCE_REL).resolve()
    if not source.is_dir():
        print(f"error: source dir does not exist: {source}", file=sys.stderr)
        sys.exit(1)

    if args.random:
        if args.inject_fail_s0 is None and args.inject_fail_s1 is None and not args.inject_fail:
            args.inject_fail_s0 = ",".join(f"t{i}" for i in random_failures())
            args.inject_fail_s1 = ",".join(f"t{i}" for i in random_failures())
        if args.interval is None:
            args.interval = 2.0
    if args.interval is None:
        args.interval = 10.0

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

    global_inject = parse_inject_fail(args.inject_fail)
    override_by_slot: dict[str, set[int]] = {}
    if args.inject_fail_s0 is not None:
        override_by_slot["S0"] = parse_inject_fail(args.inject_fail_s0)
    if args.inject_fail_s1 is not None:
        override_by_slot["S1"] = parse_inject_fail(args.inject_fail_s1)

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
    if args.random:
        print("(random mode)")

    plan: list[tuple[Path, dict[int, Path], Path | None, set[int], str]] = []
    all_test_ids: set[int] = set()
    for sd in femb_subdirs:
        slot = slot_from_subdir(sd.name) or "?"
        inject_ids = override_by_slot.get(slot, global_inject)
        reports = collect_reports(sd)
        final = find_final_report(sd)
        dst_sub = dest / sd.name
        dst_sub.mkdir()
        plan.append((dst_sub, reports, final, inject_ids, slot))
        all_test_ids.update(reports.keys())
        fails_str = sorted(inject_ids) if inject_ids else "[]"
        print(f"  femb: {sd.name}  ({slot}, {len(reports)} reports, final={'yes' if final else 'no'}, inject-fail={fails_str})")

    print(f"interval: {args.interval}s")
    print()

    for t in sorted(all_test_ids):
        time.sleep(args.interval)
        for dst_sub, reports, _, inject_ids, _ in plan:
            src = reports.get(t)
            if src is None:
                continue
            injected = t in inject_ids
            out = write_report(src, dst_sub, injected)
            tag = "FAIL (injected)" if injected else "pass" if "_P_" in out.name else "fail"
            print(f"  + {out.relative_to(dest)}  [{tag}]")

    time.sleep(args.interval)
    for dst_sub, _, final, _, _ in plan:
        if final is None:
            continue
        out = dst_sub / final.name
        shutil.copy2(final, out)
        print(f"  + {out.relative_to(dest)}  [FINAL]")

    print("\ndone.")


if __name__ == "__main__":
    main()
