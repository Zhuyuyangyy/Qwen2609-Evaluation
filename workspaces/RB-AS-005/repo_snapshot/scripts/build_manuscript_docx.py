"""Build the submission DOCX from the v0.4.1 English manuscript master.

The Markdown master (docs/research/MANUSCRIPT_v041_en.md) is the *research
source*: it carries editorial provenance markers, both spellings of
"authorization", two-figure captions as italic placeholders, and revision
labels such as "Table 1b". Those belong in the master and not in a document a
reviewer reads. This script applies the submission-layer transforms:

  1. drop the internal status note above the abstract;
  2. drop every editorial marker ([unchanged from v0.3.1], [new in v0.4.1],
     [renumbered ...]);
  3. normalise British "authorisation/authorised/authorise" to US
     "authorization/authorized/authorize", while leaving code identifiers
     (AUTHORISED_ACTION_CEILING), repository paths and the tag name untouched;
  4. merge Table 1 and Table 1b into a single Table 1 with all six rungs, giving
     the frozen v0.3 rows their confidence intervals and marking the v0.4.1 rows
     with an em dash plus a note explaining why no interval exists;
  5. qualify the bootstrap sentence in Section 5.2 to the frozen v0.3 ladder;
  6. insert the two redrawn figures instead of italic placeholder text.

Presentation only. Nothing here changes a number: every value in the generated
table and figure is read from benchmark/results/v0_04_trust_pareto.json.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "docs" / "research" / "MANUSCRIPT_v041_en.md"
ARTIFACT = ROOT / "benchmark" / "results" / "v0_4_trust_pareto.json"
FIGURE_1 = ROOT / "docs" / "research" / "figures" / "figure1_observability_gap.png"
FIGURE_2 = ROOT / "docs" / "research" / "figures" / "figure2_ladder.png"
OUT = ROOT / "docs" / "research" / "AgentShield_v041_manuscript.docx"

TITLE = ("AgentShield: Closing the Observability Gap in Tool-Using LLM Agents "
         "with Provenance-Aware Runtime Governance")

# Identifier contexts whose spelling must survive normalisation.
_PROTECTED = re.compile(
    r"(`[^`]*`"
    r"|AUTHORISED_ACTION_CEILING"
    r"|v0\.4\.1-research"
    r"|benchmark/[\w./-]+"
    r"|scripts/[\w./-]+"
    r")"
)


def normalise_spelling(text: str) -> str:
    """British -> US spelling, outside protected code/path identifiers."""
    parts = _PROTECTED.split(text)
    for i, part in enumerate(parts):
        if not part or _PROTECTED.fullmatch(part):
            continue
        part = re.sub(r"\bauthorisation\b", "authorization", part)
        part = re.sub(r"\bAuthorisation\b", "Authorization", part)
        part = re.sub(r"\bauthorised\b", "authorized", part)
        part = re.sub(r"\bAuthorised\b", "Authorized", part)
        part = re.sub(r"\bauthorise\b", "authorize", part)
        part = re.sub(r"\bAuthorise\b", "Authorize", part)
        parts[i] = part
    return "".join(parts)


_EDITORIAL = re.compile(
    r"\*\*\[(?:unchanged from v0\.3\.1|new in v0\.4\.1|renumbered[^*]*)"
    r"(?:[^\]]*)?\]\*\*\s*",
    re.IGNORECASE,
)

# Repetition of an internal path after its first principled mention. Each pair
# is (first mention replacement is left alone, later occurrences become the
# short name). Order matters: the longest path is rewritten first so a prefix
# rule cannot fire on a name that already includes it.
_PATH_REWRITES = (
    ("benchmark/results/v0_4_trust_pareto.reproduced.json", "the reproduced artifact"),
    ("benchmark/results/v0_4_trust_pareto.json", "the canonical artifact"),
    ("benchmark/v04_trust_replay.py", "the replay harness"),
    ("scripts/verify_v04_reproduction.py", "the verifier"),
    ("benchmark/independent_eval/", None),
)


def _reduce_paths(text: str) -> str:
    """Keep the first explicit occurrence of each path, later ones become short.

    Code fences are skipped: the exact path inside a command block is the thing
    a reader is meant to type, so it must survive verbatim.
    """
    out_lines: List[str] = []
    in_fence = False
    seen = set()
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            out_lines.append(line)
            continue
        if in_fence:
            out_lines.append(line)
            continue
        for path, short in _PATH_REWRITES:
            if path not in line:
                continue
            if short is None:
                continue  # dropped entirely: no prose value
            if path not in seen:
                seen.add(path)
                continue
            line = line.replace(path, short)
        out_lines.append(line)
    return "\n".join(out_lines)


def read_master() -> str:
    text = MASTER.read_text(encoding="utf-8")
    # 1. internal status note above the abstract
    text = re.sub(
        r"^# AgentShield:.*?\n\nAnonymous Authors\n\nManuscript based on the frozen "
        r"v0\.4\.1-research artifact\n\n> \*\*Status note\.\*\*.*?\n\n---\n\n",
        "",
        text,
        flags=re.DOTALL,
    )
    # 2. editorial markers
    text = _EDITORIAL.sub("", text)
    # 3. the two tables are merged, so references follow the single table number
    text = text.replace("Table 1b", "Table 1")
    # 4. keep repository paths out of the running prose. The submission keeps one
    #    explicit path per artifact inside the reproduction subsection and refers
    #    to them by short name elsewhere, so a reader is not repeatedly shown
    #    internal file layout.
    text = _reduce_paths(text)
    # 5. spelling, applied last so protected spans survive
    return normalise_spelling(text)


def load_ladder() -> List[Dict[str, object]]:
    with open(ARTIFACT, encoding="utf-8") as handle:
        return json.load(handle)["results"]


_LADDER_LABEL = {
    "local_only": "single-event gate (local only)",
    "plus_output_inspection": "+ untrusted output inspection",
    "plus_entity_provenance": "+ entity provenance / taint",
    "plus_intent_consistency": "+ intent consistency",
    "plus_trust_policy_v0_4": "+ safe authorization (v0.4.1)",
    "plus_intent_slots": "+ structured intent slots",
}

# Frozen v0.3.1-research 95% cluster-bootstrap intervals over trajectories,
# reproduced from Table 1 of that release. They are not recomputed here; they
# are recorded because the committed v0.3 artifact carries them and the v0.4.1
# artifact does not.
_V03_CI = {
    ("local_only", "attack"): ("0.0", "0.0"),
    ("local_only", "benign"): ("0.0", "3.1"),
    ("plus_output_inspection", "attack"): ("1.75", "5.5"),
    ("plus_output_inspection", "benign"): ("11.34", "27.84"),
    ("plus_entity_provenance", "attack"): ("12.5", "19.75"),
    ("plus_entity_provenance", "benign"): ("31.96", "50.52"),
    ("plus_intent_consistency", "attack"): ("12.5", "19.75"),
    ("plus_intent_consistency", "benign"): ("31.96", "50.52"),
}


def _set_cell(cell, text: str, bold: bool = False, align: str = "left") -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.alignment = {
        "left": WD_ALIGN_PARAGRAPH.LEFT,
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
    }[align]
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.size = Pt(9)
    run.font.name = "Times New Roman"


def _shade(cell, hex_fill: str) -> None:
    element = OxmlElement("w:shd")
    element.set(qn("w:fill"), hex_fill)
    cell._tc.get_or_add_tcPr().append(element)


# ─── Minimal inline Markdown -> runs ───────────────────────────────────────

_INLINE = re.compile(r"(\*\*.+?\*\*|`[^`]+`)")


def _write_runs(paragraph, text: str, base_italic: bool = False) -> None:
    for token in _INLINE.split(text):
        if not token:
            continue
        if token.startswith("**") and token.endswith("**"):
            run = paragraph.add_run(token[2:-2])
            run.bold = True
        elif token.startswith("`") and token.endswith("`"):
            run = paragraph.add_run(token[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(9)
        else:
            run = paragraph.add_run(token)
        if base_italic:
            run.italic = True
    return None


def _style_document(document: Document) -> None:
    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.15

    for name, size, space_before in (
        ("Heading 1", 14, 14),
        ("Heading 2", 12, 12),
        ("Heading 3", 11, 10),
        ("Heading 4", 11, 8),
    ):
        style = styles[name]
        style.font.name = "Times New Roman"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.paragraph_format.space_before = Pt(space_before)
        style.paragraph_format.space_after = Pt(4)


def build() -> Path:
    master = read_master()
    lines = master.split("\n")

    document = Document()
    _style_document(document)

    section = document.sections[0]
    section.top_margin = Inches(1.0)
    section.bottom_margin = Inches(1.0)
    section.left_margin = Inches(1.0)
    section.right_margin = Inches(1.0)

    # ── Title block: authors, affiliation and code availability live here,
    #    not under the abstract as an internal note.
    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title.add_run(TITLE)
    title_run.bold = True
    title_run.font.size = Pt(15)

    for line, note in (
        ("Anonymous Authors", True),
        ("", False),
        ("Manuscript for review. Submission content complete; author, affiliation, "
         "funding and target-venue formatting to be supplied at submission.", True),
    ):
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run(line)
        run.italic = note
        run.font.size = Pt(10 if note else 11)

    results = load_ladder()
    table_inserted = False
    figure1_inserted = False
    figure2_inserted = False

    index = 0
    while index < len(lines):
        raw = lines[index]
        line = raw.rstrip()
        stripped = line.strip()

        # ── Tables: emit the merged six-rung table exactly once, at the point
        #    the old draft placed Table 1, and drop the other captioned tables.
        if stripped.startswith("|") and (
            "Attack trace BLOCK" in stripped or "Attack-labelled trace BLOCK" in stripped
        ):
            if table_inserted:
                index += 1
                while index < len(lines) and (
                    lines[index].strip().startswith("|") or not lines[index].strip()
                ):
                    index += 1
                continue
            _emit_merged_table(document, results)
            table_inserted = True
            index += 1
            while index < len(lines) and (
                lines[index].strip().startswith("|") or not lines[index].strip()
            ):
                index += 1
            continue

        # Drop the superseded captions of the two tables being merged. The
        # merged table emits its own caption, so leaving these would produce
        # two captions for one table in the submission document.
        if stripped.startswith("*Table 1.") or stripped.startswith("*Table 1b."):
            index += 1
            continue

        # ── Figures: replace the placeholder paragraphs with real images.
        if stripped.startswith("*Figure 1."):
            _emit_figure(document, FIGURE_1,
                         "Figure 1. The observability gap. The final tool call may look "
                         "ordinary; the security-relevant distinction is the provenance of "
                         "arguments introduced by earlier content.")
            figure1_inserted = True
            index += 1
            continue
        if stripped.startswith("*Figure 2."):
            _emit_figure(document, FIGURE_2,
                         "Figure 2. Attack-labelled and benign trace blocking across the "
                         "six-rung ladder. The benign series is a 97-trajectory census; the "
                         "attack series is a 400-trajectory deterministic prefix.")
            figure2_inserted = True
            index += 1
            continue

        # ── Code fences.
        if stripped.startswith("```"):
            index += 1
            block: List[str] = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                block.append(lines[index])
                index += 1
            index += 1
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Inches(0.3)
            paragraph.paragraph_format.space_before = Pt(4)
            paragraph.paragraph_format.space_after = Pt(8)
            run = paragraph.add_run("\n".join(block))
            run.font.name = "Consolas"
            run.font.size = Pt(9)
            continue

        # ── Headings.
        if stripped.startswith("####"):
            document.add_heading(stripped.lstrip("#").strip(), level=4)
            index += 1
            continue
        if stripped.startswith("###"):
            document.add_heading(stripped.lstrip("#").strip(), level=3)
            index += 1
            continue
        if stripped.startswith("##"):
            document.add_heading(stripped.lstrip("#").strip(), level=2)
            index += 1
            continue
        if stripped.startswith("#"):
            index += 1  # the master's own H1 was moved to the title block
            continue

        # ── Lists.
        if stripped.startswith("- "):
            paragraph = document.add_paragraph(style="List Bullet")
            _write_runs(paragraph, stripped[2:])
            index += 1
            continue
        ordered = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if ordered:
            paragraph = document.add_paragraph(style="List Number")
            _write_runs(paragraph, ordered.group(2))
            index += 1
            continue

        # ── Blockquote (the invariant statement).
        if stripped.startswith(">"):
            quoted: List[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quoted.append(lines[index].strip().lstrip(">").strip())
                index += 1
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Inches(0.4)
            paragraph.paragraph_format.right_indent = Inches(0.4)
            joined = " ".join(part for part in quoted if part)
            # The quoted invariant is written in bold in the master; parse the
            # inline markers rather than emitting literal asterisks.
            for token in _INLINE.split(joined):
                if not token:
                    continue
                if token.startswith("**") and token.endswith("**"):
                    run = paragraph.add_run(token[2:-2])
                    run.bold = True
                elif token.startswith("`") and token.endswith("`"):
                    run = paragraph.add_run(token[1:-1])
                    run.font.name = "Consolas"
                    run.font.size = Pt(9)
                else:
                    run = paragraph.add_run(token)
                    run.bold = True
            continue

        # ── Italic caption lines such as "*Table 1. ...*".
        if stripped.startswith("*") and stripped.endswith("*") and len(stripped) > 2:
            paragraph = document.add_paragraph()
            _write_runs(paragraph, stripped.strip("*"), base_italic=True)
            index += 1
            continue

        # ── Plain paragraph.
        if stripped:
            paragraph = document.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            _write_runs(paragraph, stripped)
        index += 1

    if not table_inserted:
        raise RuntimeError("merged Table 1 was never inserted")
    if not figure1_inserted or not figure2_inserted:
        raise RuntimeError("a figure placeholder was never replaced")

    document.add_heading("Code and Artifact Availability", level=2)
    _add_availability(document)

    document.save(OUT)
    return OUT


def _emit_merged_table(document: Document, results: List[Dict[str, object]]) -> None:
    """One table, six rungs: v0.3 rows carry CIs, v0.4.1 rows carry an em dash."""
    caption = document.add_paragraph()
    _write_runs(
        caption,
        "Table 1. Ablation and authorization results on the logged-trace replay. "
        "Attack-labelled trace BLOCK is measured over a 400-trajectory deterministic "
        "prefix; benign trace BLOCK over all 97 benign trajectories. Confidence "
        "intervals are 95% cluster-bootstrap intervals over trajectories, resampled "
        "2,000 times with the trajectory as the unit.",
        base_italic=True,
    )

    table = document.add_table(rows=1, cols=5)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    headers = ["Configuration", "Attack trace BLOCK", "95% CI",
               "Benign trace BLOCK", "95% CI"]
    for cell, header in zip(table.rows[0].cells, headers):
        _set_cell(cell, header, bold=True, align="center")
        _shade(cell, "EFEFEF")

    for row in results:
        name = str(row["config"])
        cells = table.add_row().cells
        is_v041 = row["attack_trace_block_rate"] in (
            results[-2]["attack_trace_block_rate"],
            results[-1]["attack_trace_block_rate"],
        ) and name in ("plus_trust_policy_v0_4", "plus_intent_slots")
        _set_cell(cells[0], _LADDER_LABEL.get(name, name), bold=is_v041)
        _set_cell(cells[1], f"{row['attack_trace_block_rate']*100:.2f}%",
                  bold=is_v041, align="right")
        _set_cell(cells[3], f"{row['benign_trace_block_rate']*100:.2f}%",
                  bold=is_v041, align="right")

        for column, kind, cell in ((2, "attack", cells[2]), (4, "benign", cells[4])):
            ci = _V03_CI.get((name, kind))
            if ci:
                _set_cell(cell, f"[{ci[0]}, {ci[1]}]", align="right")
            else:
                _set_cell(cell, "\u2014", align="right")

    note = document.add_paragraph()
    _write_runs(
        note,
        "Em dashes mark the v0.4.1 rows, for which the frozen artifact records point "
        "estimates only and carries no variance field. Intervals for those rows were "
        "deliberately not transplanted from the v0.3 ladder: doing so would present a "
        "measurement that was never made. Obtaining them requires a separate "
        "bootstrap run over the full six-rung ladder, which is not part of this "
        "release.",
        base_italic=True,
    )


def _emit_figure(document: Document, path: Path, caption: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"figure missing: {path}")
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.add_run().add_picture(str(path), width=Inches(6.1))
    cap = document.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _write_runs(cap, caption, base_italic=True)


def _add_availability(document: Document) -> None:
    document.add_paragraph(
        "The engine, evaluation harness, dataset fingerprint and reproduction "
        "verifier are available in the project repository. The main result artifact "
        "is recorded by SHA-256 3e33c72d230cb7e0788dc4412574054c19dfd496546573698d"
        "73bff7b6a90565, and the evaluated AgentDojo-derived dump by manifest digest "
        "948b94325ae1c8cfbe41bd205fee46b0f500215559ef5cd97a25c27fcf580049 over one "
        "Arrow file of 50,898,680 bytes, 13,913 rows and 10,536 constructed "
        "trajectories. A reproduction regenerates the artifact into a separate file "
        "and compares the two mechanically, with no tolerance; three independent runs "
        "produced byte-identical output. The repository URL, release tag and license "
        "will be inserted at submission, when the venue's anonymity requirements are "
        "known."
    )


def main() -> int:
    if not MASTER.is_file():
        print(f"ERROR: master manuscript missing: {MASTER}", file=sys.stderr)
        return 2
    if not ARTIFACT.is_file():
        print(f"ERROR: canonical artifact missing: {ARTIFACT}", file=sys.stderr)
        return 2
    out = build()
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
