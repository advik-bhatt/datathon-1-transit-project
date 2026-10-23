"""Command line entry points.

    python -m accessnet.cli fetch        download every dataset
    python -m accessnet.cli accessibility  directional step-free audit
    python -m accessnet.cli equipment    elevator vertical-path model
    python -m accessnet.cli damage       reachability damage per elevator
    python -m accessnet.cli capital      which stations to make step-free next
    python -m accessnet.cli metrics      flow-weighted availability vs published
    python -m accessnet.cli figures      render the report figures
    python -m accessnet.cli all          everything, in order
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings

import pandas as pd

from . import ada, capital as cap, config, damage as dm, equipment as eqm, graph as gr
from . import metrics as mt
from . import pipeline
from .ingest import mta

log = logging.getLogger("accessnet")


def _setup(verbose: bool = True) -> None:
    warnings.filterwarnings("ignore")
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s",
                        stream=sys.stdout)


def _save(df: pd.DataFrame, name: str) -> None:
    p = config.RESULTS_DIR / name
    df.to_csv(p, index=False)
    log.info("wrote %s (%d rows)", p.relative_to(config.REPO_ROOT), len(df))


def _save_json(obj, name: str) -> None:
    p = config.RESULTS_DIR / name
    p.write_text(json.dumps(obj, indent=2, default=str))
    log.info("wrote %s", p.relative_to(config.REPO_ROOT))


def cmd_fetch(args) -> None:
    out = mta.fetch_all(force=args.force)
    _save_json({k: len(v) for k, v in out.items()}, "fetch_row_counts.json")


def cmd_accessibility(args) -> None:
    stations = mta.load_stations()
    acc = ada.station_accessibility(stations)
    cx = ada.complex_accessibility(acc)
    _save(ada.validate_notes_against_flags(acc), "ada_note_validation.csv")
    _save(cx, "complex_accessibility.csv")
    _save_json(ada.summarize(acc, cx), "accessibility_summary.json")
    edges = gr.build_edges(mta.load_topology(), stations)
    _save(edges, "network_edges.csv")
    _save_json(gr.graph_summary(edges, cx), "graph_summary.json")


def cmd_equipment(args) -> None:
    assets = eqm.build_assets(mta.load_equipment())
    v = eqm.complex_vertical_model(assets)
    _save(v, "complex_vertical_model.csv")
    _save(eqm.asset_criticality(assets), "elevator_criticality.csv")
    _save_json(eqm.summarize(assets, v), "equipment_summary.json")
    from . import availability as avm
    _save_json(avm.base_rates(mta.load_availability()), "availability_base_rates.json")


def cmd_damage(args) -> None:
    ctx = pipeline.build()
    cxd = dm.complex_removal_damage(ctx.model, ctx.sweep_candidates())
    _save(cxd.merge(ctx.names(), on="complex_id", how="left"),
          "complex_removal_damage.csv")
    summary = {}
    for name in ("segment", "any"):
        d = dm.elevator_damage(ctx.criticality, cxd, ctx.unavail, model_name=name)
        _save(d.merge(ctx.names(), on="complex_id", how="left"),
              f"elevator_damage_{name}.csv")
        _save(dm.ranking_comparison(d, ctx.unavail, ctx.ridership),
              f"ranking_comparison_{name}.csv")
        mc = dm.monte_carlo(ctx.model, ctx.criticality, ctx.unavail,
                            n_draws=args.draws, model_name=name)
        summary[name] = mc
        log.info("%s model: mean %.2f%% of step-free trips lost, p90 %.2f%%",
                 name, mc["mean_pct_flow_lost"], mc["p90_pct_flow_lost"])
    _save_json(summary, "monte_carlo.json")


def cmd_capital(args) -> None:
    ctx = pipeline.build()
    res = cap.compare_strategies(ctx.model, ctx.cx_access, ctx.ridership, k=args.k)
    _save_json(res, "capital_strategies.json")
    sel = pd.DataFrame({"complex_id": res["greedy_selection"]})
    sel["rank"] = range(1, len(sel) + 1)
    _save(sel.merge(ctx.names(), on="complex_id", how="left"), "capital_greedy_selection.csv")
    _save(cap.equity_split(res["greedy_selection"], ctx.cx_access), "capital_equity_split.csv")
    log.info("network-aware gain %.2f%%, ridership heuristic %.2f%% (%.1f%% of it), "
             "random %.2f%%", res["greedy_gain_pct"], res["ridership_gain_pct"],
             res["ridership_share_of_greedy"], res["random_mean_gain_pct"])


def cmd_metrics(args) -> None:
    ctx = pipeline.build()
    _save_json(mt.headline(ctx.model, ctx.cx_access), "headline_coverage.json")
    fw = mt.flow_weighted_by_borough(ctx.model, ctx.criticality, ctx.unavail,
                                     ctx.cx_access, n_draws=args.draws)
    _save(fw, "flow_weighted_availability.csv")
    pub = mt.mta_published_platform_availability(ctx.platform_av)
    _save(pub, "mta_published_platform_availability.csv")
    _save(mt.compare_to_published(fw, pub), "availability_comparison.csv")


def cmd_figures(args) -> None:
    from .report import make_figures

    make_figures()


def cmd_all(args) -> None:
    cmd_fetch(args)
    cmd_accessibility(args)
    cmd_equipment(args)
    cmd_damage(args)
    cmd_capital(args)
    cmd_metrics(args)
    cmd_figures(args)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="accessnet", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--quiet", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, **kw):
        s = sub.add_parser(name, **kw)
        s.set_defaults(func=fn, force=False, draws=300, k=20)
        return s

    s = add("fetch", cmd_fetch, help="download every dataset")
    s.add_argument("--force", action="store_true")
    add("accessibility", cmd_accessibility, help="directional step-free audit")
    add("equipment", cmd_equipment, help="elevator vertical-path model")
    s = add("damage", cmd_damage, help="reachability damage per elevator")
    s.add_argument("--draws", type=int, default=300)
    s = add("capital", cmd_capital, help="which stations to make step-free next")
    s.add_argument("--k", type=int, default=20)
    s = add("metrics", cmd_metrics, help="flow-weighted availability vs published")
    s.add_argument("--draws", type=int, default=200)
    add("figures", cmd_figures, help="render the report figures")
    add("all", cmd_all, help="run the whole pipeline")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    _setup(verbose=not args.quiet)
    args.func(args)


if __name__ == "__main__":
    main()
