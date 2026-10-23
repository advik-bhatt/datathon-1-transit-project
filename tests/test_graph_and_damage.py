"""Network semantics, and the invariants the damage model must obey."""
from __future__ import annotations

import pandas as pd
import pytest

from accessnet import ada, damage as dm, graph as gr


@pytest.fixture
def toy_model(toy_stations, toy_topology, toy_od):
    acc = ada.station_accessibility(toy_stations)
    cx = ada.complex_accessibility(acc)
    edges = gr.build_edges(toy_topology, toy_stations, min_trains=1)
    return dm.ReachabilityModel(edges, cx, toy_od), cx, edges


def test_edges_are_directed(toy_stations, toy_topology):
    edges = gr.build_edges(toy_topology, toy_stations, min_trains=1)
    assert set(edges["direction"]) == {"N", "S"}
    n = edges[edges["direction"] == "N"]
    assert ((n["u"] == 1) & (n["v"] == 2)).any()
    assert not ((n["u"] == 2) & (n["v"] == 1)).any()


def test_rarely_operated_patterns_are_dropped(toy_stations, toy_topology):
    few = toy_topology.assign(n_trains=5)
    assert gr.build_edges(few, toy_stations, min_trains=50).empty


def test_intermediate_station_need_not_be_accessible(toy_model):
    """A rider stays on the train, so B being inaccessible must not block A to C."""
    model, cx, edges = toy_model
    served = model.served_flow()
    assert served > 0
    g = gr.build_graph(edges, "N")
    usable = gr.step_free_nodes(cx, "N")
    assert 2 not in usable                       # B is not step-free
    reach = gr.reachable_pairs(g, usable)
    assert 3 in reach[1]                         # A still reaches C


def test_disabled_complex_stays_passable(toy_model):
    """Disabling a complex removes it as an endpoint, not as a through route.

    If an outage at C were modelled as a cut in the graph, the pair A to E
    would die with it. It must survive.
    """
    model, cx, edges = toy_model
    base = model.served_flow()
    without_c = model.served_flow(disabled={3})
    assert without_c < base
    g = gr.build_graph(edges, "N")
    usable = gr.step_free_nodes(cx, "N") - {3}
    reach = gr.reachable_pairs(g, usable)
    assert 5 in reach[1], "A to E must survive an outage at the station between them"


def test_removal_never_increases_served_flow(toy_model):
    model, cx, _ = toy_model
    base = model.served_flow()
    for c in (1, 2, 3, 4, 5):
        assert model.served_flow(disabled={c}) <= base + 1e-9


def test_removing_an_inaccessible_complex_changes_nothing(toy_model):
    """B is not step-free, so it cannot be lost."""
    model, _, _ = toy_model
    assert model.served_flow(disabled={2}) == pytest.approx(model.served_flow())


def test_adding_a_complex_never_decreases_served_flow(toy_model):
    model, _, _ = toy_model
    base = model.served_flow()
    assert model.served_flow(added={2}) >= base - 1e-9


def test_reachability_masks_do_not_depend_on_accessibility(toy_model):
    """The optimisation rests on this; if it is false the speed-up is a bug."""
    model, cx, edges = toy_model
    before = {d: m.copy() for d, m in model._reach_mask.items()}
    model.served_flow(disabled={1, 3, 5})
    model.served_flow(added={2})
    for d, m in before.items():
        assert (model._reach_mask[d] == m).all()


def test_direction_matters_for_the_partial_station(toy_stations, toy_topology, toy_od):
    """D is northbound only, so it serves as an endpoint in one direction only."""
    acc = ada.station_accessibility(toy_stations)
    cx = ada.complex_accessibility(acc)
    edges = gr.build_edges(toy_topology, toy_stations, min_trains=1)
    assert 4 in gr.step_free_nodes(cx, "N")
    assert 4 not in gr.step_free_nodes(cx, "S")
