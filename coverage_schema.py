"""Coverage-aware metadata normalisation for v0.2 harnesses.

The v0.1 evaluation exposed a measurement defect that this module is designed
to make impossible to repeat: a telemetry field that was never recorded arrived
downstream as ``None``, and every consumer had to guess whether ``None`` meant
"the event did not happen" or "nobody looked".

Both readings were used in v0.1, and each produced a wrong aggregate once:

* reading ``None`` as zero produced "7/8 tasks completed with no manual
  resume", a claim the evidence did not support;
* reading ``None`` as missing produced a "zero-resume rate of 12.5%" that looked
  like a measurement while actually scoring unmeasured tasks.

The fix is to separate the two facts at the point of collection:

```json
{
  "manual_resume_count": 0,
  "manual_resume_observed": true,
  "duration_ms": 12345,
  "duration_observed": true
}
```

A value is only interpretable next to its observation flag. This module
provides that schema, converts a v0.1-style record into it, and refuses to
publish an aggregate whose observation coverage is incomplete.

    python coverage_schema.py normalise <v0.1 metadata.json> ...
    python coverage_schema.py report <run dir> ...
    python coverage_schema.py selftest
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = "coverage-aware-1"

#: Every telemetry field, with the key its value is stored under in v0.1
#: archives and the unit the v0.2 schema normalises it to.
FIELDS = {
    "manual_resume": {
        "v01_key": "manual_resume_count",
        "unit": "count",
        "integer": True,
    },
    "runtime_error": {
        "v01_key": "harness_runtime_error_count",
        "unit": "count",
        "integer": True,
    },
    "semantic_human_intervention": {
        "v01_key": "human_intervention_count",
        "unit": "count",
        "integer": True,
    },
    "duration": {
        "v01_key": "duration_seconds",
        "unit": "ms",
        "integer": True,
    },
}

#: v0.1 stored seconds; v0.2 normalises to milliseconds for precision.
UNIT_CONVERSIONS = {
    ("duration", "ms"): lambda v: int(round(v * 1000)),
}


class CoverageError(RuntimeError):
    """Raised when an aggregate would overstate what was actually observed."""


def normalise_record(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Convert one v0.1 metadata dict into the coverage-aware schema.

    Absent values become ``null`` **with** ``observed: false`` — the pair is the
    whole point, so neither half is ever emitted alone.
    """
    out: Dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "task_id": meta.get("task_id"),
        "observations": {},
    }
    for name, spec in FIELDS.items():
        raw = meta.get(spec["v01_key"])
        observed = raw is not None
        value = raw
        if observed and name == "duration":
            value = UNIT_CONVERSIONS[("duration", "ms")](raw)
        out["observations"][name] = {
            "value": value,
            "observed": observed,
            "unit": spec["unit"],
        }
    return out


