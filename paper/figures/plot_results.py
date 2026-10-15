"""Render the existing RouteBench v13 diagnostic results for the appendix."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt

from audit_panel_alignment import require_matplotlib_panel_alignment


ROOT = Path(__file__).resolve().parent

mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "font.size": 7,
        "axes.spines.right": False,
        "axes.spines.top": False,
        "axes.linewidth": 0.7,
        "xtick.major.width": 0.7,
        "ytick.major.width": 0.7,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    }
)


def read_csv(name: str) -> list[dict[str, str]]:
    with (ROOT / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def pct(row: dict[str, str], key: str) -> float:
    return float(row[key])


def draw() -> None:
    models = read_csv("formal_results.csv")
    lengths = read_csv("qwen3_14b_length.csv")
    ablation = read_csv("component_ablation.csv")

    # Keep the model labels compact while preserving canonical names in the table.
    labels = [row["model"] for row in models]
    short = {
        "DeepSeek-R1-Distill-Qwen-14B": "DeepSeek-R1 14B",
        "OpenChat3.6-8B": "OpenChat3.6",
        "InternLM2.5-7B": "InternLM2.5",
    }
    display = [short.get(label, label) for label in labels]
    y = list(range(len(models)))

    blue = "#2f5d8a"
    teal = "#3a8f8b"
    red = "#b55454"
    gray = "#9099a2"
    accent = "#d28b45"

    fig, axes = plt.subplots(2, 2, figsize=(7.1, 4.9), constrained_layout=True)
    ax_a, ax_b, ax_c, ax_d = axes.ravel()
    # Overlay points instead of stacking the two rates, which keeps both on the same scale.
    ax_a.barh(y, [pct(row, "optimal_attempts") for row in models], color=blue, label="Optimal")
    ax_a.scatter(
        [pct(row, "capable_cases") for row in models],
        y,
        color=teal,
        s=15,
        zorder=3,
        label="Capable cases",
    )
    ax_a.set_yticks(y, display)
    ax_a.invert_yaxis()
    ax_a.set_xlim(0, 100)
    ax_a.set_xlabel("Rate (%)")
    ax_a.set_title("Model performance", loc="left", fontsize=8, fontweight="bold")
    ax_a.legend(loc="lower right", frameon=False, handlelength=1.4)

    ax_b.barh(y, [pct(row, "attack_path") for row in models], color=red)
    ax_b.set_yticks(y, display)
    ax_b.invert_yaxis()
    ax_b.set_xlim(0, 25)
    ax_b.set_xlabel("Attack-path attempts (%)")
    ax_b.set_title("Unsafe-branch selection", loc="left", fontsize=8, fontweight="bold")

    x = [int(row["safe_route_length"]) for row in lengths]
    ax_c.plot(x, [pct(row, "optimal_attempts") for row in lengths], marker="o", color=blue, label="Optimal")
    ax_c.plot(x, [pct(row, "capable_cases") for row in lengths], marker="o", color=teal, label="Capable")
    ax_c.plot(x, [pct(row, "attack_path") for row in lengths], marker="o", color=red, label="Attack")
    ax_c.set_xticks(x, [str(item) for item in x])
    ax_c.set_ylim(0, 100)
    ax_c.set_xlabel("Safe-route length")
    ax_c.set_ylabel("Rate (%)")
    ax_c.set_title("Qwen3-14B by route length", loc="left", fontsize=8, fontweight="bold")
    ax_c.set_xlim(0.85, 4.8)
    ax_c.text(4.15, 76.5, "Optimal", color=blue, va="center", fontsize=6.5)
    ax_c.text(4.15, 85.5, "Capable", color=teal, va="center", fontsize=6.5)
    ax_c.text(4.15, 5.4, "Attack", color=red, va="center", fontsize=6.5)
    ax_c.grid(axis="y", color="#d9dde1", linewidth=0.5)

    conditions = [row["condition"].replace("_", " ") for row in ablation]
    order = list(range(len(ablation)))
    ax_d.barh(order, [pct(row, "capable_cases") for row in ablation], color=accent, alpha=0.85, label="Capable")
    ax_d.scatter(
        [pct(row, "attack_path") for row in ablation],
        order,
        color=red,
        s=15,
        zorder=3,
        label="Attack",
    )
    ax_d.set_yticks(order, conditions)
    ax_d.invert_yaxis()
    ax_d.set_xlim(0, 100)
    ax_d.set_xlabel("Rate (%)")
    ax_d.set_title("Graph-component ablation", loc="left", fontsize=8, fontweight="bold")
    ax_d.legend(loc="lower right", frameon=False, handlelength=1.4)

    for label, ax in zip("abcd", axes.ravel()):
        ax.text(
            -0.2,
            1.0,
            label,
            transform=ax.transAxes,
            fontsize=9,
            fontweight="bold",
            va="top",
            ha="left",
        )
        ax.tick_params(labelsize=6, length=2.5, pad=2)
        ax.xaxis.label.set_size(7)
        ax.yaxis.label.set_size(7)

    output = ROOT / "formal_diagnostics"
    require_matplotlib_panel_alignment(
        fig,
        json_out=f"{output}.alignment.json",
        overlay_svg=f"{output}.alignment.svg",
        tolerance_pt=1.5,
        gutter_tolerance_pt=1.5,
        require_panel_labels=True,
        strict=True,
    )
    fig.savefig(f"{output}.pdf", bbox_inches="tight")
    fig.savefig(f"{output}.svg", bbox_inches="tight")
    fig.savefig(f"{output}.png", dpi=600, bbox_inches="tight")
    fig.savefig(f"{output}.tiff", dpi=600, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    draw()
