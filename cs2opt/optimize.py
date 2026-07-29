"""Optimization layer: effectiveness sweep, Pareto frontier, budget picks, duels.

Everything downstream of the Monte Carlo engine:
  - sweep():          E[TTK] for every weapon x distance x armor state,
                      under each weapon's *optimal* fire cadence
  - duel win probs:   P(you kill an AK-47 player before they kill you),
                      with and without you buying kevlar
  - profile scores:   engagement-range mixes (CQC / MID / LONG)
  - pareto():         weapons not dominated on (price, score)
  - budget_picks():   best loadout (weapon + kevlar?) per budget level
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .model import HEAD_RADIUS_M, WeaponConfig, best_policy_ttk, load_weapons

DISTANCES = [2.5, 5.0, 7.5, 10.0, 12.5, 15.0, 20.0, 25.0, 30.0, 40.0]

PROFILES = {
    "CQC":  {2.5: 0.20, 5.0: 0.40, 7.5: 0.25, 10.0: 0.15},
    "MID":  {10.0: 0.25, 12.5: 0.25, 15.0: 0.30, 20.0: 0.20},
    "LONG": {20.0: 0.30, 25.0: 0.30, 30.0: 0.25, 40.0: 0.15},
}

KEVLAR_PRICE = 650
TIME_CAP = 12.0
REFERENCE = ("ak47", "primary")  # duel benchmark opponent

# real usage: snipers are fired scoped; AUG/SG players scope when it helps
SNIPERS = {"awp", "g3sg1", "scar20", "ssg08"}


def weapon_modes(ws: dict) -> list[tuple[str, str]]:
    keys = []
    for (name, mode) in ws:
        if name in SNIPERS and mode != "scoped":
            continue
        keys.append((name, mode))
    return keys


def sweep(ws: dict, trials: int = 5000) -> tuple[pd.DataFrame, dict]:
    """Run the full MC sweep. Returns tidy results + raw TTK samples."""
    rows, samples = [], {}
    for (name, mode) in weapon_modes(ws):
        w = ws[(name, mode)]
        for armored in (True, False):
            for d in DISTANCES:
                rng = np.random.default_rng(abs(hash((name, mode, armored, d))) % 2**32)
                res, mult = best_policy_ttk(w, d, armored=armored, trials=trials,
                                            time_cap=TIME_CAP, rng=rng,
                                            keep_samples=True)
                rows.append({
                    "engine_name": name, "mode": mode,
                    "display_name": w.display_name, "category": w.category,
                    "price": w.price, "kill_award": w.kill_award,
                    "distance_m": d, "vs_armored": armored,
                    "hits_needed": res.hits_needed,
                    "expected_ttk": res.expected_ttk,
                    "median_ttk": res.median_ttk,
                    "perfect_ttk": res.perfect_ttk,
                    "p_kill_1s": res.p_kill_1s, "p_kill_2s": res.p_kill_2s,
                    "p_kill": res.p_kill, "first_hit_p": res.first_hit_p,
                    "cadence_mult": mult,
                    "interval_ms": round(w.cycle_time * mult * 1000),
                })
                samples[(name, mode, armored, d)] = res.samples
    return pd.DataFrame(rows), samples


HEAD_DISTANCES = [5.0, 10.0, 15.0, 20.0, 25.0]


def head_sweep(ws: dict, trials: int = 5000) -> pd.DataFrame:
    """Reference table: aim-at-head (vs helmet) expected TTK.

    Corrects the chest-only model's blind spot for one-tap weapons
    (Desert Eagle, SSG 08, AK-47). Head = 10cm-radius disc.
    """
    rows = []
    for (name, mode) in weapon_modes(ws):
        w = ws[(name, mode)]
        for d in HEAD_DISTANCES:
            rng = np.random.default_rng(abs(hash(("head", name, mode, d))) % 2**32)
            res, mult = best_policy_ttk(w, d, armored=True, trials=trials,
                                        target_radius=HEAD_RADIUS_M, aim="head",
                                        time_cap=TIME_CAP, rng=rng)
            rows.append({"engine_name": name, "mode": mode,
                         "display_name": w.display_name, "category": w.category,
                         "price": w.price, "distance_m": d,
                         "hits_needed": res.hits_needed,
                         "expected_ttk": res.expected_ttk,
                         "p_kill_1s": res.p_kill_1s,
                         "first_hit_p": res.first_hit_p,
                         "cadence_mult": mult})
    df = pd.DataFrame(rows)
    return (df.sort_values("expected_ttk")
              .groupby(["engine_name", "distance_m"], as_index=False).first())


def collapse_modes(df: pd.DataFrame) -> pd.DataFrame:
    """One row per weapon x distance x armor: the better of primary/scoped."""
    best = (df.sort_values("expected_ttk")
              .groupby(["engine_name", "distance_m", "vs_armored"], as_index=False)
              .first())
    return best


def duel_table(df: pd.DataFrame, samples: dict) -> pd.DataFrame:
    """P(win a duel vs an armored AK-47 player), by your armor choice.

    Both players start firing at t=0 with optimal cadence. Your armor state
    changes how fast the AK kills *you*.
    """
    rows = []
    best = collapse_modes(df[df.vs_armored])  # you shoot an armored opponent
    ak_vs = {True: {}, False: {}}
    for d in DISTANCES:
        for armored in (True, False):
            ak_vs[armored][d] = samples[(*REFERENCE, armored, d)]
    rng = np.random.default_rng(42)
    for _, r in best.iterrows():
        me = samples[(r.engine_name, r["mode"], True, r.distance_m)]
        for my_armor in (True, False):
            opp = ak_vs[my_armor][r.distance_m]
            perm = rng.permutation(len(opp))[: len(me)]
            o = opp[perm]
            win = float((me < o).mean() + 0.5 * (me == o).mean())
            rows.append({"engine_name": r.engine_name, "display_name": r.display_name,
                         "distance_m": r.distance_m, "i_have_kevlar": my_armor,
                         "p_win_vs_ak": win})
    return pd.DataFrame(rows)


def profile_scores(df: pd.DataFrame, duels: pd.DataFrame) -> pd.DataFrame:
    best = collapse_modes(df[df.vs_armored])
    rows = []
    for name, g in best.groupby("engine_name"):
        g = g.set_index("distance_m")
        d_arm = duels[(duels.engine_name == name) & duels.i_have_kevlar].set_index("distance_m")
        for prof, wts in PROFILES.items():
            ettk = sum(wt * g.loc[d, "expected_ttk"] for d, wt in wts.items())
            pwin = sum(wt * d_arm.loc[d, "p_win_vs_ak"] for d, wt in wts.items())
            rows.append({"engine_name": name,
                         "display_name": g.display_name.iloc[0],
                         "category": g.category.iloc[0],
                         "price": g.price.iloc[0],
                         "kill_award": g.kill_award.iloc[0],
                         "profile": prof, "score_ettk": ettk,
                         "p_win_vs_ak": pwin})
    return pd.DataFrame(rows)


def pareto(scores: pd.DataFrame) -> pd.DataFrame:
    """Weapons not dominated on (price, score_ettk) within each profile."""
    out = []
    for prof, g in scores.groupby("profile"):
        g = g.sort_values(["price", "score_ettk"]).reset_index(drop=True)
        best_so_far = np.inf
        for _, r in g.iterrows():
            if r.score_ettk < best_so_far - 1e-9:
                out.append({**r.to_dict(), "on_frontier": True})
                best_so_far = r.score_ettk
            else:
                out.append({**r.to_dict(), "on_frontier": False})
    return pd.DataFrame(out)


def budget_picks(scores: pd.DataFrame, duels: pd.DataFrame) -> pd.DataFrame:
    """Best (weapon, kevlar?) per budget, maximizing duel win prob vs AK.

    Uses the MID profile duel win probability as the objective — the most
    representative engagement mix — with E[TTK] as tiebreaker.
    """
    mid = scores[scores.profile == "MID"].set_index("engine_name")
    d_by_armor = {}
    for armor in (True, False):
        dd = duels[duels.i_have_kevlar == armor]
        wts = PROFILES["MID"]
        agg = (dd[dd.distance_m.isin(wts)]
               .assign(w=lambda x: x.distance_m.map(wts))
               .groupby("engine_name")
               .apply(lambda g: float((g.p_win_vs_ak * g.w).sum() / g.w.sum()),
                      include_groups=False))
        d_by_armor[armor] = agg
    rows = []
    for budget in range(200, 5901, 100):
        cands = []
        for name, r in mid.iterrows():
            for kev in (True, False):
                cost = r.price + (KEVLAR_PRICE if kev else 0)
                if cost <= budget:
                    cands.append({
                        "budget": budget, "engine_name": name,
                        "display_name": r.display_name, "kevlar": kev,
                        "cost": cost, "leftover": budget - cost,
                        "p_win_vs_ak_mid": d_by_armor[kev][name],
                        "score_ettk_mid": r.score_ettk,
                    })
        if not cands:
            continue
        cands.sort(key=lambda c: (-c["p_win_vs_ak_mid"], c["score_ettk_mid"], c["cost"]))
        rows.append(cands[0])
    return pd.DataFrame(rows)
