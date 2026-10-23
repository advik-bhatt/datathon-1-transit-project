"""Paths and the New York open-data resources this project reads."""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("ACCESSNET_DATA", REPO_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
PROC_DIR = DATA_DIR / "processed"
RESULTS_DIR = REPO_ROOT / "results"
FIG_DIR = RESULTS_DIR / "figures"

for _d in (RAW_DIR, PROC_DIR, RESULTS_DIR, FIG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Socrata hosts. An app token raises rate limits but is not required; every
# query in this project runs unauthenticated.
NY_DOMAIN = "data.ny.gov"
NYC_DOMAIN = "data.cityofnewyork.us"
APP_TOKEN = os.environ.get("SOCRATA_APP_TOKEN")

# ------------------------------------------------------------- datasets -----
# Row counts are the values observed when this project was built, recorded so
# that a later run can notice the data moved under it.
DATASETS = {
    # Network topology. Two sources, deliberately:
    #  - "schedules" is the authoritative one. It carries gtfs_stop_id, which
    #    joins directly to the accessibility table. 84.4M rows, so the stop
    #    sequences are extracted with a server-side GROUP BY.
    #  - "paths" is smaller and easier to read but only populates its numeric
    #    station_id for the numbered IRT lines; for the lettered BMT and IND
    #    lines the column is null, so it cannot carry the whole network. It is
    #    kept for cross-checking distances only.
    "schedules": ("NY", "q9nv-uegs", 84_404_962),
    "paths": ("NY", "tdmq-asac", 111_123),
    # Station level, carrying the DIRECTIONAL accessibility flags.
    "stations": ("NY", "39hk-dx4f", 496),
    # Complex level: the unit riders actually experience, and the unit the
    # equipment and ridership datasets key on.
    "complexes": ("NY", "5f5g-n3cz", 445),
    # Every elevator and escalator, with install dates and the free-text note
    # that is the only public description of which vertical segment it serves.
    "equipment": ("NY", "94fv-bak7", 759),
    # Monthly availability and outage counts per unit since 2015.
    "availability": ("NY", "rc78-7x78", 83_776),
    # The agency's own accessible-platform metric, borough-aggregated.
    "platform_availability": ("NY", "thh2-syn7", 525),
    # Hourly station-to-station ridership estimates.
    "od_2024": ("NY", "jsu2-fbtj", 116_279_069),
    "od_2025": ("NY", "y2qv-fytt", None),
    # Hourly ridership by station complex.
    "ridership_2020_2024": ("NY", "wujg-7c2s", 120_855_567),
    "ridership_2025": ("NY", "5wq4-mkjj", 46_658_853),
    # Rider-reported problems.
    "feedback": ("NY", "nh7m-at3e", 1_681_415),
    "alerts": ("NY", "7kct-peq7", 525_083),
    # City-side complaints, for the cross-agency view.
    "nyc_311": ("NYC", "erm2-nwe9", None),
}

DOMAINS = {"NY": NY_DOMAIN, "NYC": NYC_DOMAIN}

# ---------------------------------------------------- accessibility codes ---
# From the MTA station tables. 1 is fully accessible, 2 is partially
# accessible with the restriction described in free text, 0 is not accessible.
ADA_FULL, ADA_PARTIAL, ADA_NONE = 1, 2, 0

# Directions as the paths dataset labels them.
NORTH, SOUTH = "N", "S"
