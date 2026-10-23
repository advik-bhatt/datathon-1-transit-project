"""The specific MTA tables this project needs, with types fixed on the way in."""
from __future__ import annotations

import logging

import pandas as pd

from ..config import DATASETS, PROC_DIR
from .socrata import cached_query, query

log = logging.getLogger(__name__)


def _spec(key: str) -> tuple[str, str]:
    domain, dataset, _ = DATASETS[key]
    return domain, dataset


def _num(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def load_paths(force: bool = False) -> pd.DataFrame:
    """Ordered stop sequences: the subway's topology, per line and direction."""
    d, ds = _spec("paths")
    df = cached_query("paths", d, ds, force=force,
                      select="stop_path_id,line,direction,station_id,stop_order,"
                             "station_name,number_of_stops,distance",
                      order="stop_path_id,stop_order")
    return _num(df, ["station_id", "stop_order", "number_of_stops", "distance"])


def load_topology(force: bool = False) -> pd.DataFrame:
    """Ordered stop sequences keyed on gtfs_stop_id, from the published schedule.

    The schedule table holds 84.4 million rows, one per train per stop per day.
    Only the distinct route shapes are needed, so the de-duplication runs on the
    server: grouping by (line, direction, path_id, stop_order, gtfs_stop_id)
    collapses a year of trains into roughly one row per stop per stopping
    pattern. `n_trains` is kept because it says how heavily a pattern is
    actually operated, which separates the main line from a handful of special
    moves.

    This table is used instead of the smaller Subway Paths dataset because
    Paths only populates its numeric station_id for the numbered IRT lines; for
    the lettered BMT and IND lines the column is null, so it cannot carry the
    whole network. Paths is still loaded, for its inter-station distances.
    """
    d, ds = _spec("schedules")
    df = cached_query(
        "topology", d, ds, force=force, via_csv=True,
        select="line,direction,path_id,stop_order,gtfs_stop_id,count(*) as n_trains",
        group="line,direction,path_id,stop_order,gtfs_stop_id",
        order="path_id,stop_order", limit=400_000, timeout=1800,
    )
    if df.empty:
        return df
    df = _num(df, ["stop_order", "n_trains"])
    df["gtfs_stop_id"] = df["gtfs_stop_id"].astype(str).str.strip()
    return df


def load_stations(force: bool = False) -> pd.DataFrame:
    """Station level, including the directional accessibility flags."""
    d, ds = _spec("stations")
    df = cached_query("stations", d, ds, force=force)
    df = _num(df, ["station_id", "complex_id", "gtfs_latitude", "gtfs_longitude",
                   "ada", "ada_northbound", "ada_southbound"])
    for c in ("ada_notes", "stop_name", "daytime_routes", "borough",
              "north_direction_label", "south_direction_label"):
        if c in df.columns:
            df[c] = df[c].astype(str).replace({"NaN": "", "nan": "", "None": ""})
    return df


def load_complexes(force: bool = False) -> pd.DataFrame:
    """Complex level: the unit riders experience and the ridership data keys on."""
    d, ds = _spec("complexes")
    df = cached_query("complexes", d, ds, force=force)
    df = _num(df, ["complex_id", "number_of_stations_in_complex",
                   "latitude", "longitude", "ada"])
    for c in ("ada_notes", "stop_name", "display_name", "daytime_routes",
              "borough", "station_ids", "gtfs_stop_ids"):
        if c in df.columns:
            df[c] = df[c].astype(str).replace({"NaN": "", "nan": "", "None": ""})
    return df


def load_equipment(force: bool = False) -> pd.DataFrame:
    """Every elevator and escalator, with the free-text vertical-segment note."""
    d, ds = _spec("equipment")
    df = cached_query("equipment", d, ds, force=force)
    df = _num(df, ["station_mrn", "station_complex_mrn", "x_coordinate",
                   "y_coordinate", "service_life", "escalator_rise",
                   "escalator_number_of_steps", "escalator_step_width"])
    for c in ("equipment_code", "elevator_or_escalator", "asset_class", "notes",
              "street_access", "nyct_owned", "service_status", "subway_line",
              "borough", "station_name", "station_description", "maintained_by"):
        if c in df.columns:
            df[c] = df[c].astype(str).replace({"NaN": "", "nan": "", "None": ""})
    for c in ("original_installation_date", "latest_installation_date"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def load_availability(force: bool = False) -> pd.DataFrame:
    """Monthly per-unit availability, outage counts and entrapments since 2015."""
    d, ds = _spec("availability")
    df = cached_query("availability", d, ds, force=force)
    df = _num(df, ["total_outages", "scheduled_outages", "unscheduled_outages",
                   "entrapments", "time_since_major_improvement",
                   "am_peak_availability", "pm_peak_availability",
                   "_24_hour_availability", "am_peak_hours_available",
                   "am_peak_total_hours", "pm_peak_hours_available",
                   "pm_peak_total_hours", "_24_hour_hours_available",
                   "_24_hour_total_hours", "station_mrn", "station_complex_mrn"])
    if "month" in df.columns:
        df["month"] = pd.to_datetime(df["month"], errors="coerce")
    return df


def load_platform_availability(force: bool = False) -> pd.DataFrame:
    """The agency's own accessible-platform metric, aggregated by borough."""
    d, ds = _spec("platform_availability")
    df = cached_query("platform_availability", d, ds, force=force)
    df = _num(df, ["minutes_platforms_available", "minutes_platforms_in_service",
                   "availability", "platform_count"])
    if "month" in df.columns:
        df["month"] = pd.to_datetime(df["month"], errors="coerce")
    return df


def load_od_matrix(key: str = "od_2024", force: bool = False,
                   weekday_only: bool = True) -> pd.DataFrame:
    """The annual station-pair flow matrix, aggregated ON THE SERVER.

    The source table holds 116 million hourly rows. Grouping it locally is not
    an option, so the sum is pushed to Socrata and only the ~200k pair totals
    come back.
    """
    d, ds = _spec(key)
    where = None
    if weekday_only:
        where = "day_of_week not in ('Saturday','Sunday')"
    name = f"{key}_pairs" + ("_weekday" if weekday_only else "")
    df = cached_query(
        name, d, ds, force=force, via_csv=True,
        select="origin_station_complex_id as o,destination_station_complex_id as d,"
               "sum(estimated_average_ridership) as flow",
        where=where,
        group="origin_station_complex_id,destination_station_complex_id",
        limit=400_000, timeout=1800,
    )
    if df.empty:
        return df
    return _num(df, ["o", "d", "flow"])


def load_od_by_hour(key: str = "od_2024", force: bool = False) -> pd.DataFrame:
    """Pair flows split by hour of day, for the peak-hour view."""
    d, ds = _spec(key)
    df = cached_query(
        f"{key}_pairs_by_hour", d, ds, force=force, via_csv=True,
        select="origin_station_complex_id as o,destination_station_complex_id as d,"
               "hour_of_day as hr,sum(estimated_average_ridership) as flow",
        where="day_of_week not in ('Saturday','Sunday')",
        group="origin_station_complex_id,destination_station_complex_id,hour_of_day",
        limit=3_000_000, timeout=2400,
    )
    if df.empty:
        return df
    return _num(df, ["o", "d", "hr", "flow"])


def load_complex_ridership(force: bool = False) -> pd.DataFrame:
    """Annual ridership per complex, aggregated on the server."""
    frames = []
    for key in ("ridership_2020_2024", "ridership_2025"):
        d, ds = _spec(key)
        df = cached_query(
            f"{key}_by_complex", d, ds, force=force, via_csv=True,
            select="station_complex_id as complex_id,sum(ridership) as riders,"
                   "sum(transfers) as transfers,count(*) as n_rows",
            group="station_complex_id", limit=5_000, timeout=1200,
        )
        if not df.empty:
            df["source"] = key
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    return _num(out, ["complex_id", "riders", "transfers", "n_rows"])


def fetch_all(force: bool = False) -> dict[str, pd.DataFrame]:
    """Pull every table this project needs and report what landed."""
    out = {
        "topology": load_topology(force),
        "paths": load_paths(force),
        "stations": load_stations(force),
        "complexes": load_complexes(force),
        "equipment": load_equipment(force),
        "availability": load_availability(force),
        "platform_availability": load_platform_availability(force),
        "od_pairs": load_od_matrix("od_2024", force),
        "complex_ridership": load_complex_ridership(force),
    }
    for k, v in out.items():
        log.info("%-22s %8d rows", k, len(v))
    return out
