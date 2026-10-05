"""Redraw the two manuscript figures for the v0.4.1 submission DOCX.

Figure 1 is the observability-gap architecture diagram. Figure 2 is the
six-rung results chart, drawn from the committed canonical artifact so the
figure cannot drift from the table.

The old PDF carried two raster figures drawn for the v0.3.1 draft. Figure 2
showed only the four frozen v0.3 rungs, so it had to be redrawn for v0.4.1
rather than reused. Figure 1 carried no numbers, but is redrawn too so that
both figures come from one script with one style and can be regenerated.

Everything here is presentation only. This script reads
benchmark/results/v0_4_trust_pareto.json for the values it plots and writes
each figure twice: a 300 dpi PNG for the DOCX build, and a vector PDF whose
fonts are embedded as TrueType (pdf.fonttype 42) for the USENIX LaTeX build,
where a full-width figure* would otherwise shrink an in-image legend below
legibility. It does not touch the detector, the engine or the artifact.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "benchmark" / "results" / "v0_4_trust_pareto.json"
# A plain `figures/` next to the script's own tree, so the script writes
# somewhere that exists both in the repository and in the anonymous artifact
# snapshot. The previous output directory was a research-notes path that only
# exists in the repository, which broke the snapshot's "regenerate the figures"
# instruction and named a private directory in an uploaded artefact.
OUT_DIR = ROOT / "figures"

# One style for both figures: grayscale, serif, no chartjunk.
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 9,
    "axes.edgecolor": "black",
    "axes.linewidth": 0.8,
    "savefig.dpi": 300,
    "pdf.fonttype": 42,
})

_LABELS = {
    "local_only": "single-event\ngate",
    "plus_output_inspection": "+ output\ninspection",
    "plus_entity_provenance": "+ entity\nprovenance",
    "plus_intent_consistency": "+ intent\nconsistency",
    "plus_trust_policy_v0_4": "+ safe auth.\n(v0.4.1)",
    "plus_intent_slots": "+ intent\nslots",
}


def _load_ladder() -> list:
    with open(ARTIFACT, encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload["results"]


# USENIX Security double-blind review covers PDF metadata, not only visible
# text, and the submission embeds these two figures. Matplotlib's PDF backend
# otherwise writes /Creator, /Producer and /CreationDate by default: the first
# two pin the toolchain and the third carries the local UTC offset, which is a
# geographic hint with no bearing on the experiment. Passing None removes them
# at the source. Metadata is PDF-only; the PNG is consumed by the internal DOCX
# build, and forward-backend kwargs there expect strings.
_FIGURE_PDF_METADATA = {
    "Creator": None,
    "Producer": None,
    "CreationDate": None,
}


def _save(fig, stem: str) -> list[Path]:
    """Write one figure as both a 300 dpi PNG and a vector PDF, same stem."""
    written = []
    for suffix in (".png", ".pdf"):
        out = OUT_DIR / f"{stem}{suffix}"
        kwargs = {"bbox_inches": "tight", "facecolor": "white"}
        if suffix == ".pdf":
            kwargs["metadata"] = _FIGURE_PDF_METADATA
        fig.savefig(out, **kwargs)
        written.append(out)
    return written


def figure_observability_gap() -> list[Path]:
    """Figure 1: the same final call, two different argument origins."""
    fig, ax = plt.subplots(figsize=(7.2, 3.1))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4.4)
    ax.axis("off")

    def box(x: float, y: float, w: float, h: float, text: str, shade: float) -> None:
        patch = FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.06,rounding_size=0.10",
            linewidth=0.9, edgecolor="black",
            facecolor=str(shade),
        )
        ax.add_patch(patch)
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=8.2)

    def arrow(x1: float, y1: float, x2: float, y2: float, style: str = "->") -> None:
        ax.add_patch(FancyArrowPatch(
            (x1, y1), (x2, y2), arrowstyle=style, mutation_scale=11,
            linewidth=0.9, color="black",
        ))

    # Column headings.
    ax.text(2.0, 4.12, "(a) benign execution", ha="center", fontsize=8.6, style="italic")
    ax.text(8.0, 4.12, "(b) attack execution", ha="center", fontsize=8.6, style="italic")

    # (a) benign: operator request names the destination.
    box(0.35, 2.95, 3.3, 0.78, "operator request\nnames destination X", 0.93)
    box(0.35, 1.75, 3.3, 0.78, "tool output\n(trusted content)", 0.98)
    box(0.35, 0.42, 3.3, 0.86, "tool call\nsend_email(to=X)", 0.86)
    arrow(2.0, 2.95, 2.0, 2.53)
    arrow(2.0, 1.75, 2.0, 1.28)

    # (b) attack: destination first appears in untrusted output.
    box(6.35, 2.95, 3.3, 0.78, "operator request\nnames no destination", 0.93)
    box(6.35, 1.75, 3.3, 0.78, "tool output\n(untrusted content,\ninjected instruction)", 0.97)
    box(6.35, 0.42, 3.3, 0.86, "identical tool call\nsend_email(to=X)", 0.86)
    arrow(8.0, 2.95, 8.0, 2.53)
    arrow(8.0, 1.75, 8.0, 1.28)

    # The equality a single-event gate sees, and the distinction it does not.
    ax.add_patch(FancyArrowPatch(
        (3.72, 0.85), (6.28, 0.85), arrowstyle="<->", mutation_scale=10,
        linewidth=0.9, linestyle=(0, (4, 2)), color="black",
    ))
    ax.text(5.0, 1.02, "identical at e$_t$", ha="center", fontsize=8.0)
    ax.text(5.0, 2.05, "origin(X) differs", ha="center", fontsize=8.0)
    ax.add_patch(FancyArrowPatch(
        (4.6, 2.14), (8.4, 2.14), arrowstyle="-", mutation_scale=10,
        linewidth=0.9, linestyle=(0, (1, 2)), color="black",
    ))

    ax.text(5.0, 3.68, "the security-relevant distinction is provenance, not the call",
            ha="center", fontsize=8.4, style="italic")

    written = _save(fig, "figure1_observability_gap")
    plt.close(fig)
    return written


def figure_ladder() -> list[Path]:
    """Figure 2: attack and benign trace blocking across the six rungs."""
    results = _load_ladder()
    names = [r["config"] for r in results]
    attack = [r["attack_trace_block_rate"] * 100 for r in results]
    benign = [r["benign_trace_block_rate"] * 100 for r in results]

    positions = range(len(names))
    width = 0.38

    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    bars_a = ax.bar([p - width / 2 for p in positions], attack, width,
                    label="attack-labelled trace BLOCK (400-trajectory prefix)",
                    color="0.35", edgecolor="black", linewidth=0.6)
    bars_b = ax.bar([p + width / 2 for p in positions], benign, width,
                    label="benign trace BLOCK (97-trajectory census)",
                    color="0.80", edgecolor="black", linewidth=0.6)

    for bars in (bars_a, bars_b):
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f"{height:.1f}",
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 2), textcoords="offset points",
                        ha="center", va="bottom", fontsize=7.2)

    # Mark where the authorization semantics enter, and that the sample bases
    # differ, so a reader does not compare the two series as if symmetric.
    ax.axvline(3.5, color="black", linewidth=0.7, linestyle=(0, (4, 3)))
    ax.text(3.56, ax.get_ylim()[1] * 0.94, "v0.4.1 authorization semantics",
            fontsize=7.4, style="italic", va="top")

    ax.set_xticks(list(positions))
    ax.set_xticklabels([_LABELS.get(n, n) for n in names], fontsize=7.6)
    ax.set_ylabel("trace BLOCK rate (%)")
    ax.set_ylim(0, max(benign) * 1.22)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linewidth=0.4, color="0.85")
    ax.set_axisbelow(True)
    ax.legend(fontsize=7.4, frameon=False, loc="upper left")

    written = _save(fig, "figure2_ladder")
    plt.close(fig)
    return written


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not ARTIFACT.is_file():
        print(f"ERROR: canonical artifact not found: {ARTIFACT}", file=sys.stderr)
        return 2
    for path in figure_observability_gap() + figure_ladder():
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
