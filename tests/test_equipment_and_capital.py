"""Vertical-path inference, and the capital search's mathematical properties."""
from __future__ import annotations

import pandas as pd
import pytest

from accessnet import ada, availability as avm, capital as cap, damage as dm
from accessnet import equipment as eqm, graph as gr


def test_non_passenger_assets_are_excluded(toy_equipment):
    a = eqm.build_assets(toy_equipment)
    yard = a[a["equipment_code"] == "EL5"].iloc[0]
    assert not yard["passenger_asset"]
    assert yard["segment_confidence"] == "non_passenger"
    assert int(a["passenger_asset"].sum()) == 5


def test_revenue_machine_flag_overrides_the_notes(toy_equipment):
    """The agency's own flag is stricter than the text and is checked first.

    On the real inventory it marks 52 elevators non-revenue where the notes
    catch only 31, so a passenger-looking note must not rescue a machine the
    agency says earns no revenue.
    """
    eq = toy_equipment.copy()
    eq["revenue_machine"] = "YES"
    # An ordinary-looking note, but flagged non-revenue by the agency.
    eq.loc[eq["equipment_code"] == "EL3", "revenue_machine"] = "NO"
    a = eqm.build_assets(eq).set_index("equipment_code")
    assert not a.loc["EL3", "passenger_asset"]
    assert a.loc["EL3", "segment_confidence"] == "non_passenger"
    # And a revenue machine whose STATION name contains "Yards" survives.
    assert a.loc["EL1", "passenger_asset"]


def test_segments_are_inferred_from_notes_and_flag(toy_equipment):
    a = eqm.build_assets(toy_equipment).set_index("equipment_code")
    assert a.loc["EL1", "segment"] == "street->mezzanine"
    assert a.loc["EL2", "segment"] == "mezzanine->platform"
    assert a.loc["EL6", "segment"] == "street->platform"


def test_redundancy_is_detected(toy_equipment):
    a = eqm.build_assets(toy_equipment)
    crit = eqm.asset_criticality(a).set_index("equipment_code")
    # Complex 1 has two different segments, each served by one machine.
    assert crit.loc["EL1", "sole_on_segment"]
    assert crit.loc["EL2", "sole_on_segment"]
    # Complex 3 has two machines on the same segment, so neither is sole.
    assert not crit.loc["EL3", "sole_on_segment"]
    assert not crit.loc["EL4", "sole_on_segment"]
    v = eqm.complex_vertical_model(a).set_index("complex_id")
    assert v.loc[3, "all_segments_redundant"]
    assert not v.loc[1, "all_segments_redundant"]


def test_step_free_complex_without_an_elevator_is_not_at_risk(toy_stations, toy_equipment):
    """Ramp and grade access cannot be taken away by an elevator outage."""
    acc = ada.station_accessibility(toy_stations)
    cx = ada.complex_accessibility(acc)
    a = eqm.build_assets(toy_equipment)
    dep = eqm.elevator_dependent_complexes(cx, a).set_index("complex_id")
    # Complex 4 is step-free northbound but has no elevator in the inventory.
    assert dep.loc[4, "step_free_any"]
    assert not dep.loc[4, "has_elevator"]
    assert not dep.loc[4, "elevator_dependent"]


def test_unavailability_is_one_minus_availability(toy_availability):
    u = avm.unavailability(toy_availability, months=24).set_index("equipment_code")
    assert u.loc["EL6", "unavailability"] == pytest.approx(0.20, abs=1e-6)
    assert u.loc["EL1", "unavailability"] == pytest.approx(0.01, abs=1e-6)


