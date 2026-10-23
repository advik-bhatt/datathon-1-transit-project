"""Synthetic fixtures: a small network whose right answers are known by hand."""
from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture
def toy_stations() -> pd.DataFrame:
    """Five stations on one line, with a deliberate one-direction-only case.

        A --- B --- C --- D --- E

    A, C, E are step-free both ways. B is not step-free at all.
    D is step-free northbound only, which is the case the published data has
    eight real instances of and which a binary model gets wrong.
    """
    rows = [
        ("A", 1, 1, 1, 1, ""),
        ("B", 2, 2, 0, 0, ""),
        ("C", 3, 3, 1, 1, ""),
        ("D", 4, 4, 2, 1, "Uptown only"),
        ("E", 5, 5, 1, 1, ""),
    ]
    return pd.DataFrame(
        [{"gtfs_stop_id": g, "station_id": s, "complex_id": c, "ada": a,
          "ada_northbound": n, "ada_southbound": (1 if a == 1 else 0),
          "ada_notes": note, "stop_name": g, "daytime_routes": "1",
          "borough": "M", "gtfs_latitude": 40.0 + s / 100,
          "gtfs_longitude": -74.0, "north_direction_label": "",
          "south_direction_label": ""}
         for g, s, c, a, n, note in rows]
    )


@pytest.fixture
def toy_topology() -> pd.DataFrame:
    """One northbound pattern and one southbound pattern over all five stops."""
    rows = []
    for direction, order in (("N", ["A", "B", "C", "D", "E"]),
                             ("S", ["E", "D", "C", "B", "A"])):
        for i, stop in enumerate(order, 1):
            rows.append({"line": "1", "direction": direction,
                         "path_id": f"1-{direction}", "stop_order": i,
                         "gtfs_stop_id": stop, "n_trains": 1000})
    return pd.DataFrame(rows)


@pytest.fixture
def toy_od() -> pd.DataFrame:
    """Equal flow on every ordered pair, so set sizes drive the arithmetic."""
    ids = [1, 2, 3, 4, 5]
    return pd.DataFrame([{"o": o, "d": d, "flow": 100.0}
                         for o in ids for d in ids if o != d])


@pytest.fixture
def toy_equipment() -> pd.DataFrame:
    """Elevators covering the cases the parser has to separate."""
    # Columns mirror the real inventory: the vertical path comes from the
    # structured level-access flags and redundancy from `redundant_elevator`,
    # with `notes` present only as a cross-check.
    # (code, complex, street_access, mezz1, mezz2, platform, redundant,
    #  partner, direction, order, revenue, notes)
    rows = [
        # Complex 1: a street-to-mezzanine and a mezzanine-to-platform leg,
        # neither with a substitute.
        ("EL1", 1, "YES", "+", "-", "-", "-", "", "Both", 1, "YES",
         "Street entrance to mezzanine"),
        ("EL2", 1, "NO", "+", "-", "+", "-", "", "Northbound", 2, "YES",
         "mezzanine to platform for uptown service"),
        # Complex 3: two machines the agency records as substitutes for each
        # other, so neither is a single point of failure.
        ("EL3", 3, "NO", "+", "-", "+", "+", "EL4", "Both", 1, "YES",
         "mezzanine to platform"),
        ("EL4", 3, "NO", "+", "-", "+", "+", "EL3", "Both", 1, "YES",
         "mezzanine to platform"),
        # Complex 5: a yard machine, which the revenue flag excludes and which
        # therefore carries no structured path data, as in the real file.
        ("EL5", 5, "NO", None, None, None, None, "", "", None, "NO",
         "Freight Elevator At 207Th Street Yard"),
        ("EL6", 5, "YES", "-", "-", "+", "-", "", "Both", 1, "YES",
         "Street to platform"),
    ]
    return pd.DataFrame(
        [{"equipment_code": c, "elevator_or_escalator": "Elevator",
          "asset_class": "Elevator", "station_complex_mrn": cx,
          "station_mrn": cx, "street_access": sa, "notes": note,
          "elevator_mezzanine_1_access": m1,
          "elevator_mezzanine_2_access": m2,
          "elevator_platform_access": pl,
          "redundant_elevator": red,
          "redundant_elevator_platform": partner,
          "redundant_elevator_street": "",
          "redundant_elevator_mezzanine": "",
          "redundant_elevator_access": "",
          "elevator_direction_serviced": direction,
          "elevator_order": order,
          "revenue_machine": rev,
          "ada_compliant": "YES",
          "service_status": "Installed-Functioning-In Service",
          "original_installation_date": pd.Timestamp("2005-01-01"),
          "latest_installation_date": pd.Timestamp("2005-01-01"),
          "service_life": 25.0, "exposed_to_weather": "NO",
          "station_name": f"S{cx}", "borough": "M", "subway_line": "1",
          "x_coordinate": 40.0, "y_coordinate": -74.0}
         for c, cx, sa, m1, m2, pl, red, partner, direction, order, rev, note in rows]
    )


@pytest.fixture
def toy_availability() -> pd.DataFrame:
    """Twenty-four months of availability for the toy elevators."""
    months = pd.date_range("2025-01-01", periods=24, freq="MS")
    rows = []
    avail = {"EL1": 0.99, "EL2": 0.90, "EL3": 0.95, "EL4": 0.95,
             "EL5": 0.99, "EL6": 0.80}
    # Hours are made consistent with the ratio, because unavailability is
    # computed hours-weighted and a fixture whose hours contradict its ratios
    # would test nothing.
    total_h = 730.0
    for code, a in avail.items():
        for m in months:
            rows.append({"month": m, "equipment_code": code,
                         "equipment_type": "Elevator", "borough": "Manhattan",
                         "_24_hour_availability": a,
                         "am_peak_availability": a, "pm_peak_availability": a,
                         "total_outages": 1.0, "scheduled_outages": 0.0,
                         "unscheduled_outages": 1.0, "entrapments": 0.0,
                         "station_complex_mrn": 1,
                         "time_since_major_improvement": 100.0,
                         "station_name": "S", "station_complex_name": "S",
                         "am_peak_hours_available": 120.0 * a,
                         "am_peak_total_hours": 120.0,
                         "pm_peak_hours_available": 120.0 * a,
                         "pm_peak_total_hours": 120.0,
                         "_24_hour_hours_available": total_h * a,
                         "_24_hour_total_hours": total_h,
                         "station_mrn": 1})
    return pd.DataFrame(rows)
