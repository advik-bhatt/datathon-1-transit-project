"""How often each machine is actually out, from the agency's own monthly record.

`rc78-7x78` publishes, per unit per month since 2015, the number of scheduled
and unscheduled outages, the number of entrapments, and availability during the
AM peak, the PM peak and the full 24 hours. It does not publish outage events,
so the finest exposure measure available publicly is a monthly fraction. That
is enough to estimate how likely a unit is to be down, which is what the damage
model needs; it is not enough to reconstruct individual outages, and nothing
here pretends otherwise.

One number worth keeping in view: across all 83,776 equipment-months, 64.4% of
them contain at least one unscheduled outage, and for escalators alone the rate
is 75.2%. Any binary "will this unit have an outage next month" target is
therefore close to uninformative, which is why this module estimates
*unavailability* rather than outage occurrence.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

AVAIL_COLS = ("_24_hour_availability", "am_peak_availability", "pm_peak_availability")


def tidy_availability(av: pd.DataFrame) -> pd.DataFrame:
    df = av.copy()
    df["month"] = pd.to_datetime(df["month"], errors="coerce")
    for c in list(AVAIL_COLS) + ["total_outages", "scheduled_outages",
                                 "unscheduled_outages", "entrapments",
                                 "station_complex_mrn"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["equipment_code"] = df["equipment_code"].astype(str).str.strip()
    df["is_elevator"] = df["equipment_type"].astype(str).str.strip().str.lower() == "elevator"
    # Availability is published as a fraction; anything outside [0,1] is a
    # reporting error and is dropped rather than clipped, so it cannot quietly
    # become a 100%-available month.
    for c in AVAIL_COLS:
        if c in df.columns:
            df.loc[(df[c] < 0) | (df[c] > 1), c] = np.nan
    return df.dropna(subset=["month"])


def base_rates(av: pd.DataFrame) -> dict:
    """Context numbers that decide how this data can honestly be used."""
    df = tidy_availability(av)
    el = df[df["is_elevator"]]
    es = df[~df["is_elevator"]]
    def rate(x):
        u = x["unscheduled_outages"].fillna(0)
        return round(100.0 * float((u >= 1).mean()), 1)
    return {
        "equipment_months": int(len(df)),
        "months_with_an_unscheduled_outage_pct": rate(df),
        "elevator_months": int(len(el)),
        "elevator_months_with_outage_pct": rate(el),
        "escalator_months": int(len(es)),
        "escalator_months_with_outage_pct": rate(es),
        "median_24h_availability": round(float(df["_24_hour_availability"].median()), 4),
        "median_elevator_24h_availability": round(float(el["_24_hour_availability"].median()), 4),
        "entrapments_total": int(df["entrapments"].fillna(0).sum()),
        "month_range": f"{df['month'].min().date()} to {df['month'].max().date()}",
    }


def unavailability(av: pd.DataFrame, months: int = 24,
                   as_of: str | pd.Timestamp | None = None) -> pd.DataFrame:
    """Per-unit expected unavailability over a trailing window.

    Returns the mean fraction of time each unit was NOT available, over the
    most recent `months` months of published history. Units with no recent
    record fall back to the fleet median for their equipment type, which is
    stated in the output so the substitution is visible.
    """
    df = tidy_availability(av)
    end = pd.Timestamp(as_of) if as_of else df["month"].max()
    start = end - pd.DateOffset(months=months)
    win = df[(df["month"] > start) & (df["month"] <= end)]
    if win.empty:
        raise ValueError("no availability rows in the requested window")

    g = win.groupby("equipment_code").agg(
        n_months=("month", "size"),
        is_elevator=("is_elevator", "first"),
        avail_24h=("_24_hour_availability", "mean"),
        avail_am=("am_peak_availability", "mean"),
        avail_pm=("pm_peak_availability", "mean"),
        outages=("total_outages", "mean"),
        unscheduled=("unscheduled_outages", "mean"),
        entrapments=("entrapments", "sum"),
        complex_id=("station_complex_mrn", "first"),
    ).reset_index()

    med_el = float(win.loc[win["is_elevator"], "_24_hour_availability"].median())
    med_es = float(win.loc[~win["is_elevator"], "_24_hour_availability"].median())
    fallback = np.where(g["is_elevator"], med_el, med_es)
    g["imputed_availability"] = g["avail_24h"].isna()
    g["avail_24h"] = g["avail_24h"].fillna(pd.Series(fallback, index=g.index))
    g["unavailability"] = (1.0 - g["avail_24h"]).clip(lower=0.0, upper=1.0)
    g["peak_unavailability"] = (
        1.0 - g[["avail_am", "avail_pm"]].mean(axis=1)
    ).clip(lower=0.0, upper=1.0).fillna(g["unavailability"])
    g["window_start"] = start
    g["window_end"] = end
    n_imp = int(g["imputed_availability"].sum())
    if n_imp:
        log.info("%d of %d units had no availability in the window and use the "
                 "fleet median for their type", n_imp, len(g))
    return g


def age_features(assets: pd.DataFrame, as_of: str | pd.Timestamp | None = None) -> pd.DataFrame:
    """Asset age and remaining service life, for the maintenance view."""
    now = pd.Timestamp(as_of) if as_of else pd.Timestamp.today().normalize()
    a = assets.copy()
    inst = pd.to_datetime(a.get("original_installation_date"), errors="coerce")
    latest = pd.to_datetime(a.get("latest_installation_date"), errors="coerce")
    a["age_years"] = (now - inst).dt.days / 365.25
    a["years_since_latest_work"] = (now - latest).dt.days / 365.25
    life = pd.to_numeric(a.get("service_life"), errors="coerce")
    a["service_life_years"] = life
    a["life_used_frac"] = (a["age_years"] / life.where(life > 0)).clip(lower=0)
    a["past_service_life"] = a["life_used_frac"] > 1.0
    a["weather_exposed"] = (a.get("exposed_to_weather", "")
                            .astype(str).str.strip().str.upper().eq("YES"))
    return a
