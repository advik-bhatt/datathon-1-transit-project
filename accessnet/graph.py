"""The subway as a directed graph, and the step-free subgraph inside it.

Nodes are station complexes, because that is the unit a rider experiences, the
unit the ridership and origin-destination data key on, and the unit the
equipment data points at. Edges are directed and labelled by line: an edge
exists from complex A to complex B in direction d if some published stopping
pattern on some line calls at A and then B consecutively in that direction.

The step-free subgraph is then the same graph with two restrictions:

* a rider can only START a trip at a complex whose platform for their
  direction of travel is step-free, and can only FINISH at one likewise, so
  the directional flags decide which nodes are usable per direction;
* a rider stays aboard between those points, so intermediate complexes do not
  need to be accessible. This is why the problem is a reachability problem on
  a subgraph and not a simple count of accessible stations.

Transfers are the one place where open data runs out. Whether a specific
in-complex transfer between two lines is step-free is not published in a
machine-readable form. The model therefore assumes a transfer inside a complex
is step-free when the complex is step-free in both the arriving and departing
directions, and `TRANSFER_ASSUMPTION` records that in one place so it can be
cited, tightened, or relaxed rather than buried.
"""
from __future__ import annotations

import logging

import networkx as nx
import pandas as pd

from .config import NORTH, SOUTH

log = logging.getLogger(__name__)

TRANSFER_ASSUMPTION = (
    "A transfer between lines inside one station complex is treated as step-free "
    "when the complex is step-free in both the arriving and the departing "
    "direction. Open data does not publish per-transfer step-free status, so "
    "this is an assumption, and it is optimistic: it can only overstate "
    "reachability, never understate it."
)

# A stopping pattern operated by fewer than this many trains over the schedule
# year is treated as a special move rather than part of the network.
MIN_TRAINS_PER_PATTERN = 50


def station_to_complex(stations: pd.DataFrame) -> pd.DataFrame:
    """Map each gtfs_stop_id to its complex."""
    s = stations[["gtfs_stop_id", "station_id", "complex_id", "stop_name"]].copy()
    s["gtfs_stop_id"] = s["gtfs_stop_id"].astype(str).str.strip()
    s["complex_id"] = pd.to_numeric(s["complex_id"], errors="coerce")
    return s.dropna(subset=["complex_id"])


def build_edges(topology: pd.DataFrame, stations: pd.DataFrame,
                min_trains: int = MIN_TRAINS_PER_PATTERN) -> pd.DataFrame:
    """Consecutive complex pairs per line and direction."""
    t = topology.copy()
    t["gtfs_stop_id"] = t["gtfs_stop_id"].astype(str).str.strip()
    t["stop_order"] = pd.to_numeric(t["stop_order"], errors="coerce")
    if "n_trains" in t.columns:
        heavy = t.groupby("path_id")["n_trains"].transform("max") >= min_trains
        dropped = int((~heavy).sum())
        if dropped:
            log.info("dropping %d topology rows from rarely-operated patterns", dropped)
        t = t[heavy]

    s2c = station_to_complex(stations)
    t = t.merge(s2c[["gtfs_stop_id", "complex_id"]], on="gtfs_stop_id", how="left")
    unmatched = int(t["complex_id"].isna().sum())
    if unmatched:
        log.warning("%d topology rows had no matching complex and are dropped", unmatched)
    t = t.dropna(subset=["complex_id", "stop_order"]).sort_values(["path_id", "stop_order"])

    t["next_complex"] = t.groupby("path_id")["complex_id"].shift(-1)
    e = t.dropna(subset=["next_complex"]).copy()
    # A pattern that skips a stop still connects the two complexes it serves.
    e = e[e["complex_id"] != e["next_complex"]]
    edges = (e.groupby(["complex_id", "next_complex", "line", "direction"], as_index=False)
              .agg(n_patterns=("path_id", "nunique"),
                   n_trains=("n_trains", "sum") if "n_trains" in e.columns
                   else ("path_id", "size")))
    return edges.rename(columns={"complex_id": "u", "next_complex": "v"})


