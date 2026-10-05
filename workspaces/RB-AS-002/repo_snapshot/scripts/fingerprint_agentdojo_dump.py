"""Deterministic fingerprint of the locally staged AgentDojo dump.

Why this exists
---------------
The v0.4.1 logged-trace experiment reads Arrow files from
``benchmark/external_datasets/``. Running the same replay script against a
*different version* of that dump is not a reproduction, and the difference is
invisible in the output artifact unless the input bytes are pinned down.

This script records the input side of the reproduction contract:

    files        -- how many Arrow files were hashed
    total_bytes  -- the bytes those files occupy
    manifest_sha256 -- a single digest over (relative_path, file_sha256) pairs
                      in sorted path order
    rows         -- rows the harness parses out of them
    trajectories -- trajectories ``build_trajectories`` constructs

The manifest digest is stable across machines because it depends only on file
contents and repository-relative paths, never on absolute directories, mtimes
or inode order. Sorted path order is what makes the concatenation order
deterministic.

This script is read-only with respect to the dataset: it hashes, it does not
modify, move or regenerate anything. It is a verification tool, not a predictor
-- no expected value is fed back into the detector, the engine or the replay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# The dump the v0.4.1 experiment actually reads. Other datasets staged under
# external_datasets/ (AgentHarm, agentdojo_tiny) are not part of this
# experiment and are fingerprinted separately so the manifest stays specific.
AGENTDOJO_DUMP = ROOT / "benchmark" / "external_datasets" / "ffuuugor___agentdojo-dump"

_CHUNK = 1 << 20  # 1 MiB: the dump is ~50 MB, so stream it.


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    """Repository-relative POSIX path, so the digest is machine-independent."""
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def fingerprint(dump_dir: Path = AGENTDOJO_DUMP) -> Dict[str, Any]:
    """Return the deterministic fingerprint of ``dump_dir``.

    Raises ``FileNotFoundError`` when no Arrow file is present: a fingerprint
    of nothing would otherwise look like a valid fingerprint of an empty
    dataset, which is precisely the failure this script exists to prevent.
    """
    if not dump_dir.is_dir():
        raise FileNotFoundError(
            f"AgentDojo dump directory not found: {_relative(dump_dir)}\n"
            "Stage the dump before fingerprinting; see DATASET.md, which records "
            "the source, the expected path and the expected manifest digest."
        )

    arrow_files = sorted(dump_dir.rglob("*.arrow"), key=lambda p: _relative(p))
    if not arrow_files:
        raise FileNotFoundError(
            f"No .arrow files under {_relative(dump_dir)}. "
            "Refusing to emit a fingerprint of an empty dataset."
        )

    entries: List[Dict[str, Any]] = []
    manifest = hashlib.sha256()
    total_bytes = 0
    for path in arrow_files:
        rel = _relative(path)
        size = path.stat().st_size
        file_sha = _sha256_file(path)
        # NUL separator: a path cannot contain NUL, so (a, b) pairs cannot be
        # confused by a different (a, b) pair producing the same concatenation.
        manifest.update(rel.encode("utf-8"))
        manifest.update(b"\0")
        manifest.update(file_sha.encode("ascii"))
        total_bytes += size
        entries.append({"path": rel, "bytes": size, "sha256": file_sha})

    # Row/trajectory counts come from the same loader the replay uses, so the
    # fingerprint describes the dataset as the harness sees it rather than as
    # the filesystem sees it.
    from benchmark.agentdojo_trace_replay import build_trajectories, load_rows

    rows = load_rows()
    _trajectories, audit = build_trajectories(rows)

    return {
        "dataset": "ffuuugor/agentdojo-dump",
        "files": len(entries),
        "total_bytes": total_bytes,
        "manifest_sha256": manifest.hexdigest(),
        "rows": len(rows),
        "trajectories": audit["trajectories"],
        "excluded_total": audit["excluded_total"],
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the fingerprint as JSON instead of the human summary",
    )
    args = parser.parse_args()

    try:
        payload = fingerprint()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"dataset:        {payload['dataset']}")
        print(f"files:          {payload['files']}")
        print(f"total_bytes:    {payload['total_bytes']}")
        print(f"rows:           {payload['rows']}")
        print(f"trajectories:   {payload['trajectories']}")
        print(f"excluded_total: {payload['excluded_total']}")
        print(f"manifest_sha256: {payload['manifest_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
