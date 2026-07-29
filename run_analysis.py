"""End-to-end: parse xlsx -> MC sweep -> optimization -> results/ CSVs + JSON."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from cs2opt import optimize as opt
from cs2opt.model import load_weapons
from cs2opt.parse import main as parse_main

ROOT = Path(__file__).resolve().parent


def main() -> None:
    t0 = time.time()
    parse_main(ROOT / "data/source/weapon_spreadsheet.xlsx", ROOT / "data")
    ws = load_weapons(ROOT / "data")
    print(f"[{time.time()-t0:5.1f}s] weapons loaded: {len(ws)} configs")

    df, samples = opt.sweep(ws, trials=5000)
    print(f"[{time.time()-t0:5.1f}s] sweep done: {len(df)} rows")

    duels = opt.duel_table(df, samples)
    scores = opt.profile_scores(df, duels)
    front = opt.pareto(scores)
    picks = opt.budget_picks(scores, duels)
    heads = opt.head_sweep(ws, trials=5000)
    print(f"[{time.time()-t0:5.1f}s] optimization done")

    outdir = ROOT / "results"
    outdir.mkdir(exist_ok=True)
    df.drop(columns=[]).to_csv(outdir / "effectiveness.csv", index=False)
    duels.to_csv(outdir / "duel_vs_ak.csv", index=False)
    scores.to_csv(outdir / "profile_scores.csv", index=False)
    front.to_csv(outdir / "pareto.csv", index=False)
    picks.to_csv(outdir / "budget_picks.csv", index=False)
    heads.to_csv(outdir / "headshot.csv", index=False)

    best = opt.collapse_modes(df[df.vs_armored])
    curves = pd.read_csv(ROOT / "data/bullet_curves.csv")
    weapons = pd.read_csv(ROOT / "data/weapons.csv")
    summary = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "distances_m": opt.DISTANCES,
        "profiles": {k: {str(d): w for d, w in v.items()}
                     for k, v in opt.PROFILES.items()},
        "weapons": weapons[["engine_name", "display_name", "category", "price",
                            "kill_award", "damage", "armor_pen", "range_modifier",
                            "cycle_time", "mag_size", "move_speed",
                            "reload_fire_ready"]].to_dict("records"),
        "effectiveness_armored": best.to_dict("records"),
        "duels": duels.to_dict("records"),
        "profile_scores": scores.to_dict("records"),
        "pareto": front.to_dict("records"),
        "budget_picks": picks.to_dict("records"),
        "headshot": heads.to_dict("records"),
        "spray_curves_stand": (
            curves[(curves.stance == "stand") & (curves["mode"] == "primary")
                   & (curves.bullet <= 30)]
            .to_dict("records")),
    }
    (outdir / "summary.json").write_text(json.dumps(summary, indent=1))
    print(f"[{time.time()-t0:5.1f}s] wrote {outdir}/summary.json")

    # console highlights
    mid = scores[scores.profile == "MID"].sort_values("score_ettk")
    print("\nTop 10, MID profile (10-20m), vs armored, optimal cadence:")
    print(mid[["display_name", "price", "score_ettk", "p_win_vs_ak"]]
          .head(10).to_string(index=False))
    print("\nBudget picks (every $400):")
    p = picks[picks.budget % 400 == 0]
    print(p[["budget", "display_name", "kevlar", "cost", "p_win_vs_ak_mid"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