def build_graph(edges: pd.DataFrame, direction: str | None = None) -> nx.DiGraph:
    """A directed multigraph collapsed to one edge per complex pair."""
    e = edges if direction is None else edges[edges["direction"] == direction]
    g = nx.DiGraph()
    for r in e.itertuples():
        u, v = int(r.u), int(r.v)
        if g.has_edge(u, v):
            g[u][v]["lines"].add(r.line)
            g[u][v]["n_trains"] += float(getattr(r, "n_trains", 0) or 0)
        else:
            g.add_edge(u, v, lines={r.line}, n_trains=float(getattr(r, "n_trains", 0) or 0))
    return g


def step_free_nodes(cx_access: pd.DataFrame, direction: str) -> set[int]:
    """Complexes whose platform for this direction of travel is step-free."""
    col = "step_free_north" if direction == NORTH else "step_free_south"
    sel = cx_access[cx_access[col].fillna(False)]
    return {int(c) for c in sel["complex_id"].dropna()}


def reachable_pairs(graph: nx.DiGraph, usable: set[int],
                    sources: set[int] | None = None) -> dict[int, set[int]]:
    """Which usable complexes can be reached from each usable complex.

    Travel may pass through complexes that are not step-free, because the
    rider stays on the train, so the search runs on the full graph and only
    the endpoints are restricted to `usable`.
    """
    src = sources if sources is not None else usable
    out: dict[int, set[int]] = {}
    for s in src:
        if s not in graph:
            out[s] = set()
            continue
        reached = nx.descendants(graph, s)
        out[s] = (reached & usable) - {s}
    return out


def directed_step_free_reach(edges: pd.DataFrame, cx_access: pd.DataFrame,
                             removed: set[int] | None = None) -> dict[str, dict[int, set[int]]]:
    """Step-free reachability per direction, optionally with complexes removed.

    `removed` names complexes whose step-free access is currently unavailable,
    for instance because an elevator is out. A removed complex is still
    passable by a rider who stays aboard; it simply stops being a usable
    origin or destination. Modelling it any other way would overstate the
    damage an outage does.
    """
    out: dict[str, dict[int, set[int]]] = {}
    gone = removed or set()
    for d in (NORTH, SOUTH):
        g = build_graph(edges, direction=d)
        usable = step_free_nodes(cx_access, d) - gone
        out[d] = reachable_pairs(g, usable)
    return out


def graph_summary(edges: pd.DataFrame, cx_access: pd.DataFrame) -> dict:
    """Shape of the network and of the step-free subgraph inside it."""
    gn = build_graph(edges, NORTH)
    gs = build_graph(edges, SOUTH)
    res = {
        "n_complexes_in_graph": len(set(gn.nodes) | set(gs.nodes)),
        "n_edges_north": gn.number_of_edges(),
        "n_edges_south": gs.number_of_edges(),
        "step_free_nodes_north": len(step_free_nodes(cx_access, NORTH)),
        "step_free_nodes_south": len(step_free_nodes(cx_access, SOUTH)),
    }
    for d, g in ((NORTH, gn), (SOUTH, gs)):
        usable = step_free_nodes(cx_access, d) & set(g.nodes)
        reach = reachable_pairs(g, usable)
        res[f"step_free_pairs_{d}"] = sum(len(v) for v in reach.values())
        res[f"all_pairs_{d}"] = sum(len(nx.descendants(g, n)) for n in g.nodes)
    res["step_free_pairs_total"] = res["step_free_pairs_N"] + res["step_free_pairs_S"]
    res["all_pairs_total"] = res["all_pairs_N"] + res["all_pairs_S"]
    res["step_free_pair_share_pct"] = round(
        100.0 * res["step_free_pairs_total"] / max(res["all_pairs_total"], 1), 2
    )
    return res
