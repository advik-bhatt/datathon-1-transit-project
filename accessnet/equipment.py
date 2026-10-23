"""Elevators as a vertical path, not as a count.

A rider in a wheelchair needs a continuous step-free chain from the street to
the platform they board from. Whether a given elevator outage breaks that chain
depends on whether the machine is the only one serving its segment or one of
several. The open data does not state this. It gives, per asset:

* `street_access`, a reliable structured flag, YES for 168 of the 482
  elevators and NO for 308;
* `notes`, free text that is the only description of which vertical segment the
  machine serves. 333 of 482 mention a mezzanine or concourse, 278 mention a
  platform, 424 contain the word "to" and so describe a segment at all.
* 31 are not passenger assets at all, serving yards, freight, relay rooms,
  inspection barns and signal towers. 9 say only "N Landings".

So the chain is inferable for most assets and not for some. Rather than
pretend otherwise, every complex is labelled with the confidence of its
inferred vertical model, and the downstream damage ranking is reported under
both this model and a deliberately cruder fallback, so a reader can see how
much the free-text parse is carrying.

Twelve of the 140 step-free complexes have no elevator in the inventory at all.
Those are accessible by ramp or at grade, so no elevator outage can remove
them, and treating them as elevator-dependent would invent damage.
"""
from __future__ import annotations

import logging
import re

import pandas as pd

log = logging.getLogger(__name__)

STREET, MEZZANINE, PLATFORM, UNKNOWN = "street", "mezzanine", "platform", "unknown"

# Assets that do not carry passengers between street and platform.
NON_PASSENGER = re.compile(
    r"\byard\b|\bfreight\b|relay|inspection\s+barn|signal\s+tower|storage|depot",
    re.IGNORECASE,
)
# A note that says only how many landings the car serves, with no segment.
LANDINGS_ONLY = re.compile(r"^\s*\d+\s*landings?\s*\.?\s*$", re.IGNORECASE)

MEZZ_WORDS = re.compile(r"mezzanine|mezz\b|concourse", re.IGNORECASE)
PLATFORM_WORDS = re.compile(r"platform", re.IGNORECASE)
# Street-side language, used only to corroborate the structured flag.
STREET_WORDS = re.compile(
    r"\bstreet\b|\bst\b\s*&|\bav\b\s*&|\bave\b\s*&|corner|entrance|sidewalk"
    r"|plaza|intersection|\bblvd\b",
    re.IGNORECASE,
)
MEZZ_TO_MEZZ = re.compile(
    r"(upper|lower)\s+mezzanine\s+to\s+(upper|lower)\s+mezzanine", re.IGNORECASE
)

SERVICE_OUT = re.compile(r"Out of Service", re.IGNORECASE)


def classify_segment(row) -> tuple[str, str, str]:
    """Infer (from_level, to_level, confidence) for one elevator."""
    note = str(getattr(row, "notes", "") or "")
    street_flag = str(getattr(row, "street_access", "") or "").strip().upper() == "YES"

    if NON_PASSENGER.search(note):
        return UNKNOWN, UNKNOWN, "non_passenger"
    if LANDINGS_ONLY.match(note):
        # The structured flag still tells us where it starts.
        return (STREET if street_flag else UNKNOWN), UNKNOWN, "landings_only"

    mezz = bool(MEZZ_WORDS.search(note))
    plat = bool(PLATFORM_WORDS.search(note))

    if MEZZ_TO_MEZZ.search(note):
        return MEZZANINE, MEZZANINE, "high"
    if street_flag and plat and not mezz:
        return STREET, PLATFORM, "high"          # direct street to platform
    if street_flag and mezz:
        return STREET, MEZZANINE, "high"
    if street_flag:
        return STREET, UNKNOWN, "medium"
    if mezz and plat:
        return MEZZANINE, PLATFORM, "high"
    if plat:
        return UNKNOWN, PLATFORM, "medium"
    if mezz:
        return UNKNOWN, MEZZANINE, "medium"
    if STREET_WORDS.search(note):
        # Street language without the structured flag; weaker evidence.
        return STREET, UNKNOWN, "low"
    return UNKNOWN, UNKNOWN, "none"


