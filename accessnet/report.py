"""Figures. Matplotlib only, no network access."""
from __future__ import annotations

import json
import logging

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .config import FIG_DIR, RESULTS_DIR  # noqa: E402

log = logging.getLogger(__name__)

INK = "#1b1b1b"
GREY = "#8a8a8a"
BLUE = "#2b6cb0"
ORANGE = "#dd6b20"
GREEN = "#2f855a"
RED = "#c53030"
PURPLE = "#6b46c1"


def _style(ax, title: str, xlabel: str = "", ylabel: str = "") -> None:
    ax.set_title(title, fontsize=11, color=INK, loc="left", pad=8)
    ax.set_xlabel(xlabel, fontsize=9, color=INK)
    ax.set_ylabel(ylabel, fontsize=9, color=INK)
    ax.tick_params(labelsize=8, colors=INK)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GREY)
    ax.grid(axis="y", color=GREY, alpha=0.25, linewidth=0.6)
    ax.set_axisbelow(True)


def _read(name: str):
    p = RESULTS_DIR / name
    if not p.exists():
        log.warning("skipping figure, %s missing", name)
        return None
    return pd.read_csv(p) if name.endswith(".csv") else json.loads(p.read_text())


def fig_damage_vs_outages() -> None:
    """The central claim: consequence and failure frequency are unrelated."""
    d = _read("elevator_damage_segment.csv")
    if d is None or d.empty:
        return
    s = d.dropna(subset=["damage_pct"])
    s = s[s["damage_pct"] > 0]
    if s.empty or "outages" not in s.columns:
        return
    fig, ax = plt.subplots(figsize=(7.8, 5.4))
    sizes = 18 + 120 * (s["unavailability"].fillna(0) / max(s["unavailability"].max(), 1e-9))
    ax.scatter(s["outages"].fillna(0), s["damage_pct"], s=sizes, alpha=0.75,
               color=BLUE, edgecolor="white", linewidth=0.6)
    top = s.nlargest(6, "damage_pct")
    for r in top.itertuples():
        label = str(getattr(r, "display_name", "") or r.equipment_code)[:26]
        ax.annotate(label, (float(r.outages or 0), float(r.damage_pct)),
                    fontsize=7, color=INK, xytext=(5, 3), textcoords="offset points")
    rho = s[["damage_pct", "outages"]].corr(method="spearman").iloc[0, 1]
    _style(ax, "An elevator's consequence has almost nothing to do with how often it breaks",
           "mean outages per month, trailing 24 months",
           "share of step-free travel this elevator gates, %")
    ax.text(0.98, 0.04, f"Spearman rank correlation {rho:.3f}  (n={len(s)})",
            transform=ax.transAxes, ha="right", fontsize=9, color=RED)
    ax.text(0.98, 0.10, "marker size is time out of service",
            transform=ax.transAxes, ha="right", fontsize=7.5, color=GREY)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "damage_vs_outages.png", dpi=150)
    plt.close(fig)
    log.info("wrote figures/damage_vs_outages.png")


def fig_top_damage(top: int = 18) -> None:
    d = _read("complex_removal_damage.csv")
    if d is None or d.empty:
        return
    s = d.nlargest(top, "flow_lost_pct").sort_values("flow_lost_pct")
    label = s.get("display_name", s["complex_id"].astype(str)).fillna(
        s["complex_id"].astype(str))
    fig, ax = plt.subplots(figsize=(8.6, max(4.5, 0.32 * len(s))))
    ax.barh(label.str.slice(0, 44), s["flow_lost_pct"], color=ORANGE, height=0.72)
    _style(ax, "Step-free travel lost when one complex loses step-free access",
           "percent of all step-free served trips", "")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "top_complex_damage.png", dpi=150)
    plt.close(fig)
    log.info("wrote figures/top_complex_damage.png")


def fig_availability_comparison() -> None:
    c = _read("availability_comparison.csv")
    if c is None or c.empty:
        return
    s = c.dropna(subset=["flow_weighted_availability_pct", "published_availability_pct"])
    if s.empty:
        return
    s = s.sort_values("flow_weighted_availability_pct")
    y = np.arange(len(s))
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.barh(y - 0.19, s["published_availability_pct"], height=0.36,
            color=GREY, label="MTA published, weighted by platform count")
    ax.barh(y + 0.19, s["flow_weighted_availability_pct"], height=0.36,
            color=BLUE, label="this work, weighted by trips actually carried")
    ax.set_yticks(y)
    ax.set_yticklabels(s["borough_name"])
    ax.set_xlim(85, 100)
    _style(ax, "Weighting by riders instead of platforms lowers step-free reliability everywhere",
           "step-free availability, percent", "")
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    for i, r in enumerate(s.itertuples()):
        ax.annotate(f"{r.difference_pts:+.1f} pts", (r.flow_weighted_availability_pct, i + 0.19),
                    fontsize=7.5, color=RED, xytext=(4, -3), textcoords="offset points")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "availability_comparison.png", dpi=150)
    plt.close(fig)
    log.info("wrote figures/availability_comparison.png")