def summarise(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate telemetry, publishing only what observation coverage supports.

    An aggregate over a field with partial coverage is refused rather than
    emitted: the caller gets a ``CoverageError`` naming the field and the
    coverage, so a missing 7 tasks cannot silently become a benchmark-wide zero.
    """
    total = len(records)
    if not total:
        raise CoverageError("no records to summarise")

    out: Dict[str, Any] = {"records": total, "fields": {}}
    for name in FIELDS:
        obs = [r["observations"][name] for r in records]
        observed = [o for o in obs if o["observed"]]
        coverage = f"{len(observed)}/{total}"
        complete = len(observed) == total

        field_block: Dict[str, Any] = {
            "coverage": coverage,
            "coverage_status": "COMPLETE" if complete else "PARTIAL_COVERAGE",
        }

        if complete:
            values = [o["value"] for o in observed]
            field_block["value"] = {
                "count": len(values),
                "sum": sum(values),
                "min": min(values),
                "max": max(values),
                "mean": round(sum(values) / len(values), 2),
                "median": _median(values),
            }
        else:
            # Refuse the aggregate, but keep the coverage facts so a reader
            # can see exactly how much was measured.
            field_block["value"] = None
            field_block["refusal"] = (
                f"aggregate withheld: only {coverage} of tasks have an observed "
                f"{name}; a value over {total} would score unmeasured tasks"
            )
        out["fields"][name] = field_block
    return out


def _median(values: List[Any]) -> Optional[float]:
    s = sorted(values)
    n = len(s)
    if not n:
        return None
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _load_v01(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CoverageError(f"{path}: not parseable JSON ({e})") from e


def cmd_normalise(paths: List[str]) -> int:
    records = []
    for p in paths:
        meta = _load_v01(Path(p))
        records.append(normalise_record(meta))
    print(json.dumps({"schema": SCHEMA_VERSION, "records": records},
                     indent=2, ensure_ascii=False))
    return 0


def cmd_report(run_root: str) -> int:
    root = Path(run_root)
    records = []
    for meta_path in sorted(root.glob("*/metadata.json")):
        records.append(normalise_record(_load_v01(meta_path)))
    if not records:
        print("no metadata.json found", file=sys.stderr)
        return 2
    try:
        summary = summarise(records)
    except CoverageError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    withheld = [n for n, b in summary["fields"].items() if b["value"] is None]
    if withheld:
        print(f"\naggregates withheld for: {', '.join(withheld)}")
    return 0


def selftest() -> int:
    """The behaviours that must hold, including the refusals."""
    failures: List[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        if not cond:
            failures.append(f"{name}: {detail}" if detail else name)

    # A present value and an absent value must be distinguishable without
    # inspecting anything but the pair itself.
    present = normalise_record({
        "task_id": "T-A", "manual_resume_count": 0,
        "harness_runtime_error_count": 0, "human_intervention_count": 0,
        "duration_seconds": 1.5,
    })["observations"]
    absent = normalise_record({"task_id": "T-B"})["observations"]

    check("present value is 0", present["manual_resume"]["value"] == 0)
    check("present observed", present["manual_resume"]["observed"] is True)
    check("absent value is null", absent["manual_resume"]["value"] is None)
    check("absent not observed", absent["manual_resume"]["observed"] is False)
    check("zero and unknown differ structurally",
          (present["manual_resume"]["observed"],
           present["manual_resume"]["value"]) !=
          (absent["manual_resume"]["observed"],
           absent["manual_resume"]["value"]))

    # duration normalises seconds -> ms
    check("duration converted to ms",
          present["duration"]["value"] == 1500, str(present["duration"]))

    # Full coverage yields an aggregate.
    full = summarise([normalise_record(r) for r in [
        {"task_id": "A", "manual_resume_count": 0, "duration_seconds": 1.0},
        {"task_id": "B", "manual_resume_count": 2, "duration_seconds": 3.0},
    ]])
    check("full coverage aggregates",
          full["fields"]["manual_resume"]["coverage_status"] == "COMPLETE"
          and full["fields"]["manual_resume"]["value"]["sum"] == 2)
    check("ms median",
          full["fields"]["duration"]["value"]["median"] == 2000,
          str(full["fields"]["duration"]["value"]))

    # Partial coverage must withhold the aggregate, not emit 0.
    partial = summarise([normalise_record(r) for r in [
        {"task_id": "A", "manual_resume_count": 0},
        {"task_id": "B"},
    ]])
    block = partial["fields"]["manual_resume"]
    check("partial coverage flagged",
          block["coverage_status"] == "PARTIAL_COVERAGE", block["coverage_status"])
    check("partial coverage withholds value", block["value"] is None)
    check("partial coverage says why", "aggregate withheld" in block["refusal"])

    for msg in failures:
        print(f"FAIL {msg}")
    print(f"\n{len(failures)} failure(s); "
          f"{'OK' if not failures else 'NOT OK'}")
    return 1 if failures else 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_n = sub.add_parser("normalise")
    p_n.add_argument("paths", nargs="+")
    p_r = sub.add_parser("report")
    p_r.add_argument("run_root")
    sub.add_parser("selftest")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "normalise":
            return cmd_normalise(args.paths)
        if args.cmd == "report":
            return cmd_report(args.run_root)
        if args.cmd == "selftest":
            return selftest()
    except CoverageError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
