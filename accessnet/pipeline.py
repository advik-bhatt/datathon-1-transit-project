"""One place that assembles the model, so every entry point agrees."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from . import ada, availability as avm, equipment as eqm, graph as gr
from .damage import ReachabilityModel
from .ingest import mta

log = logging.getLogger(__name__)


@dataclass
class Context:
    stations: pd.DataFrame
    complexes: pd.DataFrame
    cx_access: pd.DataFrame
    station_access: pd.DataFrame
    edges: pd.DataFrame
    od: pd.DataFrame
    model: ReachabilityModel
    assets: pd.DataFrame
    criticality: pd.DataFrame
    unavail: pd.DataFrame
    dependent: pd.DataFrame
    ridership: pd.DataFrame
    platform_av: pd.DataFrame

    def names(self) -> pd.DataFrame:
        n = self.complexes[["complex_id", "display_name", "borough"]].copy()
        n["complex_id"] = pd.to_numeric(n["complex_id"], errors="coerce")
        return n

    def sweep_candidates(self) -> list[int]:
        d = self.dependent
        return sorted(set(d.loc[d["elevator_dependent"], "complex_id"]
                          .dropna().astype(int)))


def build(force: bool = False, od_key: str = "od_2024",
          unavail_months: int = 24) -> Context:
    stations = mta.load_stations(force)
    complexes = mta.load_complexes(force)
    topology = mta.load_topology(force)
    equipment = mta.load_equipment(force)
    av = mta.load_availability(force)
    platform_av = mta.load_platform_availability(force)
    od = mta.load_od_matrix(od_key, force)
    ridership = mta.load_complex_ridership(force)

    station_access = ada.station_accessibility(stations)
    cx_access = ada.complex_accessibility(station_access)
    edges = gr.build_edges(topology, stations)
    model = ReachabilityModel(edges, cx_access, od)
    assets = avm.age_features(eqm.build_assets(equipment))
    criticality = eqm.asset_criticality(assets)
    unavail = avm.unavailability(av, months=unavail_months)
    dependent = eqm.elevator_dependent_complexes(cx_access, assets)

    return Context(stations=stations, complexes=complexes, cx_access=cx_access,
                   station_access=station_access, edges=edges, od=od, model=model,
                   assets=assets, criticality=criticality, unavail=unavail,
                   dependent=dependent, ridership=ridership,
                   platform_av=platform_av)