def fig_capital_frontier() -> None:
    res = _read("capital_strategies.json")
    sel = _read("capital_greedy_selection.csv")
    if res is None:
        return
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    names = ["network-aware\n(greedy submodular)", "by ridership", "random"]
    vals = [res.get("greedy_gain_pct"), res.get("ridership_gain_pct"),
            res.get("random_mean_gain_pct")]
    axes[0].bar(names, vals, color=[BLUE, GREEN, GREY], width=0.6)
    _style(axes[0], f"Step-free travel unlocked by {res.get('k')} new accessible complexes",
           "", "gain, percent of current step-free trips")
    for i, v in enumerate(vals):
        if v is not None:
            axes[0].annotate(f"{v:.1f}%", (i, v), ha="center", fontsize=9,
                             color=INK, xytext=(0, 3), textcoords="offset points")

    eq = _read("capital_equity_split.csv")
    if eq is not None and not eq.empty:
        e = eq.sort_values("n_selected", ascending=False)
        axes[1].bar(e["borough"].astype(str), e["n_selected"], color=PURPLE, width=0.6)
        _style(axes[1], "Where the network-aware plan puts those stations",
               "", "complexes selected")
        for i, r in enumerate(e.itertuples()):
            axes[1].annotate(f"{int(r.n_candidates)} candidates",
                             (i, r.n_selected), ha="center", fontsize=7.5, color=GREY,
                             xytext=(0, 4), textcoords="offset points")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "capital_strategies.png", dpi=150)
    plt.close(fig)
    log.info("wrote figures/capital_strategies.png")


def fig_coverage_gap() -> None:
    h = _read("headline_coverage.json")
    if h is None:
        return
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    labels = ["complexes\nstep-free", "station pairs\nstep-free served",
              "weekday trips\nstep-free served"]
    vals = [h.get("pct_complexes_step_free"), h.get("pct_pairs_step_free_served"),
            h.get("pct_trips_step_free_served")]
    ax.bar(labels, vals, color=[GREY, ORANGE, BLUE], width=0.58)
    for i, v in enumerate(vals):
        if v is not None:
            ax.annotate(f"{v:.1f}%", (i, v), ha="center", fontsize=10, color=INK,
                        xytext=(0, 3), textcoords="offset points")
    _style(ax, "Counting stations or pairs understates how much travel is step-free served",
           "", "percent")
    f = h.get("pair_count_understates_by_factor")
    if f:
        ax.text(0.98, 0.9, f"trips / pairs = {f}x", transform=ax.transAxes,
                ha="right", fontsize=9, color=RED)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "coverage_gap.png", dpi=150)
    plt.close(fig)
    log.info("wrote figures/coverage_gap.png")


def fig_asset_age() -> None:
    c = _read("elevator_criticality.csv")
    if c is None or c.empty or "service_life" not in c.columns:
        return
    d = c.copy()
    inst = pd.to_datetime(d.get("original_installation_date"), errors="coerce")
    d["age"] = (pd.Timestamp("2026-10-23") - inst).dt.days / 365.25
    d["life"] = pd.to_numeric(d["service_life"], errors="coerce")
    d = d.dropna(subset=["age", "life"])
    if d.empty:
        return
    fig, ax = plt.subplots(figsize=(7.6, 5.0))
    sole = d["sole_on_segment"].fillna(False).astype(bool)
    ax.scatter(d.loc[~sole, "age"], d.loc[~sole, "life"], s=26, alpha=0.6,
               color=GREY, edgecolor="white", linewidth=0.5, label="has a redundant peer")
    ax.scatter(d.loc[sole, "age"], d.loc[sole, "life"], s=34, alpha=0.85,
               color=RED, edgecolor="white", linewidth=0.5,
               label="sole elevator on its vertical segment")
    lim = float(min(d["age"].max(), d["life"].max()) * 1.05)
    ax.plot([0, lim], [0, lim], color=INK, linewidth=0.9, linestyle="--")
    past = int((d["age"] > d["life"]).sum())
    _style(ax, "Elevator age against stated service life",
           "age in years", "stated service life in years")
    ax.text(0.98, 0.06, f"{past} of {len(d)} are past their stated service life",
            transform=ax.transAxes, ha="right", fontsize=9, color=RED)
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "asset_age.png", dpi=150)
    plt.close(fig)
    log.info("wrote figures/asset_age.png")


def make_figures() -> None:
    fig_coverage_gap()
    fig_damage_vs_outages()
    fig_top_damage()
    fig_availability_comparison()
    fig_capital_frontier()
    fig_asset_age()
