"""The metric the agency publishes, and the one it does not.

MTA publishes two accessibility reliability numbers:

* `rc78-7x78`, per-unit monthly availability, which measures machines;
* `thh2-syn7`, accessible-platform availability aggregated by borough and
  weighted by platform count, which measures platforms.

Neither measures riders. A platform that carries forty thousand trips a day and
one that carries four hundred count the same, and a station that is the only
step-free way into a borough counts the same as one with three step-free
neighbours. This module computes the flow-weighted version, which weights every
step-free origin-destination pair by the travel it actually carries, and puts it
directly beside the agency's own numbers so the two can be compared rather than
asserted over.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def mta_published_platform_availability(platform_av: pd.DataFrame,
                                        months: int = 12) -> pd.DataFrame:
    """The agency's own borough-level accessible-platform availability."""
    df = platform_av.copy()
    df["month"] = pd.to_datetime(df["month"], errors="coerce")
    for c in ("availability", "platform_count", "minutes_platforms_available",
              "minutes_platforms_in_service"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["month", "availability"])
    end = df["month"].max()
    win = df[df["month"] > end - pd.DateOffset(months=months)]
    g = win.groupby("borough", as_index=False).agg(
        n_months=("month", "size"),
        mean_platform_count=("platform_count", "mean"),
        published_availability=("availability", "mean"),
    )
    g["published_unavailability_pct"] = (100.0 * (1.0 - g["published_availability"])).round(3)
    g["published_availability_pct"] = (100.0 * g["published_availability"]).round(3)
    g["window_end"] = end
    return g.sort_values("published_availability_pct").reset_index(drop=True)


def flow_weighted_by_borough(model, criticality: pd.DataFrame,
                             unavail: pd.DataFrame, cx_access: pd.DataFrame,
                             n_draws: int = 200, seed: int = 17,
                             model_name: str = "segment") -> pd.DataFrame:
    """Expected share of step-free travel lost, attributed by borough.

    A trip is attributed to the borough of its origin complex, so the number
    answers "how much of the step-free travel starting in this borough is
    actually served", which is the rider-facing question.
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

    bor = cx_access.copy()
    bor["complex_id"] = pd.to_numeric(bor["complex_id"], errors="coerce")
    bmap = dict(zip(bor["complex_id"].astype("Int64"), bor["borough"]))
    origin_borough = pd.Series(model.flow["o"]).map(bmap).fillna("unknown")

    base_served = _served_mask(model, frozenset())
    base_by_b = (model.flow["flow"] * base_served).groupby(origin_borough).sum()

    acc = pd.DataFrame(0.0, index=base_by_b.index, columns=["lost"])
    for _ in range(n_draws):
        down = rng.random(len(p)) < p
        disabled = frozenset(int(x) for x in cx[down] if np.isfinite(x))
        served = _served_mask(model, disabled)
        lost = (model.flow["flow"] * (base_served & ~served)).groupby(origin_borough).sum()
        acc["lost"] = acc["lost"].add(lost, fill_value=0.0)
    acc["lost"] /= n_draws

    out = pd.DataFrame({
        "borough": base_by_b.index,
        "baseline_step_free_flow": base_by_b.to_numpy(),
        "expected_flow_lost": acc["lost"].reindex(base_by_b.index).to_numpy(),
    })
    out["flow_weighted_availability_pct"] = (
        100.0 * (1.0 - out["expected_flow_lost"] / out["baseline_step_free_flow"].where(
            out["baseline_step_free_flow"] > 0))
    ).round(3)
    out["expected_pct_lost"] = (100.0 - out["flow_weighted_availability_pct"]).round(3)
    out["damage_model"] = model_name
    out["n_draws"] = n_draws
    return out.sort_values("flow_weighted_availability_pct").reset_index(drop=True)


def _served_mask(model, disabled: frozenset) -> pd.Series:
    """Boolean mask of served pairs, reusing the model's precomputed masks."""
    served = np.zeros(len(model.flow), dtype=bool)
    for d, mask in model._reach_mask.items():
        usable = model.step_free[d] - {int(x) for x in disabled}
        flags = model._flags(usable)
        served |= mask & flags[model._o] & flags[model._d]
    return pd.Series(served, index=model.flow.index)


def compare_to_published(flow_weighted: pd.DataFrame,
                         published: pd.DataFrame) -> pd.DataFrame:
    """Put the two measures side by side, per borough.

    The boroughs are coded differently in the two tables (one uses letters,
    the other full names), so the mapping is explicit rather than inferred.
    """
    code = {"M": "Manhattan", "Bk": "Brooklyn", "Bx": "Bronx",
            "Q": "Queens", "SI": "Staten Island"}
    fw = flow_weighted.copy()
    fw["borough_name"] = fw["borough"].map(code).fillna(fw["borough"])
    pub = published.copy()
    pub["borough_name"] = pub["borough"].astype(str).str.strip()
    m = fw.merge(pub[["borough_name", "published_availability_pct",
                      "mean_platform_count", "n_months"]],
                 on="borough_name", how="outer")
    m["difference_pts"] = (
        m["flow_weighted_availability_pct"] - m["published_availability_pct"]
    ).round(3)
    return m.sort_values("flow_weighted_availability_pct").reset_index(drop=True)


def headline(model, cx_access: pd.DataFrame) -> dict:
    """Coverage of the step-free network, by pairs and by travel.

    The gap between these two is the point: step-free stations are
    disproportionately busy, so counting station pairs understates how much
    travel is actually step-free served by roughly a factor of three.
    """
    total_pairs = len(model.flow)
    served_pairs = model.served_pairs()
    base = model.baseline()
    return {
        "complexes": int(len(cx_access)),
        "complexes_step_free_any_direction": int(cx_access["step_free_any"].sum()),
        "pct_complexes_step_free": round(100.0 * float(cx_access["step_free_any"].mean()), 2),
        "od_pairs_with_flow": total_pairs,
        "od_pairs_step_free_served": served_pairs,
        "pct_pairs_step_free_served": round(100.0 * served_pairs / total_pairs, 2),
        "total_weekday_trips": round(model.total_flow, 0),
        "step_free_served_trips": round(base, 0),
        "pct_trips_step_free_served": round(100.0 * base / model.total_flow, 2),
        "pair_count_understates_by_factor": round(
            (100.0 * base / model.total_flow) / (100.0 * served_pairs / total_pairs), 2
        ),
    }
