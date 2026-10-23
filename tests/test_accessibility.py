"""Accessibility must stay directional, and the parse must agree with the flags."""
from __future__ import annotations

import pandas as pd

from accessnet import ada


def test_directional_flags_are_not_collapsed(toy_stations):
    acc = ada.station_accessibility(toy_stations)
    d = acc.set_index("stop_name")
    assert d.loc["A", "step_free_both"]
    assert not d.loc["B", "step_free_any"]
    # The partial station is usable one way only; a binary model loses this.
    assert d.loc["D", "step_free_north"]
    assert not d.loc["D", "step_free_south"]
    assert d.loc["D", "step_free_any"]
    assert not d.loc["D", "step_free_both"]


def test_complex_rollup_keeps_direction(toy_stations):
    acc = ada.station_accessibility(toy_stations)
    cx = ada.complex_accessibility(acc).set_index("complex_id")
    assert cx.loc[4, "step_free_north"]
    assert not cx.loc[4, "step_free_south"]


def test_route_restriction_is_flagged_not_ignored():
    """'Uptown local only' restricts which trains, not just which direction."""
    df = pd.DataFrame([{
        "gtfs_stop_id": "X", "station_id": 9, "complex_id": 9, "ada": 2,
        "ada_northbound": 1, "ada_southbound": 0,
        "ada_notes": "Uptown local only", "stop_name": "86 St",
        "daytime_routes": "4 5 6", "borough": "M",
        "gtfs_latitude": 40.0, "gtfs_longitude": -74.0,
        "north_direction_label": "", "south_direction_label": "",
    }])
    acc = ada.station_accessibility(df)
    assert bool(acc["route_restricted"].iloc[0])


def test_notes_and_structured_flags_agree_on_real_data():
    """The whole directed model rests on the flags; this is the cross-check.

    Skipped when the cached station table is not present, so the suite still
    runs on a fresh clone before any download.
    """
    import pytest

    from accessnet.config import RAW_DIR

    p = RAW_DIR / "stations.parquet"
    if not p.exists():
        pytest.skip("station table not downloaded")
    from accessnet.ingest import mta

    acc = ada.station_accessibility(mta.load_stations())
    v = ada.validate_notes_against_flags(acc)
    assert len(v) > 0
    # No note may contradict the structured flags. Direction-ambiguous
    # phrasings such as "Outbound only" come back as None, not False.
    assert int((v["agrees"] == False).sum()) == 0  # noqa: E712
