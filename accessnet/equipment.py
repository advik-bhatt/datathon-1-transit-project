"""Elevators as a vertical path, from the columns the agency already publishes.

This module was first written to infer the vertical path and the redundancy of
each elevator by parsing the free-text `notes` field, on the stated belief that
the notes were "the only public description of which vertical segment the
machine serves." **That was wrong, and the error was material.** The inventory
carries structured fields for all of it, populated for exactly the 430
passenger elevators and blank for exactly the 52 the agency flags
`revenue_machine = NO`:

    elevator_direction_serviced    Both (213), Southbound (111), Northbound (106)
    elevator_order                 position in the chain, 1 through 6
    street_access                  does it reach the street
    elevator_mezzanine_1_access    does it serve the first mezzanine
    elevator_mezzanine_2_access    does it serve the second mezzanine
    elevator_platform_access       does it reach a platform
    redundant_elevator             "+" if another elevator can substitute
    redundant_elevator_street      the substitute's equipment code, per level
    redundant_elevator_mezzanine
    redundant_elevator_access
    redundant_elevator_platform
    alternative_route              what a rider should do when it is out

The published redundancy flag means "this elevator has a substitute": 107 of
the 109 units flagged "+" name a partner code, and 308 of 309 flagged "-" name
none.

**Why the text parse failed, kept here because it is the instructive part.**
Scored against the published flag, the notes-based inference agreed on only
45.7% of 418 elevators, Cohen's kappa 0.105, which is barely better than
chance. The failure is systematic rather than noisy: the parse collapsed a
level pair such as "mezzanine to platform" into one segment and treated every
elevator sharing that pair at a complex as a substitute. They usually are not.
EL298 serves "Park Ave & 23 St (NE corner) to uptown platform" and EL299 serves
"(NW corner) to downtown platform"; both parse as street-to-platform, and
neither can stand in for the other. The same mistake made Penn Station's
uptown-1 elevator look redundant against machines serving entirely different
platforms.

The consequence was that the first version of this project **understated
single points of failure**, counting 116 where the agency's own flag implies
309, and so understated how much step-free travel is at risk. The structured
fields are now the source of truth and the notes are a cross-check.
"""

from __future__ import annotations

import logging
import re

import numpy as np
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


def _plus(v) -> bool:
    """The inventory encodes these booleans as "+" and "-"."""
    return str(v or "").strip() == "+"


def classify_segment(row) -> tuple[str, str, str]:
    """Infer (from_level, to_level, confidence) from the structured columns.

    The chain is read off the level-access flags rather than the notes:
    `street_access`, the two mezzanine flags and `elevator_platform_access`
    say which levels a machine touches, and `elevator_order` says where it
    sits in the sequence. The notes are no longer consulted for this.
    """
    revenue = str(getattr(row, "revenue_machine", "") or "").strip().upper()
    note = str(getattr(row, "notes", "") or "")

    # `revenue_machine` is the agency's own flag and is exactly the set of
    # machines with no structured path data: 52 of 482, every one of them a
    # yard, freight, relay, barn, signal-tower or parking asset. Matching on
    # the notes caught only 31 of them.
    if revenue == "NO":
        return UNKNOWN, UNKNOWN, "non_passenger"
    if NON_PASSENGER.search(note):
        return UNKNOWN, UNKNOWN, "non_passenger"

    street = str(getattr(row, "street_access", "") or "").strip().upper() == "YES"
    mezz = _plus(getattr(row, "elevator_mezzanine_1_access", "")) or \
        _plus(getattr(row, "elevator_mezzanine_2_access", ""))
    plat = _plus(getattr(row, "elevator_platform_access", ""))

    if street and plat and not mezz:
        return STREET, PLATFORM, "structured"
    if street and mezz:
        return STREET, MEZZANINE, "structured"
    if mezz and plat:
        return MEZZANINE, PLATFORM, "structured"
    if street:
        return STREET, UNKNOWN, "structured"
    if plat:
        return UNKNOWN, PLATFORM, "structured"
    if mezz:
        return UNKNOWN, MEZZANINE, "structured"
    return UNKNOWN, UNKNOWN, "no_levels_flagged"


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

    # Redundancy comes from the agency's own flag, not from inference. "+"
    # means a substitute exists, and the partner columns name it per level.
    el["has_substitute"] = el["redundant_elevator"].map(_plus) \
        if "redundant_elevator" in el.columns else False
    partner_cols = [c for c in ("redundant_elevator_street",
                                "redundant_elevator_mezzanine",
                                "redundant_elevator_access",
                                "redundant_elevator_platform")
                    if c in el.columns]
    if partner_cols:
        named = el[partner_cols].apply(
            lambda r: ", ".join(sorted({str(v).strip() for v in r
                                        if str(v).strip() not in ("", "nan", "NaN", "None")})),
            axis=1)
        el["substitute_codes"] = named
        el["names_a_substitute"] = named.str.len() > 0
    else:
        el["substitute_codes"] = ""
        el["names_a_substitute"] = False

    el["direction_served"] = (el["elevator_direction_serviced"].astype(str).str.strip()
                              if "elevator_direction_serviced" in el.columns else "")
    el["chain_position"] = (pd.to_numeric(el.get("elevator_order"), errors="coerce")
                            if "elevator_order" in el.columns else pd.NA)

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
        sub = g["has_substitute"].fillna(False).astype(bool)
        structured = (g["segment_confidence"] == "structured").mean()
        rows.append({
            "complex_id": cid,
            "n_elevators": int(len(g)),
            "n_levels_touched": int(counts.size),
            "n_single_points_of_failure": int((~sub).sum()),
            "all_elevators_have_a_substitute": bool(len(g) > 0 and sub.all()),
            "n_directions_served": int(g["direction_served"].nunique()),
            "max_chain_position": (int(g["chain_position"].max())
                                   if g["chain_position"].notna().any() else 0),
            "pct_from_structured_fields": round(100.0 * float(structured), 1),
        })
    return pd.DataFrame(rows)


