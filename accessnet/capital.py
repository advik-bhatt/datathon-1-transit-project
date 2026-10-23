"""Which stations should get elevators next, if the goal is reachable travel.

The MTA publishes the criteria it uses to choose stations for accessibility
work: systemwide coverage, transfer points and terminals, proximity to major
activity centres, ridership, demographics, and cost and constructability. None
of those six is a network-reachability term. "Does this selection maximise the
step-free travel it unlocks" therefore has no published answer.

Adding one station to the step-free set does not add a fixed amount of travel.
It adds every pair between that station and the stations already step-free, so
the gain of a set is not the sum of its members' individual gains and the
problem is submodular. Greedy selection on a submodular objective carries the
standard (1 - 1/e) guarantee, which is why it is used here rather than ranking
stations by their standalone gain.

What this module deliberately does NOT do is score the MTA's actual capital
plan. The published station lists found during this work did not reconcile with
each other, and scoring the agency against a list we could not verify would be
worse than not scoring it. The comparison is therefore against two baselines
that are fully computable from open data: selecting by complex ridership, which
is the obvious heuristic and is close to what the published criteria imply, and
selecting at random. `score_selection` accepts any explicit list, so a verified
plan can be dropped in later.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .config import NORTH, SOUTH
from .damage import ReachabilityModel

log = logging.getLogger(__name__)


def _with_added(model: ReachabilityModel, added: set[int]) -> float:
    """Served flow if `added` complexes became step-free in both directions."""
    return model.served_flow(added=frozenset(int(x) for x in added))


def candidate_complexes(cx_access: pd.DataFrame,
                        in_graph: set[int] | None = None) -> list[int]:
    """Complexes that are not step-free in either direction."""
    c = cx_access.copy()
    c["complex_id"] = pd.to_numeric(c["complex_id"], errors="coerce")
    out = c.loc[~c["step_free_any"].fillna(False), "complex_id"].dropna().astype(int)
    ids = sorted(set(out))
    if in_graph is not None:
        ids = [i for i in ids if i in in_graph]
    return ids


def greedy_selection(model: ReachabilityModel, candidates: list[int],
                     k: int = 25, progress_every: int = 5) -> pd.DataFrame:
    """Greedy submodular maximisation of step-free served travel."""
    chosen: list[int] = []
    rows = []
    base = model.baseline()
    current = base
    pool = list(candidates)
    for step in range(1, k + 1):
        best, best_val = None, current
        for c in pool:
            val = _with_added(model, set(chosen) | {c})
            if val > best_val:
                best, best_val = c, val
        if best is None:
            log.info("no candidate adds flow at step %d; stopping", step)
            break
        chosen.append(best)
        pool.remove(best)
        rows.append({
            "step": step,
            "complex_id": best,
            "served_flow": best_val,
            "marginal_gain": best_val - current,
            "cumulative_gain": best_val - base,
            "cumulative_gain_pct_of_baseline": 100.0 * (best_val - base) / base,
        })
        current = best_val
        if step % progress_every == 0:
            log.info("greedy step %d/%d: +%.2f%% cumulative",
                     step, k, 100.0 * (current - base) / base)
    return pd.DataFrame(rows)


def score_selection(model: ReachabilityModel, selection: list[int]) -> dict:
    """Total step-free travel unlocked by an explicit set of complexes."""
    base = model.baseline()
    val = _with_added(model, set(int(s) for s in selection))
    return {
        "n_selected": len(selection),
        "served_flow": val,
        "gain": val - base,
        "gain_pct_of_baseline": round(100.0 * (val - base) / base, 3) if base > 0 else np.nan,
    }


def ridership_baseline(model: ReachabilityModel, candidates: list[int],
                       ridership: pd.DataFrame, k: int = 25) -> tuple[list[int], dict]:
    """Select the k busiest inaccessible complexes, the obvious heuristic."""
    r = ridership.groupby("complex_id", as_index=False)["riders"].sum()
    r = r[r["complex_id"].isin(candidates)].sort_values("riders", ascending=False)
    pick = r["complex_id"].head(k).astype(int).tolist()
    return pick, score_selection(model, pick)


def random_baseline(model: ReachabilityModel, candidates: list[int], k: int = 25,
                    n_draws: int = 30, seed: int = 5) -> dict:
    """Random selection, to show what the structure is worth at all."""
    rng = np.random.default_rng(seed)
    gains = []
    for _ in range(n_draws):
        pick = rng.choice(candidates, size=min(k, len(candidates)), replace=False)
        gains.append(score_selection(model, [int(p) for p in pick])["gain"])
    base = model.baseline()
    g = np.asarray(gains, dtype=float)
    return {
        "n_draws": n_draws,
        "mean_gain": float(g.mean()),
        "mean_gain_pct_of_baseline": round(100.0 * float(g.mean()) / base, 3),
        "best_draw_gain_pct": round(100.0 * float(g.max()) / base, 3),
        "worst_draw_gain_pct": round(100.0 * float(g.min()) / base, 3),
    }


def compare_strategies(model: ReachabilityModel, cx_access: pd.DataFrame,
                       ridership: pd.DataFrame, k: int = 25) -> dict:
    """Greedy network-aware selection against ridership and random selection."""
    in_graph = set(model.graphs[NORTH].nodes) | set(model.graphs[SOUTH].nodes)
    cands = candidate_complexes(cx_access, in_graph=in_graph)
    log.info("%d inaccessible complexes in the graph are candidates", len(cands))

    greedy = greedy_selection(model, cands, k=k)
    greedy_gain = float(greedy["cumulative_gain"].iloc[-1]) if not greedy.empty else 0.0
    rid_pick, rid_score = ridership_baseline(model, cands, ridership, k=k)
    rnd = random_baseline(model, cands, k=k)
    base = model.baseline()

    return {
        "k": k,
        "n_candidates": len(cands),
        "baseline_served_flow": base,
        "greedy_gain_pct": round(100.0 * greedy_gain / base, 3),
        "ridership_gain_pct": rid_score["gain_pct_of_baseline"],
        "random_mean_gain_pct": rnd["mean_gain_pct_of_baseline"],
        "ridership_share_of_greedy": round(100.0 * rid_score["gain"] / greedy_gain, 1)
        if greedy_gain > 0 else np.nan,
        "random_share_of_greedy": round(100.0 * rnd["mean_gain"] / greedy_gain, 1)
        if greedy_gain > 0 else np.nan,
        "greedy_selection": greedy["complex_id"].astype(int).tolist(),
        "ridership_selection": rid_pick,
        "overlap_greedy_ridership": len(set(greedy["complex_id"].astype(int)) & set(rid_pick)),
        "note": "The MTA's own capital-plan station list is deliberately not "
                "scored here: the public counts found during this work did not "
                "reconcile, and scoring the agency against an unverified list "
                "would be worse than not scoring it. Pass a verified list to "
                "score_selection to add that comparison.",
    }


def equity_split(selection: list[int], cx_access: pd.DataFrame) -> pd.DataFrame:
    """Borough composition of a selection, so a gain is not just Manhattan.

    A reachability-optimal plan concentrates on transfer hubs, and the hubs are
    in Manhattan. Reporting the split is how that failure mode stays visible
    rather than being discovered later.
    """
    c = cx_access.copy()
    c["complex_id"] = pd.to_numeric(c["complex_id"], errors="coerce")
    sel = c[c["complex_id"].isin([int(s) for s in selection])]
    out = sel.groupby("borough", as_index=False).size().rename(columns={"size": "n_selected"})
    allc = c[~c["step_free_any"].fillna(False)].groupby(
        "borough", as_index=False).size().rename(columns={"size": "n_candidates"})
    m = out.merge(allc, on="borough", how="outer").fillna(0)
    m["pct_of_candidates_chosen"] = (
        100.0 * m["n_selected"] / m["n_candidates"].where(m["n_candidates"] > 0)
    ).round(1)
    return m.sort_values("n_selected", ascending=False).reset_index(drop=True)
