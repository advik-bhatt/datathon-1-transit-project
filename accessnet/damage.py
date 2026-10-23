"""What an elevator outage actually costs, measured in trips rather than hours.

The published way to rank elevators is by how often they break. That ranks
machines. This module ranks them by how much step-free travel they gate, which
ranks consequences, and the two orderings turn out to be almost unrelated.

The quantity is flow-weighted step-free reachability. A trip from complex `o`
to complex `d` is step-free served when there is a direction of travel in which
the origin platform is step-free, the destination platform is step-free, and
the destination is reachable from the origin on the network in that direction.
Intermediate complexes need not be accessible, because the rider stays aboard.
Each served pair is weighted by its actual estimated ridership, taken from the
MTA's hourly origin-destination estimates summed over a year of weekdays:
177,998 complex pairs carrying 222.5 million trips.

Removing a complex from the step-free set removes it only as an origin and a
destination. It stays passable. Modelling it as a cut in the graph would invent
damage that no rider experiences.

Two damage models are reported side by side, because the first depends on a
free-text parse and the second does not:

    segment   an elevator outage disables its complex only when that elevator
              is the sole server of its vertical segment. This is the model
              the inventory notes support.
    any       any elevator outage disables its complex. A deliberately crude
              upper bound, included so a reader can see how much the parse is
              carrying.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .config import NORTH, SOUTH
from .graph import build_graph, reachable_pairs, step_free_nodes

log = logging.getLogger(__name__)


def flow_matrix(od: pd.DataFrame) -> pd.DataFrame:
    """Clean the origin-destination pair flows."""
    f = od.copy()
    for c in ("o", "d", "flow"):
        f[c] = pd.to_numeric(f[c], errors="coerce")
    f = f.dropna(subset=["o", "d", "flow"])
    f = f[(f["flow"] > 0) & (f["o"] != f["d"])]
    f["o"] = f["o"].astype(int)
    f["d"] = f["d"].astype(int)
    return f.reset_index(drop=True)


class ReachabilityModel:
    """Precomputed reachability, so hypothetical outages are cheap to score.

    The important observation is that network reachability does not depend on
    which stations are step-free. Whether a train can get from one complex to
    another is a property of the graph; accessibility only decides whether a
    rider can board and alight at the ends. So reachability is computed once,
    per direction, for every origin-destination pair in the flow matrix, and
    every later question becomes a boolean mask over 177,998 pairs.

    Without that split a greedy capital search re-runs thousands of full graph
    sweeps and takes twenty minutes. With it, one evaluation is a millisecond.
    """

    def __init__(self, edges: pd.DataFrame, cx_access: pd.DataFrame,
                 od: pd.DataFrame):
        import networkx as nx

        self.graphs = {d: build_graph(edges, direction=d) for d in (NORTH, SOUTH)}
        self.step_free = {d: step_free_nodes(cx_access, d) for d in (NORTH, SOUTH)}
        self.flow = flow_matrix(od)
        self.total_flow = float(self.flow["flow"].sum())

        self._o = self.flow["o"].to_numpy(dtype=np.int64)
        self._d = self.flow["d"].to_numpy(dtype=np.int64)
        self._w = self.flow["flow"].to_numpy(dtype=float)
        all_nodes = set(self.graphs[NORTH].nodes) | set(self.graphs[SOUTH].nodes)
        hi = max(int(self._o.max()), int(self._d.max()),
                 max(all_nodes) if all_nodes else 0)
        self._size = hi + 1

        self._reach_mask: dict[str, np.ndarray] = {}
        for d in (NORTH, SOUTH):
            g = self.graphs[d]
            desc = {n: nx.descendants(g, n) for n in g.nodes}
            mask = np.fromiter(
                ((dd in desc.get(o, ())) for o, dd in zip(self._o, self._d)),
                dtype=bool, count=len(self.flow),
            )
            self._reach_mask[d] = mask
            log.info("direction %s: %d of %d flow pairs are reachable at all",
                     d, int(mask.sum()), len(mask))
        self._cache: dict[tuple, float] = {}

    def _flags(self, usable: set[int]) -> np.ndarray:
        f = np.zeros(self._size, dtype=bool)
        idx = np.fromiter((u for u in usable if 0 <= u < self._size),
                          dtype=np.int64, count=-1)
        if idx.size:
            f[idx] = True
        return f

    def served_flow(self, disabled=None, added=None) -> float:
        """Ridership on pairs that remain step-free served.

        `disabled` names complexes that have lost step-free access, for
        instance because an elevator is out. `added` names complexes that have
        gained it, which is what the capital-planning search varies. A disabled
        complex stays passable: it stops being a usable origin or destination
        but riders still travel through it, so modelling it as a cut in the
        graph would invent damage nobody experiences.
        """
        dkey = frozenset(int(x) for x in (disabled or ()))
        akey = frozenset(int(x) for x in (added or ()))
        key = (dkey, akey)
        if key in self._cache:
            return self._cache[key]
        served = np.zeros(len(self.flow), dtype=bool)
        for d in (NORTH, SOUTH):
            usable = (self.step_free[d] | akey) - dkey
            flags = self._flags(usable)
            served |= self._reach_mask[d] & flags[self._o] & flags[self._d]
        val = float(self._w[served].sum())
        self._cache[key] = val
        return val

    def baseline(self) -> float:
        return self.served_flow()

    def served_pairs(self, disabled=None) -> int:
        """Count of served pairs, for comparison with pair-count analyses."""
        dkey = {int(x) for x in (disabled or ())}
        served = np.zeros(len(self.flow), dtype=bool)
        for d in (NORTH, SOUTH):
            flags = self._flags(self.step_free[d] - dkey)
            served |= self._reach_mask[d] & flags[self._o] & flags[self._d]
        return int(served.sum())


def complex_removal_damage(model: ReachabilityModel,
                           candidates: list[int] | None = None) -> pd.DataFrame:
    """Flow lost when each single complex loses step-free access.

    This is the expensive sweep, and it is the only one needed: a single
    elevator outage can disable at most its own complex, so every elevator's
    damage is one of these numbers.
    """
    base = model.baseline()
    cands = candidates if candidates is not None else sorted(
        model.step_free[NORTH] | model.step_free[SOUTH]
    )
    rows = []
    for i, c in enumerate(cands, 1):
        lost = base - model.served_flow(frozenset({int(c)}))
        rows.append({
            "complex_id": int(c),
            "flow_lost": lost,
            "flow_lost_pct": 100.0 * lost / base if base > 0 else np.nan,
        })
        if i % 40 == 0:
            log.info("complex sweep %d/%d", i, len(cands))
    out = pd.DataFrame(rows)
    out["baseline_served_flow"] = base
    return out.sort_values("flow_lost", ascending=False).reset_index(drop=True)


def elevator_damage(criticality: pd.DataFrame, cx_damage: pd.DataFrame,
                    unavail: pd.DataFrame | None = None,
                    model_name: str = "segment") -> pd.DataFrame:
    """Per-elevator reachability damage, and its expected annual cost.

    `model_name` selects which damage model applies:
      "segment"  the elevator disables its complex only if it is the sole
                 server of its vertical segment;
      "any"      every elevator disables its complex.
    """
    if model_name not in ("segment", "any"):
        raise ValueError("model_name must be 'segment' or 'any'")
    c = criticality.copy()
    c["complex_id"] = pd.to_numeric(c["complex_id"], errors="coerce")
    d = cx_damage[["complex_id", "flow_lost", "flow_lost_pct"]]
    out = c.merge(d, on="complex_id", how="left")
    disables = out["sole_on_segment"] if model_name == "segment" else True
    out["disables_complex"] = disables
    out["damage_flow"] = np.where(out["disables_complex"],
                                  out["flow_lost"].fillna(0.0), 0.0)
    out["damage_pct"] = np.where(out["disables_complex"],
                                 out["flow_lost_pct"].fillna(0.0), 0.0)
    out["damage_model"] = model_name

    if unavail is not None and not unavail.empty:
        u = unavail[["equipment_code", "unavailability", "peak_unavailability",
                     "outages", "entrapments", "imputed_availability"]]
        out = out.merge(u, on="equipment_code", how="left")
        out["unavailability"] = out["unavailability"].fillna(
            float(unavail["unavailability"].median())
        )
        # Expected trips denied per year: how much travel this machine gates,
        # multiplied by the fraction of time it is actually down.
        out["expected_trips_denied"] = out["damage_flow"] * out["unavailability"]
        out["expected_trips_denied_peak"] = (
            out["damage_flow"] * out["peak_unavailability"].fillna(out["unavailability"])
        )
    return out.sort_values("damage_flow", ascending=False).reset_index(drop=True)


def monte_carlo(model: ReachabilityModel, criticality: pd.DataFrame,
                unavail: pd.DataFrame, n_draws: int = 400,
                seed: int = 11, model_name: str = "segment") -> dict:
    """Expected step-free reachability under simultaneous independent outages.

    Single-asset damage understates the problem whenever two machines gate
    overlapping travel. Each draw takes every elevator down independently with
    its own published unavailability, maps that to the set of complexes that
    lose step-free access, and recomputes served flow.

    Independence is an assumption and a questionable one: outages cluster, by
    weather, by maintenance campaign and by shared equipment vintage. It makes
    this an optimistic estimate of the tail and a reasonable one for the mean.
    """
    rng = np.random.default_rng(seed)
    c = criticality.merge(
        unavail[["equipment_code", "unavailability"]], on="equipment_code", how="left"
    )
    c["unavailability"] = c["unavailability"].fillna(float(unavail["unavailability"].median()))
    if model_name == "segment":
        c = c[c["sole_on_segment"]]
    p = c["unavailability"].to_numpy(dtype=float)
    cx = c["complex_id"].to_numpy()
    base = model.baseline()

    served = np.empty(n_draws, dtype=float)
    n_down = np.empty(n_draws, dtype=int)
    for i in range(n_draws):
        down = rng.random(len(p)) < p
        disabled = frozenset(int(x) for x in cx[down] if np.isfinite(x))
        served[i] = model.served_flow(disabled)
        n_down[i] = int(down.sum())
    loss = 100.0 * (base - served) / base if base > 0 else np.full(n_draws, np.nan)
    return {
        "damage_model": model_name,
        "n_draws": int(n_draws),
        "baseline_served_flow": base,
        "mean_pct_flow_lost": round(float(loss.mean()), 3),
        "median_pct_flow_lost": round(float(np.median(loss)), 3),
        "p90_pct_flow_lost": round(float(np.quantile(loss, 0.90)), 3),
        "p99_pct_flow_lost": round(float(np.quantile(loss, 0.99)), 3),
        "worst_draw_pct_flow_lost": round(float(loss.max()), 3),
        "mean_elevators_down": round(float(n_down.mean()), 2),
        "max_elevators_down": int(n_down.max()),
        "independence_assumed": True,
    }


def ranking_comparison(dmg: pd.DataFrame, unavail: pd.DataFrame,
                       ridership: pd.DataFrame | None = None) -> pd.DataFrame:
    """Does ranking by consequence agree with ranking by the published signals?

    This is the falsifiable claim of the project. If flow-weighted criticality
    simply reproduced the outage-count ranking, the model would be decoration.
    """
    d = dmg.merge(
        unavail[["equipment_code", "outages", "unscheduled", "unavailability",
                 "entrapments"]].rename(columns={"outages": "outages_mean"}),
        on="equipment_code", how="left", suffixes=("", "_u"),
    )
    if ridership is not None and not ridership.empty:
        r = ridership.groupby("complex_id", as_index=False)["riders"].sum()
        d = d.merge(r, on="complex_id", how="left")

    pairs = [
        ("damage_flow", "outages_mean", "reachability damage vs mean monthly outages"),
        ("damage_flow", "unavailability", "reachability damage vs unavailability"),
        ("damage_flow", "entrapments", "reachability damage vs entrapments"),
    ]
    if "expected_trips_denied" in d.columns:
        pairs.append(("expected_trips_denied", "outages_mean",
                      "expected trips denied vs mean monthly outages"))
    if "riders" in d.columns:
        pairs.append(("damage_flow", "riders",
                      "reachability damage vs complex ridership"))
    rows = []
    for a, b, label in pairs:
        s = d[[a, b]].dropna()
        if len(s) < 20 or s[a].std() == 0 or s[b].std() == 0:
            continue
        rows.append({
            "comparison": label,
            "n": int(len(s)),
            "spearman": round(float(s[a].corr(s[b], method="spearman")), 3),
            "pearson": round(float(s[a].corr(s[b], method="pearson")), 3),
        })
    return pd.DataFrame(rows)


def flow_weighted_availability(model: ReachabilityModel, criticality: pd.DataFrame,
                               unavail: pd.DataFrame,
                               model_name: str = "segment") -> dict:
    """The metric the agency does not publish: availability weighted by riders.

    MTA publishes accessible-platform availability aggregated by borough and
    weighted by platform count. Weighting by the travel each platform actually
    carries is a better estimator of rider harm, and it is computable from the
    same open data.
    """
    mc = monte_carlo(model, criticality, unavail, n_draws=200, model_name=model_name)
    return {
        "flow_weighted_step_free_availability_pct": round(100.0 - mc["mean_pct_flow_lost"], 3),
        "expected_pct_of_step_free_trips_lost": mc["mean_pct_flow_lost"],
        "p90_pct_lost": mc["p90_pct_flow_lost"],
        "damage_model": model_name,
        "baseline_served_flow": mc["baseline_served_flow"],
    }
