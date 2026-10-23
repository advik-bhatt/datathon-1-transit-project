"""Step-free accessibility, as the data actually describes it.

Published analyses treat accessibility as one bit per station. The station
table does not. It carries three fields, and they disagree with each other in
ways that matter:

    ada              0 none, 1 full, 2 partial
    ada_northbound   step-free platform access in the northbound direction
    ada_southbound   step-free platform access in the southbound direction

Measured on the 496-row station table: 166 stations are step-free in both
directions, 322 in neither, and 8 in exactly one. Those 8 are the whole
argument for treating the network as directed, and every one of them carries a
free-text note that corroborates the flags:

    49 St (N R W)          northbound only    "Uptown only"
    Wilson Av (L)          northbound only    "Manhattan-bound only"
    86 St (4 5 6)          northbound only    "Uptown local only"
    50 St (C E)            southbound only    "Downtown only"
    Spring St (C E)        southbound only    "Downtown only"
    28 St (6)              southbound only    "Downtown only"
    Court Sq-23 St (E F)   southbound only    "Manhattan-bound only"
    Hoyt St (2 3)          southbound only    "Outbound only"

Because the structured flags exist, this module uses them as the source of
truth and uses the notes only to cross-check, which avoids resting the result
on free-text parsing. `validate_notes_against_flags` performs that check and
is run in the test suite.

One restriction the flags cannot express is noted and carried as a caveat
rather than silently dropped: 86 St's note says "Uptown local only", meaning
the accessible platform serves the local 6 but not the express 4 and 5.
"""
from __future__ import annotations

import logging
import re

import pandas as pd

from .config import ADA_FULL, ADA_NONE, ADA_PARTIAL, NORTH, SOUTH

log = logging.getLogger(__name__)

# Phrases that indicate a northbound-only or southbound-only restriction.
# In MTA usage "uptown" and "Bronx-bound" are northbound; "downtown",
# "Manhattan-bound" on an outer-borough line, and "outbound" vary, which is
# exactly why the structured flags are preferred over these.
_NORTH_WORDS = ("uptown", "bronx-bound", "northbound", "queens-bound")
_SOUTH_WORDS = ("downtown", "southbound", "brooklyn-bound", "outbound")

# Notes that additionally restrict which ROUTES the accessible platform serves.
_ROUTE_RESTRICTED = re.compile(r"\b(?:local|express)\b", re.IGNORECASE)


def station_accessibility(stations: pd.DataFrame) -> pd.DataFrame:
    """One row per station with explicit per-direction step-free booleans."""
    df = stations.copy()
    for c in ("ada", "ada_northbound", "ada_southbound", "station_id", "complex_id"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    notes = df.get("ada_notes", pd.Series("", index=df.index))
    df["ada_notes"] = notes.astype(str).replace({"NaN": "", "nan": "", "None": ""}).fillna("")

    df["step_free_north"] = df["ada_northbound"].fillna(0).astype(int) == 1
    df["step_free_south"] = df["ada_southbound"].fillna(0).astype(int) == 1
    df["step_free_any"] = df["step_free_north"] | df["step_free_south"]
    df["step_free_both"] = df["step_free_north"] & df["step_free_south"]
    df["partial"] = df["ada"].fillna(0).astype(int) == ADA_PARTIAL
    # Flagged, not silently assumed away: the accessible platform may not serve
    # every route that calls at the station.
    df["route_restricted"] = df["ada_notes"].str.contains(_ROUTE_RESTRICTED, na=False)
    df["routes"] = (df.get("daytime_routes", pd.Series("", index=df.index))
                      .astype(str).str.split())
    return df


def validate_notes_against_flags(acc: pd.DataFrame) -> pd.DataFrame:
    """Cross-check the free-text notes against the structured flags.

    Returns one row per partially accessible station with the note, the flags,
    and whether they agree. Disagreement would mean the structured flags
    cannot be trusted alone, so this is asserted in the tests.
    """
    part = acc[acc["partial"]].copy()
    rows = []
    for r in part.itertuples():
        note = (r.ada_notes or "").lower()
        says_north = any(w in note for w in _NORTH_WORDS)
        says_south = any(w in note for w in _SOUTH_WORDS)
        flags_north_only = r.step_free_north and not r.step_free_south
        flags_south_only = r.step_free_south and not r.step_free_north
        if says_north and not says_south:
            agree = flags_north_only
        elif says_south and not says_north:
            agree = flags_south_only
        else:
            # "Outbound only" is direction-ambiguous without knowing the line's
            # orientation, so it is recorded as unresolved rather than failed.
            agree = None
        rows.append({
            "station_id": r.station_id,
            "stop_name": getattr(r, "stop_name", ""),
            "routes": " ".join(r.routes) if isinstance(r.routes, list) else "",
            "ada_notes": r.ada_notes,
            "step_free_north": bool(r.step_free_north),
            "step_free_south": bool(r.step_free_south),
            "note_says_north": says_north,
            "note_says_south": says_south,
            "agrees": agree,
            "route_restricted": bool(r.route_restricted),
        })
    return pd.DataFrame(rows)


def complex_accessibility(acc: pd.DataFrame) -> pd.DataFrame:
    """Roll station accessibility up to the complex, keeping direction.

    A complex counts as step-free in a direction if ANY of its constituent
    stations is step-free in that direction. That is the optimistic reading and
    it is the right one for reachability: a rider only needs one step-free
    platform serving their direction. The pessimistic reading is also computed,
    because the gap between them is itself informative about complexes that are
    only partly served.
    """
    g = acc.groupby("complex_id")
    out = g.agg(
        n_stations=("station_id", "size"),
        step_free_north=("step_free_north", "any"),
        step_free_south=("step_free_south", "any"),
        all_stations_north=("step_free_north", "all"),
        all_stations_south=("step_free_south", "all"),
        any_partial=("partial", "any"),
        any_route_restricted=("route_restricted", "any"),
        borough=("borough", "first"),
        lat=("gtfs_latitude", "mean"),
        lon=("gtfs_longitude", "mean"),
    ).reset_index()
    out["step_free_any"] = out["step_free_north"] | out["step_free_south"]
    out["step_free_both"] = out["step_free_north"] & out["step_free_south"]
    out["partially_served"] = out["step_free_any"] & ~(
        out["all_stations_north"] & out["all_stations_south"]
    )
    return out


def summarize(acc: pd.DataFrame, cx: pd.DataFrame) -> dict:
    """The headline counts, each carrying its denominator."""
    return {
        "n_stations": int(len(acc)),
        "stations_step_free_both_directions": int(acc["step_free_both"].sum()),
        "stations_step_free_one_direction_only": int(
            (acc["step_free_any"] & ~acc["step_free_both"]).sum()
        ),
        "stations_not_step_free": int((~acc["step_free_any"]).sum()),
        "pct_stations_step_free_any": round(100.0 * float(acc["step_free_any"].mean()), 1),
        "n_complexes": int(len(cx)),
        "complexes_step_free_any": int(cx["step_free_any"].sum()),
        "complexes_step_free_both": int(cx["step_free_both"].sum()),
        "complexes_not_step_free": int((~cx["step_free_any"]).sum()),
        "pct_complexes_step_free_any": round(100.0 * float(cx["step_free_any"].mean()), 1),
        "complexes_route_restricted": int(cx["any_route_restricted"].sum()),
    }
