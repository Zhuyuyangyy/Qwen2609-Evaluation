"""Assemble the anonymous double-blind artifact snapshot for submission.

Why this exists
---------------
USENIX Security is double-blind. The artifact is part of the submission, so it
is subject to the same rule as the paper: nothing in it may point back to the
authors. That is stricter than it sounds, because the development repository
carries identifying material in places nobody thinks to look:

    backend/app/shield/__init__.py
        # Inherits ASF-BGT Framework (D:\\ZYY Project\\ASF-BGT-Framework)
        a local absolute path, and therefore the machine it was written on
    backend/app/factory.py, backend/app/main.py
        "engine": "AgentShield_V3"
        the repository name, which is searchable
    backend/app/shield/session_store.py
        # AgentShield_V3 - SQLite Session Persistence Layer
    backend/app/shield/provenance_signals.py
        "the v0.3.1-research freeze"
        a release-tag label, searchable the same way a commit SHA is

Mirroring the repository and trusting the hosting site to blur that is not
enough, so this script builds a separate snapshot and rewrites every occurrence
of a known identifying string on the way in. The development repository keeps
its own history and comments; only the shipped copy is sanitised.

What it deliberately does not do
--------------------------------
It never copies the evaluated dataset. The AgentDojo-derived Arrow dump is
about 50 MB, and the anonymous mirror's per-file limit is 8 MB and it does not
rewrite binaries, so staging it would both fail the upload and ship a file that
carries upstream dataset metadata. DATASET.md records the manifest digest
instead, and a reviewer stages the dump at the documented path.

Usage
-----
    python scripts/build_anonymous_artifact.py [--out DIR]

Exit status is 0 only if every assertion below held.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_OUT = ROOT / "artifact"

# The anonymous mirror refuses anything above this, so the snapshot must not
# either. Asserted, not trusted.
HOST_FILE_LIMIT = 8 * 1024 * 1024

# Content digests printed in the paper. These bind the snapshot to the reported
# numbers, so a snapshot that no longer hashes to them is not the paper's
# artifact and the build must fail.
CANONICAL_ARTIFACT = "benchmark/results/v0_4_trust_pareto.json"
CANONICAL_ARTIFACT_SHA256 = (
    "3e33c72d230cb7e0788dc4412574054c19dfd496546573698d73bff7b6a90565"
)
DATASET_MANIFEST_SHA256 = (
    "948b94325ae1c8cfbe41bd205fee46b0f500215559ef5cd97a25c27fcf580049"
)

# Where a reviewer must stage the Arrow dump so the replay can read it. The
# replay hard-codes this glob relative to the snapshot root.
DUMP_GLOB = "benchmark/external_datasets/ffuuugor___agentdojo-dump/**/*.arrow"

# Source-relative paths copied verbatim into the snapshot. Anything not listed
# here is left behind on purpose; see the docstring.
INCLUDE: Tuple[str, ...] = (
    # The reproduction chain: replay -> trace replay -> engine.
    "benchmark/__init__.py",
    "benchmark/agentdojo_trace_replay.py",
    "benchmark/v04_trust_replay.py",
    "benchmark/results/v0_4_trust_pareto.json",
    # The verifier that pins the reported numbers, and its tests.
    "scripts/fingerprint_agentdojo_dump.py",
    "scripts/verify_v04_reproduction.py",
    # The paper's Open Science appendix states that the figures are generated
    # from the canonical result file, so the drawing script is part of what is
    # promised. It additionally needs matplotlib, which is not in either
    # requirements file because the manuscript build is a separate toolchain;
    # README says so rather than quietly depending on it.
    "scripts/draw_manuscript_figures.py",
    "tests/__init__.py",
    "tests/test_verify_v04_reproduction.py",
    # Environment. requirements-test.txt starts with "-r requirements.txt", so
    # shipping it alone would make the documented install command fail, and
    # pytest.ini is what puts backend/ on sys.path for the backend suite.
    "requirements.txt",
    "requirements-test.txt",
    "pytest.ini",
)

# Whole subtrees copied recursively, minus __pycache__ and anything the
# denylist rejects. backend/app is the engine the replay imports; the rest of
# backend (service entry points, API layer) is not part of the experiment.
INCLUDE_TREES: Tuple[str, ...] = (
    "backend/app",
)

# Never copied, whatever else matches. benchmark/external_datasets holds the
# Arrow dumps; .tmp, dist and .uploads hold working state and prior packages.
DENY_DIRS = frozenset({
    "__pycache__", "external_datasets", ".git", ".github", ".tmp", "dist",
    ".uploads", ".pytest_cache", ".venv", "venv", "node_modules", "frontend",
    "paper", "docs", "sdk", "backup",
})

# Authored rather than derived, so a rebuild must keep them: deleting artifact/
# to regenerate it would otherwise throw away the only documents that explain
# the artifact to a reviewer.
HANDWRITTEN: Tuple[str, ...] = ("README.md", "DATASET.md")

# (old, new, expected occurrences). The expected count is the point: if an edit
# upstream changes the text, the count changes, the build fails, and nobody
# silently ships a snapshot with a local path still in it.
SUBSTITUTIONS: List[Tuple[str, str, int]] = [
    (
        "# Inherits ASF-BGT Framework (D:\\ZYY Project\\ASF-BGT-Framework)",
        "# Inherits the ASF-BGT prototype framework, developed separately.",
        1,
    ),
    (
        "# AgentShield_V3 - SQLite Session Persistence Layer",
        "# AgentShield - SQLite Session Persistence Layer",
        1,
    ),
    ('"engine": "AgentShield_V3"', '"engine": "AgentShield"', 2),
    ("v0.3.1-research froze", "v0.3.1 froze", 1),
]

# Screens the finished snapshot the way the hosting site will not: raw byte
# search over every text file, so a leak cannot hide inside a docstring.
SCREEN_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (r"Zhuyuyangyy", "author handle"),
    (r"zhuyu", "handle fragment"),
    (r"AgentShield_V3", "repository name"),
    (r"github\.com|githubusercontent|raw\.github|gitlab\.com|gitee\.com",
     "public git host"),
    (r"\b[0-9a-f]{40}\b", "40-hex git object name"),
    (r"\bv\d+\.\d+\.\d+-[A-Za-z][\w.\-]*", "release-tag label"),
    (r"\b[A-Za-z]:\\", "Windows absolute path"),
    (r"[\\/]mnt[\\/][a-z]\b", "WSL mount path"),
    (r"/(?:home|Users)/[\w.\-]+", "user home directory"),
    (r"[\w.+-]+@[\w-]+\.(?:com|org|net|cn|io|dev)\b", "email address"),
)

# Addresses that are part of the documented security behaviour rather than
# identity: the policy gateway's outbound example recipient, and the
# authorization label-matching examples in its docstring. They are compared
# against each individual match, so they suppress only themselves.
SCREEN_ALLOW_SUBSTRINGS = (
    "example.com",
    "reports@",
    "external@",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text_preserving(path: Path) -> str:
    """Read a text file without touching its line endings.

    Path.read_text() applies universal-newline translation, which silently turns
    the canonical result file's CRLF into LF. That file's SHA-256 is printed in
    the paper, so the snapshot must be byte-identical to the repository outside
    the substitutions made here.
    """
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return handle.read()


def write_text_preserving(path: Path, text: str) -> None:
    """Write back with newline="", i.e. no translation in either direction."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def sanitise(text: str) -> Tuple[str, List[Tuple[str, int]]]:
    """Apply the substitution table, reporting which entries fired.

    Only the entries that actually matched are returned, so a file nobody
    touched is not rewritten at all.
    """
    applied: List[Tuple[str, int]] = []
    for old, new, _expected in SUBSTITUTIONS:
        count = text.count(old)
        if count:
            text = text.replace(old, new)
            applied.append((old, count))
    return text, applied