def build_assets(equipment: pd.DataFrame) -> pd.DataFrame:
    """Elevators only, joined to their complex, with their inferred segment."""
    el = equipment[equipment["elevator_or_escalator"].str.strip().str.lower()
                   == "elevator"].copy()
    el["complex_id"] = pd.to_numeric(el["station_complex_mrn"], errors="coerce")
    el["in_service"] = ~el["service_status"].astype(str).str.contains(SERVICE_OUT, na=False)

    seg = [classify_segment(r) for r in el.itertuples()]
    el["from_level"] = [s[0] for s in seg]
    el["to_level"] = [s[1] for s in seg]
    el["segment_confidence"] = [s[2] for s in seg]
    el["passenger_asset"] = el["segment_confidence"] != "non_passenger"
    el["segment"] = el["from_level"] + "->" + el["to_level"]

    n_np = int((~el["passenger_asset"]).sum())
    log.info("elevators: %d total, %d passenger assets, %d non-passenger dropped "
             "from the accessibility model", len(el), len(el) - n_np, n_np)
    return el


def complex_vertical_model(assets: pd.DataFrame) -> pd.DataFrame:
    """Per complex: how many distinct segments, and how redundant each is.

    An elevator is REDUNDANT when another passenger elevator at the same
    complex serves the same inferred segment, and CRITICAL when it is the only
    one on its segment. A complex whose segments are all redundant keeps
    step-free access through any single outage; a complex with any critical
    segment does not.
    """
    pa = assets[assets["passenger_asset"] & assets["in_service"]].copy()
    rows = []
    for cid, g in pa.groupby("complex_id"):
        counts = g["segment"].value_counts()
        known = g[g["segment_confidence"].isin(("high", "medium"))]
        conf = ("high" if (g["segment_confidence"] == "high").mean() >= 0.8
                else "medium" if len(known) >= max(1, len(g) // 2)
                else "low")
        rows.append({
            "complex_id": cid,
            "n_elevators": int(len(g)),
            "n_segments": int(counts.size),
            "n_critical_segments": int((counts == 1).sum()),
            "min_redundancy": int(counts.min()) if counts.size else 0,
            "all_segments_redundant": bool(counts.size > 0 and (counts > 1).all()),
            "vertical_model_confidence": conf,
        })
    return pd.DataFrame(rows)


def asset_criticality(assets: pd.DataFrame) -> pd.DataFrame:
    """Flag each elevator as the sole server of its segment or not."""
    pa = assets[assets["passenger_asset"] & assets["in_service"]].copy()
    size = pa.groupby(["complex_id", "segment"])["equipment_code"].transform("size")
    pa["peers_on_segment"] = size - 1
    pa["sole_on_segment"] = pa["peers_on_segment"] == 0
    return pa[["equipment_code", "complex_id", "segment", "from_level", "to_level",
               "segment_confidence", "peers_on_segment", "sole_on_segment",
               "street_access", "original_installation_date", "service_life",
               "exposed_to_weather", "station_name", "borough", "notes"]]


def elevator_dependent_complexes(cx_access: pd.DataFrame,
                                 assets: pd.DataFrame) -> pd.DataFrame:
    """Which step-free complexes actually depend on an elevator.

    A step-free complex with no elevator in the inventory is reached by ramp or
    at grade. No elevator outage can take it away, so it must not be counted as
    at risk.
    """
    have = set(assets.loc[assets["passenger_asset"], "complex_id"].dropna().astype(int))
    cx = cx_access.copy()
    cx["complex_id"] = pd.to_numeric(cx["complex_id"], errors="coerce")
    cx["has_elevator"] = cx["complex_id"].astype("Int64").isin(have)
    cx["elevator_dependent"] = cx["step_free_any"] & cx["has_elevator"]
    n = int((cx["step_free_any"] & ~cx["has_elevator"]).sum())
    log.info("%d step-free complexes have no elevator in the inventory and are "
             "treated as ramp or grade access", n)
    return cx


def summarize(assets: pd.DataFrame, vmodel: pd.DataFrame) -> dict:
    pa = assets[assets["passenger_asset"]]
    crit = asset_criticality(assets)
    return {
        "n_elevators_total": int(len(assets)),
        "n_passenger_elevators": int(len(pa)),
        "n_non_passenger": int((~assets["passenger_asset"]).sum()),
        "n_out_of_service": int((~assets["in_service"]).sum()),
        "segment_confidence": assets["segment_confidence"].value_counts().to_dict(),
        "n_complexes_with_elevators": int(vmodel["complex_id"].nunique()),
        "n_complexes_all_segments_redundant": int(vmodel["all_segments_redundant"].sum()),
        "n_complexes_with_a_critical_segment": int((vmodel["n_critical_segments"] > 0).sum()),
        "n_elevators_sole_on_their_segment": int(crit["sole_on_segment"].sum()),
        "vertical_model_confidence": vmodel["vertical_model_confidence"]
        .value_counts().to_dict(),
    }
