"""Path relativisation for the submission bundle.

Kept in its own module, written with plain literals, because the escaping rules
for a run of backslashes are what defeated every attempt to patch the pattern
inline.

Three operator locations are rewritten:

* the frozen-benchmark root  -> ``RealRepoBench-Q2609/``
* the evaluation root        -> removed, leaving a workspace-relative path
* any ``X:\\Users\\...``     -> ``<user-home>``
* any ``X:\\python...``      -> ``<python-home>``

Every pattern accepts a *run* of backslashes. Absolute paths appear in three
shapes here: prose (one), JSON strings (two), and double-escaped JSON (four).
A pattern that matches only one run silently leaves the rest behind, which is
how the previous "absolute paths = 0" QA claim became false.
"""

from __future__ import annotations

import re
from pathlib import Path

EVAL_ROOT = Path(__file__).resolve().parent
BENCH = EVAL_ROOT.parent / "RealRepoBench-Q2609"

#: One or more backslashes, in a character class.
_BS = r"[\\]+"
#: An optional trailing run of backslashes.
_BS_OPT = r"[\\]*"

RULES = [
    # MSYS/Git-Bash form first: /d/ZYY Project/... (forward slashes, no colon).
    (re.compile(r"/[a-zA-Z]/ZYY Project/[^\r\n" + chr(39) + chr(34) + r"]*"),
     "<operator-path>"),
    # Most specific first: the benchmark root and its JSON-escaped form.
    (re.compile(r"D:" + _BS + r"ZYY Project" + _BS + r"RealRepoBench-Q2609" + _BS_OPT),
     "RealRepoBench-Q2609/"),
    # The evaluation root, in prose or JSON-escaped form. The trailing run of
    # backslashes is consumed too, so nothing dangling is left behind.
    (re.compile(r"D:" + _BS + r"ZYY Project" + _BS + r"Qwen2609-Evaluation" + _BS_OPT),
     ""),
    # Any other path under the operator's project directory.
    (re.compile(r"D:" + _BS + r"ZYY Project" + _BS + r"[^\r\n" + chr(39) + chr(34) + r"]*"),
     "<operator-path>"),
    # User-home trees, including non-ASCII usernames.
    (re.compile(r"[A-Za-z]:" + _BS + r"Users" + _BS + r"[^\r\n" + chr(39) + chr(34) + r"]*"),
     "<user-home>"),
    # The interpreter's own location, which shows up in tool traces.
    (re.compile(r"[A-Za-z]:" + _BS + r"python[^\r\n" + chr(39) + chr(34) + r"]*"),
     "<python-home>"),
    # Generic C:/D: drive-root leftovers that are not covered above.
    (re.compile(r"D:" + _BS + r"[A-Za-z0-9_.\u4e00-\u9fa5-]+" + _BS
                + r"[^\r\n" + chr(39) + chr(34) + r"]*"),
     "<absolute-path>"),
]

#: Names that must never survive a relativisation pass.
_LEAK_MARKERS = ("ZYY Project", "python", "Users", "AppData")


def relativise(text: str) -> str:
    """Rewrite operator absolute paths into portable references."""
    out = text
    for pattern, replacement in RULES:
        out = pattern.sub(lambda _m, _r=replacement: _r, out)
    return out


def find_residual(text: str) -> list:
    """Absolute-path-looking substrings still present, for QA.

    Covers all three shapes these paths take here: ``D:\\x`` in prose,
    ``D:\\\\x`` inside JSON, and the MSYS ``/d/x`` form Git Bash prints.
    """
    tail = r"[^\r\n" + chr(39) + chr(34) + r"]{0,60}"
    rx = re.compile(
        r"(?:[A-Za-z]:" + _BS + r"|/[a-zA-Z]/)"
        r"(?:Users|python|ZYY)" + tail)
    return sorted(set(rx.findall(text)))


if __name__ == "__main__":
    B = chr(92)
    B2 = B * 2
    B4 = B * 4
    samples = [
        "JSON1 " + "D:" + B2 + "ZYY Project" + B2 + "Qwen2609-Evaluation" + B2 + "workspaces" + B2 + "RB-AS-002",
        "JSON2 " + "D:" + B4 + "ZYY Project" + B4 + "Qwen2609-Evaluation" + B4 + "workspaces",
        "PROSE " + "D:" + B + "ZYY Project" + B + "Qwen2609-Evaluation" + B + "workspaces" + B + "RB-AS-002",
        "BENCH " + "D:" + B + "ZYY Project" + B + "RealRepoBench-Q2609" + B + "grader" + B + "score.py",
        "PY " + "D:" + B + "python" + chr(23454) + B + "Lib" + B + "site-packages" + B + "pytest",
        "HOME " + "C:" + B + "Users" + B + chr(32844) + B + "AppData" + B + "Local" + B + "Temp",
    ]
    ok = True
    for s in samples:
        out = relativise(s)
        residual = find_residual(out)
        if residual:
            ok = False
        print(("LEAK " if residual else "ok   ") + repr(out[:66])
              + ("" if not residual else f"  residual={residual}"))
    print("result:", "clean" if ok else "residual absolute paths")
    raise SystemExit(0 if ok else 1)