def test_unavailability_is_hours_weighted_not_a_mean_of_ratios(toy_availability):
    """Months with few in-service hours must not count as much as full months.

    This is the real EL131 case: 744 in-service hours in one month and 80 in
    another. Averaging the two ratios equally understates its unavailability
    by 5 points.
    """
    av = toy_availability[toy_availability["equipment_code"] == "EL1"].copy()
    av = av.sort_values("month").reset_index(drop=True)
    # One full month at 50% availability, one near-empty month at 100%.
    av.loc[0, ["_24_hour_total_hours", "_24_hour_hours_available",
               "_24_hour_availability"]] = [730.0, 365.0, 0.5]
    av.loc[1, ["_24_hour_total_hours", "_24_hour_hours_available",
               "_24_hour_availability"]] = [10.0, 10.0, 1.0]
    av = av.iloc[:2]
    u = avm.unavailability(av, months=24).set_index("equipment_code")
    hours_weighted = 1.0 - (365.0 + 10.0) / (730.0 + 10.0)
    mean_of_ratios = 1.0 - (0.5 + 1.0) / 2.0
    assert u.loc["EL1", "unavailability"] == pytest.approx(hours_weighted, abs=1e-6)
    assert u.loc["EL1", "unavailability"] > mean_of_ratios


def test_months_out_of_service_are_separated_from_unreliability(toy_availability):
    """A unit under capital replacement is not a unit that keeps breaking."""
    av = toy_availability[toy_availability["equipment_code"] == "EL2"].copy()
    av = av.sort_values("month").reset_index(drop=True)
    # Sixteen months with no in-service hours at all, as EL131 really shows.
    av.loc[:15, ["_24_hour_total_hours", "_24_hour_hours_available",
                 "_24_hour_availability"]] = [0.0, 0.0, float("nan")]
    u = avm.unavailability(av, months=24).set_index("equipment_code")
    assert int(u.loc["EL2", "months_out_of_service"]) == 16
    assert u.loc["EL2", "in_service_coverage"] < 0.5
    assert bool(u.loc["EL2", "mostly_out_of_service"])
    # The remaining months still drive the reliability figure.
    assert u.loc["EL2", "unavailability"] == pytest.approx(0.10, abs=1e-6)


def test_availability_outside_zero_one_is_dropped(toy_availability):
    bad = toy_availability.copy()
    bad.loc[0, "_24_hour_availability"] = 1.4
    t = avm.tidy_availability(bad)
    assert t["_24_hour_availability"].max() <= 1.0


def test_damage_is_zero_for_a_redundant_elevator(toy_stations, toy_topology,
                                                 toy_od, toy_equipment,
                                                 toy_availability):
    acc = ada.station_accessibility(toy_stations)
    cx = ada.complex_accessibility(acc)
    edges = gr.build_edges(toy_topology, toy_stations, min_trains=1)
    model = dm.ReachabilityModel(edges, cx, toy_od)
    a = eqm.build_assets(toy_equipment)
    crit = eqm.asset_criticality(a)
    cxd = dm.complex_removal_damage(model, [1, 3, 5])
    un = avm.unavailability(toy_availability, months=24)
    seg = dm.elevator_damage(crit, cxd, un, model_name="segment").set_index("equipment_code")
    assert seg.loc["EL3", "damage_flow"] == 0.0
    assert seg.loc["EL1", "damage_flow"] > 0.0
    # The crude model holds every machine responsible, so it is an upper bound.
    anym = dm.elevator_damage(crit, cxd, un, model_name="any").set_index("equipment_code")
    assert anym.loc["EL3", "damage_flow"] >= seg.loc["EL3", "damage_flow"]


def test_greedy_gains_are_non_increasing(toy_stations, toy_topology, toy_od):
    """Submodularity: each extra station can only add less than the last."""
    acc = ada.station_accessibility(toy_stations)
    cx = ada.complex_accessibility(acc)
    edges = gr.build_edges(toy_topology, toy_stations, min_trains=1)
    model = dm.ReachabilityModel(edges, cx, toy_od)
    sel = cap.greedy_selection(model, [2], k=1)
    assert len(sel) == 1
    assert sel["marginal_gain"].iloc[0] > 0
    g = sel["marginal_gain"].to_numpy()
    assert all(g[i] >= g[i + 1] - 1e-9 for i in range(len(g) - 1))


def test_score_selection_is_order_independent(toy_stations, toy_topology, toy_od):
    acc = ada.station_accessibility(toy_stations)
    cx = ada.complex_accessibility(acc)
    edges = gr.build_edges(toy_topology, toy_stations, min_trains=1)
    model = dm.ReachabilityModel(edges, cx, toy_od)
    a = cap.score_selection(model, [2, 4])
    b = cap.score_selection(model, [4, 2])
    assert a["gain"] == pytest.approx(b["gain"])