def collect_files(out: Path) -> Tuple[List[Path], List[str]]:
    """Rebuild the snapshot tree and return every file written, sorted.

    The second return value names the hand-written documents that survived the
    rebuild, so the report can say whether the artifact still explains itself.
    """
    carried = {
        rel: (out / rel).read_bytes()
        for rel in HANDWRITTEN
        if (out / rel).is_file()
    }
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    written: List[Path] = []
    for rel in INCLUDE:
        src = ROOT / rel
        if not src.is_file():
            raise FileNotFoundError(f"include list entry is not a file: {rel}")
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        written.append(dst)

    for tree in INCLUDE_TREES:
        src = ROOT / tree
        if not src.is_dir():
            raise NotADirectoryError(f"include tree is not a directory: {tree}")
        for item in sorted(src.rglob("*")):
            if item.is_dir():
                continue
            if any(part in DENY_DIRS for part in item.relative_to(src).parts):
                continue
            dst = out / item.relative_to(ROOT)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dst)
            written.append(dst)

    for rel, payload in carried.items():
        dst = out / rel
        dst.write_bytes(payload)
        written.append(dst)

    return sorted(written), sorted(carried)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(DEFAULT_OUT),
                    help="snapshot directory (default: artifact/)")
    args = ap.parse_args()
    out = Path(args.out)

    problems: List[str] = []

    written, carried = collect_files(out)
    print(f"assembled {len(written)} files under {out.relative_to(ROOT)}")
    for rel in HANDWRITTEN:
        if rel in carried:
            print(f"   kept   {rel} (hand-written, never regenerated)")
        else:
            print(f"   absent {rel} -- author it before upload")

    # 1. Rewrite identifying strings. A file nothing applies to is not rewritten
    #    at all, so every other byte in the snapshot is the repository's own.
    total_bytes = 0
    largest: Tuple[int, Path] = (0, written[0])
    ledger: Dict[str, int] = {old: 0 for old, _, _ in SUBSTITUTIONS}
    sites: Dict[str, List[str]] = {old: [] for old, _, _ in SUBSTITUTIONS}
    for path in written:
        total_bytes += path.stat().st_size
        size = path.stat().st_size
        if size > largest[0]:
            largest = (size, path)
        try:
            text = read_text_preserving(path)
        except (UnicodeDecodeError, ValueError):
            continue  # binary; there should be none, caught by the arrow check
        text, applied = sanitise(text)
        if not applied:
            continue
        write_text_preserving(path, text)
        rel = str(path.relative_to(out))
        for old, count in applied:
            ledger[old] += count
            sites[old].append(f"{rel} x{count}")
            print(f"   rewrite {rel}: {count}x {old[:56]!r}")

    # Drift is judged over the whole snapshot, not per file: an entry that is
    # absent from one file is not news. What the count protects is that the
    # table still describes reality -- if an upstream edit deletes the local
    # path or duplicates the engine string, the total moves and the build fails
    # instead of quietly shipping something the table no longer covers.
    for old, new, expected in SUBSTITUTIONS:
        count = ledger[old]
        where = ", ".join(sites[old]) or "nowhere"
        if count == expected:
            print(f"   ok    {count}x {old[:56]!r} -> {new[:40]!r} ({where})")
        else:
            problems.append(
                f"substitution table drift: expected {expected} occurrence(s) of "
                f"{old!r} across the snapshot, found {count} ({where}) -- "
                f"update SUBSTITUTIONS and re-run"
            )

    # 2. Size limit the mirror enforces.
    for path in written:
        if path.stat().st_size > HOST_FILE_LIMIT:
            problems.append(
                f"{path.relative_to(out)} is {path.stat().st_size} bytes, "
                f"above the {HOST_FILE_LIMIT}-byte mirror limit"
            )

    # 3. The dataset must not be here, in any form.
    for path in written:
        if path.suffix == ".arrow":
            problems.append(f"{path.relative_to(out)}: Arrow dump must not ship")
        if path.suffix == ".parquet":
            problems.append(f"{path.relative_to(out)}: Parquet dump must not ship")

    # 4. No build residue, no caches.
    for path in written:
        parts = path.relative_to(out).parts
        if "__pycache__" in parts:
            problems.append(f"{path.relative_to(out)}: build residue shipped")

    # 5. The dataset must not be here under any name, directory or not.
    for leaked in (out / "benchmark" / "external_datasets",):
        if leaked.exists():
            problems.append(f"{leaked.relative_to(out)}: the Arrow dump is "
                            f"outside the artifact on purpose")

    # 6. The canonical artifact must still be the paper's canonical artifact.
    canon = out / CANONICAL_ARTIFACT
    if not canon.is_file():
        problems.append(f"missing canonical artifact {CANONICAL_ARTIFACT}")
    else:
        digest = sha256_file(canon)
        if digest != CANONICAL_ARTIFACT_SHA256:
            problems.append(
                f"{CANONICAL_ARTIFACT} hashes to {digest}, paper reports "
                f"{CANONICAL_ARTIFACT_SHA256}"
            )
        else:
            print(f"   ok    {CANONICAL_ARTIFACT} matches the paper digest")

    # 7. Screen the finished tree for identifying material. The allowlist is
    #    applied per match, so an allowed address never excuses the other
    #    patterns in the same file.
    for path in written:
        try:
            text = read_text_preserving(path)
        except (UnicodeDecodeError, ValueError):
            continue
        for pattern, why in SCREEN_PATTERNS:
            for m in re.finditer(pattern, text):
                hit = m.group(0)
                if any(allow in hit for allow in SCREEN_ALLOW_SUBSTRINGS):
                    continue
                line = text[:m.start()].count("\n") + 1
                problems.append(
                    f"{path.relative_to(out)}:{line}: {why} "
                    f"({hit[:60]!r})"
                )

    print(f"\nsnapshot total: {total_bytes:,} bytes across {len(written)} files")
    print(f"largest file  : {largest[0]:,} bytes "
          f"({largest[1].relative_to(out)})")
    print(f"reviewer stages the dump at: {DUMP_GLOB}")
    print(f"dataset manifest digest    : {DATASET_MANIFEST_SHA256}")

    if problems:
        print(f"\nFAIL: {len(problems)} problem(s)")
        for p in problems:
            print(f"   {p}")
        return 1

    print("\nOK: anonymous artifact snapshot is clean and complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