def asset_criticality(assets: pd.DataFrame) -> pd.DataFrame:
    """Flag each elevator as a single point of failure, per the agency's data.

    `sole_on_segment` is now the published `redundant_elevator` flag inverted:
    an elevator is a single point of failure when the agency records no
    substitute for it. The level-pair count that the first version of this
    module used is kept alongside as `peers_on_same_level_pair`, because the
    gap between the two is the measurement that justified the rewrite: it
    agreed with the published flag on only 45.7% of elevators.
    """
    pa = assets[assets["passenger_asset"] & assets["in_service"]].copy()
    size = pa.groupby(["complex_id", "segment"])["equipment_code"].transform("size")
    pa["peers_on_same_level_pair"] = size - 1
    pa["sole_on_segment"] = ~pa["has_substitute"].fillna(False).astype(bool)
    pa["peers_on_segment"] = np.where(pa["sole_on_segment"], 0, 1)
    return pa[["equipment_code", "complex_id", "segment", "from_level", "to_level",
               "segment_confidence", "sole_on_segment", "has_substitute",
               "substitute_codes", "names_a_substitute", "direction_served",
               "chain_position", "peers_on_segment", "peers_on_same_level_pair",
               "street_access", "original_installation_date", "service_life",
               "exposed_to_weather", "station_name", "borough", "notes"]]


def redundancy_agreement(assets: pd.DataFrame) -> dict:
    """How far the old text inference was from the published flag.

    Reported rather than buried, because it is the reason this module no
    longer parses notes for redundancy.
    """
    pa = assets[assets["passenger_asset"] & assets["in_service"]].copy()
    size = pa.groupby(["complex_id", "segment"])["equipment_code"].transform("size")
    inferred_sole = (size - 1) == 0
    published_sole = ~pa["has_substitute"].fillna(False).astype(bool)
    agree = float((inferred_sole == published_sole).mean())
    both = int((inferred_sole & published_sole).sum())
    return {
        "n_compared": int(len(pa)),
        "agreement_pct": round(100.0 * agree, 1),
        "inferred_single_points": int(inferred_sole.sum()),
        "published_single_points": int(published_sole.sum()),
        "agreed_single_points": both,
        "published_has_substitute": int(pa["has_substitute"].fillna(False).sum()),
        "substitute_flag_corroborated_by_a_named_partner": int(
            (pa["has_substitute"].fillna(False) & pa["names_a_substitute"]).sum()),
    }


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
        "segment_source": assets["segment_confidence"].value_counts().to_dict(),
        "n_complexes_with_elevators": int(vmodel["complex_id"].nunique()),
        "n_complexes_all_elevators_substitutable": int(
            vmodel["all_elevators_have_a_substitute"].sum()),
        "n_complexes_with_a_single_point_of_failure": int(
            (vmodel["n_single_points_of_failure"] > 0).sum()),
        "n_single_points_of_failure": int(crit["sole_on_segment"].sum()),
        "redundancy_agreement_with_old_text_inference": redundancy_agreement(assets),
        "direction_served": assets.loc[assets["passenger_asset"], "direction_served"]
        .value_counts().to_dict(),
    }
