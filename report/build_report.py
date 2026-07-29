"""Assemble report/index.html from results/ + report/template.html."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"

TTK_SERIES = ["ak47", "m4a1_silencer", "awp", "mp9", "famas", "glock"]
SPRAY_SERIES = ["ak47", "m4a1_silencer", "negev"]
DUEL_COLS = [5.0, 10.0, 20.0, 30.0, 40.0]
DUEL_ROWS = ["awp", "m4a1_silencer", "ak47", "sg556", "m4a1", "g3sg1", "aug",
             "famas", "galilar", "mp9", "mp5sd", "ump45", "p90", "xm1014",
             "mag7", "tec9", "cz75a", "deagle", "glock"]
CADENCE_ROWS = ["ak47", "m4a1_silencer", "famas", "galilar", "mp9", "ump45",
                "negev", "xm1014"]
CADENCE_COLS = [10.0, 20.0, 30.0]
HEAD_ROWS = ["deagle", "ssg08", "ak47", "sg556", "awp", "m4a1_silencer", "mp9"]


CATEGORY_PT = {
    "Pistols": "Pistolas", "Shotguns": "Escopetas", "SMGs": "SMGs",
    "Automatic Rifles": "Rifles automáticos", "LMGs": "Metralhadoras",
    "Sniper Rifles": "Snipers",
}


def cadence_label(mult: float) -> str:
    if mult <= 1.0:
        return "spray"
    if mult <= 2.0:
        return "burst"
    return "tap"


def main() -> None:
    eff = pd.read_csv(RES / "effectiveness.csv")
    duels = pd.read_csv(RES / "duel_vs_ak.csv")
    scores = pd.read_csv(RES / "profile_scores.csv")
    front = pd.read_csv(RES / "pareto.csv")
    picks = pd.read_csv(RES / "budget_picks.csv")
    heads = pd.read_csv(RES / "headshot.csv")
    curves = pd.read_csv(ROOT / "data" / "bullet_curves.csv")
    summary = json.loads((RES / "summary.json").read_text())

    # best-mode collapsed armored effectiveness
    best = (eff[eff.vs_armored].sort_values("expected_ttk")
            .groupby(["engine_name", "distance_m"], as_index=False).first())
    distances = sorted(best.distance_m.unique().tolist())
    names = dict(zip(best.engine_name, best.display_name))

    ttk_lines = {"distances": distances, "series": []}
    for eng in TTK_SERIES:
        g = best[best.engine_name == eng].set_index("distance_m")
        ttk_lines["series"].append({
            "name": names[eng],
            "values": [round(float(g.loc[d, "expected_ttk"]), 3) for d in distances],
        })

    mid = scores[scores.profile == "MID"].set_index("engine_name")
    fmid = front[front.profile == "MID"].set_index("engine_name")
    scatter = [{
        "name": r.display_name, "cat": CATEGORY_PT.get(r.category, r.category),
        "price": float(r.price),
        "score": round(float(r.score_ettk), 3),
        "frontier": bool(fmid.loc[eng, "on_frontier"]),
    } for eng, r in mid.iterrows()]

    dk = duels[duels.i_have_kevlar].set_index(["engine_name", "distance_m"])
    duel_rows = [{
        "name": names[eng],
        "price": float(mid.loc[eng, "price"]),
        "vals": [round(float(dk.loc[(eng, d), "p_win_vs_ak"]), 3) for d in DUEL_COLS],
    } for eng in DUEL_ROWS]

    cad = best.set_index(["engine_name", "distance_m"])
    cadence_rows = [{
        "name": names[eng],
        "cells": [{
            "ms": int(cad.loc[(eng, d), "interval_ms"]),
            "label": cadence_label(float(cad.loc[(eng, d), "cadence_mult"])),
        } for d in CADENCE_COLS],
    } for eng in CADENCE_ROWS]

    hh = heads.set_index(["engine_name", "distance_m"])
    head_rows = [{
        "name": names[eng],
        "cells": [{
            "n": int(hh.loc[(eng, d), "hits_needed"]),
            "ttk": round(float(hh.loc[(eng, d), "expected_ttk"]), 2),
            "p1": round(float(hh.loc[(eng, d), "first_hit_p"]), 2),
        } for d in [10.0, 20.0]],
    } for eng in HEAD_ROWS]

    # budget picks -> consecutive ranges
    ranges = []
    for _, r in picks.sort_values("budget").iterrows():
        key = (r.display_name, bool(r.kevlar))
        if ranges and (ranges[-1]["name"], ranges[-1]["kevlar"]) == key:
            ranges[-1]["hi"] = int(r.budget)
        else:
            ranges.append({"lo": int(r.budget), "hi": int(r.budget),
                           "name": r.display_name, "kevlar": bool(r.kevlar),
                           "cost": int(r.cost),
                           "pwin": round(float(r.p_win_vs_ak_mid), 3)})

    cs = curves[(curves.stance == "stand") & (curves["mode"] == "primary")
                & (curves.bullet <= 30)]
    spray = {"bullets": list(range(1, 31)), "series": []}
    for eng in SPRAY_SERIES:
        g = cs[cs.engine_name == eng].sort_values("bullet")
        spray["series"].append({"name": names[eng],
                                "values": [round(float(v), 2)
                                           for v in g.total_inaccuracy]})

    data = {
        "generated": summary["generated"],
        "budget_ranges": ranges, "ttk_lines": ttk_lines, "scatter": scatter,
        "duels": {"cols": [int(c) for c in DUEL_COLS], "rows": duel_rows},
        "cadence": {"cols": [int(c) for c in CADENCE_COLS], "rows": cadence_rows},
        "headshot": head_rows, "spray": spray,
    }

    tpl = (ROOT / "report" / "template.html").read_text()
    html = tpl.replace("/*__DATA__*/", json.dumps(data, separators=(",", ":")))
    out = ROOT / "report" / "index.html"
    out.write_text(html)
    print(f"wrote {out} ({len(html)//1024} KB)")


if __name__ == "__main__":
    main()
