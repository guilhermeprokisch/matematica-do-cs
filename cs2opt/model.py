"""Stochastic engagement model: expected time-to-kill under real spread.

The classic TTK tables assume every bullet hits. That makes the Negev look
like the best gun in the game. What actually separates weapons is *hit
probability per bullet*, which degrades with distance and spray length.

Geometry (validated against the sheet's own 'Accurate Range' columns):
  deviation radius at distance d  =  inaccuracy / 1000 * d   [meters]
  ('accurate range' in the sheet == distance where total inaccuracy keeps
   shots inside a 1-foot circle: 152.4 / inaccuracy  ==  0.1524m radius)

Each shot's deviation is sampled as the sum of two uniform-disc draws, the
way the engine does it: one for accumulated inaccuracy (shared by all
pellets of a shell), one for Spread (per pellet).

Kill condition: N chest hits, N = ceil(100 / dmg(d)), with
  dmg(d) = Damage * [ArmorPen if armored] * RangeModifier^(d_units / 500)
which reproduces the sheet's 'Damage @Range(Armor)' table exactly.

Simplifications (documented, roughly rank-neutral):
  - aim is centered on the chest; recoil is assumed compensated (spray
    control), so only engine inaccuracy + spread remain
  - all hits are chest hits (no stomach/head mixing)
  - reload resets spray inaccuracy to base
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

UNIT_M = 0.0254
CHEST_RADIUS_M = 0.17   # torso as a disc; ~34cm effective width
HEAD_RADIUS_M = 0.10
HP = 100.0
SCOPE_IN_S = 0.30       # commit time before the first accurate scoped shot


@dataclass
class WeaponConfig:
    engine_name: str
    display_name: str
    category: str
    price: float
    kill_award: float
    damage: float
    armor_pen: float
    range_modifier: float
    cycle_time: float
    mag_size: int
    pellets: int
    reload_time: float
    spread: float                 # constant per-pellet spread component
    curve: np.ndarray             # total inaccuracy per bullet (incl. spread)
    fire_inacc: float = 0.0       # inaccuracy added per shot
    decay: float = 0.0            # per-cycle exponential recovery factor
    hs_mult: float = 4.0
    mode: str = "primary"
    move_speed: float = 250.0


@dataclass
class TTKResult:
    expected_ttk: float           # E[min(TTK, cap)]
    median_ttk: float
    p_kill_1s: float
    p_kill_2s: float
    p_kill: float                 # within cap
    hits_needed: int
    first_hit_p: float
    perfect_ttk: float            # all-bullets-hit reference
    samples: np.ndarray = field(repr=False, default=None)


def load_weapons(data_dir) -> dict[tuple[str, str], WeaponConfig]:
    w = pd.read_csv(f"{data_dir}/weapons.csv")
    curves = pd.read_csv(f"{data_dir}/bullet_curves.csv")
    params = pd.read_csv(f"{data_dir}/spray_params.csv")
    out = {}
    for _, r in w.iterrows():
        for mode in ("primary", "scoped"):
            cur = curves[(curves.engine_name == r.engine_name)
                         & (curves["mode"] == mode) & (curves.stance == "stand")]
            if cur.empty:
                continue
            par = params[(params.engine_name == r.engine_name)
                         & (params["mode"] == mode)
                         & (params.stance == "stand")].iloc[0]
            spread = r.spread if mode == "primary" else r.spread_alt
            cycle = r.cycle_time
            if mode == "scoped" and not math.isnan(r.cycle_time_alt):
                cycle = r.cycle_time_alt
            out[(r.engine_name, mode)] = WeaponConfig(
                engine_name=r.engine_name, display_name=r.display_name,
                category=r.category, price=r.price, kill_award=r.kill_award,
                damage=r.damage, armor_pen=r.armor_pen,
                range_modifier=r.range_modifier, cycle_time=cycle,
                mag_size=int(r.mag_size), pellets=int(r.pellets),
                reload_time=r.reload_fire_ready,
                spread=spread,
                curve=cur.sort_values("bullet").total_inaccuracy.to_numpy(),
                fire_inacc=par.fire_inacc, decay=par.decay_per_cycle,
                hs_mult=r.hs_mult, mode=mode, move_speed=r.move_speed,
            )
    return out


def damage_at(w: WeaponConfig, dist_m: float, armored: bool,
              aim: str = "chest") -> float:
    d_units = dist_m / UNIT_M
    dmg = w.damage * (w.armor_pen if armored else 1.0)
    if aim == "head":
        dmg *= w.hs_mult
    return dmg * (w.range_modifier ** (d_units / 500.0))


def hits_needed(w: WeaponConfig, dist_m: float, armored: bool,
                aim: str = "chest") -> int:
    dmg = damage_at(w, dist_m, armored, aim)
    if dmg < 0.5:
        return 10_000
    return int(math.ceil(HP / dmg))


def _uniform_disc(rng, shape) -> tuple[np.ndarray, np.ndarray]:
    r = np.sqrt(rng.random(shape))
    th = rng.random(shape) * 2 * np.pi
    return r * np.cos(th), r * np.sin(th)


def _inacc_sequence(w: WeaponConfig, interval_mult: float) -> np.ndarray:
    """Per-bullet total inaccuracy within one magazine for a firing cadence.

    interval_mult=1 -> continuous spray, use the sheet curve verbatim
    (captures Negev's laser mechanic). Slower cadences use the fitted
    recovery recurrence with decay^mult.
    """
    if interval_mult <= 1.0:
        return w.curve
    base = float(w.curve[0])
    d_eff = w.decay ** interval_mult
    seq, cur = [], base
    for _ in range(len(w.curve)):
        seq.append(cur)
        cur = base + (cur - base + w.fire_inacc) * d_eff
    return np.array(seq)


def simulate_ttk(w: WeaponConfig, dist_m: float, armored: bool = True,
                 target_radius: float = CHEST_RADIUS_M, trials: int = 4000,
                 time_cap: float = 12.0, max_mags: int = 3,
                 interval_mult: float = 1.0, aim: str = "chest",
                 rng: np.random.Generator | None = None,
                 keep_samples: bool = False) -> TTKResult:
    rng = rng or np.random.default_rng(7)
    n_need = hits_needed(w, dist_m, armored, aim)
    perfect = _perfect_ttk(w, n_need)
    if n_need > w.mag_size * max_mags * w.pellets:
        return TTKResult(time_cap, time_cap, 0.0, 0.0, 0.0, n_need, 0.0, math.inf)

    # shot schedule across mags
    interval = w.cycle_time * interval_mult
    n_shots = w.mag_size * max_mags
    idx_in_mag = np.arange(n_shots) % w.mag_size
    mag_no = np.arange(n_shots) // w.mag_size
    delay = SCOPE_IN_S if w.mode == "scoped" else 0.0
    times = delay + idx_in_mag * interval + mag_no * (w.mag_size * interval
                                                      + w.reload_time)
    keep = times <= time_cap
    idx_in_mag, times = idx_in_mag[keep], times[keep]
    n_shots = len(times)
    if n_shots == 0:
        return TTKResult(time_cap, time_cap, 0.0, 0.0, 0.0, n_need, 0.0, perfect)

    curve = _inacc_sequence(w, interval_mult)
    inacc_total = curve[np.minimum(idx_in_mag, len(curve) - 1)]
    r_inacc = np.maximum(inacc_total - w.spread, 0.0) / 1000.0 * dist_m
    r_spread = w.spread / 1000.0 * dist_m

    # inaccuracy draw: shared across pellets of a shell
    ix, iy = _uniform_disc(rng, (trials, n_shots))
    ix, iy = ix * r_inacc, iy * r_inacc
    if w.pellets > 1:
        sx, sy = _uniform_disc(rng, (trials, n_shots, w.pellets))
        dx = ix[:, :, None] + sx * r_spread
        dy = iy[:, :, None] + sy * r_spread
        hits = (dx * dx + dy * dy <= target_radius ** 2).sum(axis=2)
    else:
        sx, sy = _uniform_disc(rng, (trials, n_shots))
        dx, dy = ix + sx * r_spread, iy + sy * r_spread
        hits = (dx * dx + dy * dy <= target_radius ** 2).astype(np.int32)

    cum = np.cumsum(hits, axis=1)
    killed = cum >= n_need
    any_kill = killed.any(axis=1)
    first = np.argmax(killed, axis=1)
    ttk = np.where(any_kill, times[first], time_cap)

    first_hit_p = float((hits[:, 0] > 0).mean())
    return TTKResult(
        expected_ttk=float(ttk.mean()), median_ttk=float(np.median(ttk)),
        p_kill_1s=float((ttk <= 1.0).mean()), p_kill_2s=float((ttk <= 2.0).mean()),
        p_kill=float(any_kill.mean()), hits_needed=n_need,
        first_hit_p=first_hit_p, perfect_ttk=perfect,
        samples=ttk if keep_samples else None,
    )


def _perfect_ttk(w: WeaponConfig, n_need: int) -> float:
    if n_need >= 10_000:
        return math.inf
    shells = math.ceil(n_need / w.pellets)
    full_mags = (shells - 1) // w.mag_size
    delay = SCOPE_IN_S if w.mode == "scoped" else 0.0
    return delay + (shells - 1) * w.cycle_time + full_mags * w.reload_time


CADENCE_MULTS = (1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 9.0)


def best_policy_ttk(w: WeaponConfig, dist_m: float, armored: bool = True,
                    target_radius: float = CHEST_RADIUS_M, trials: int = 4000,
                    time_cap: float = 12.0, aim: str = "chest",
                    rng: np.random.Generator | None = None,
                    keep_samples: bool = False) -> tuple[TTKResult, float]:
    """Expected TTK under the *optimal fire cadence* for this range.

    Tries continuous spray plus slower tap/burst cadences (which let engine
    inaccuracy recover between shots) and keeps the best. Intervals beyond
    1.5s are pointless — a player would just re-peek.
    """
    best, best_mult = None, 1.0
    for mult in CADENCE_MULTS:
        if mult > 1.0 and w.cycle_time * mult > 1.5:
            continue
        if mult > 1.0 and w.decay <= 0.0:
            continue  # no recovery data; spray only
        res = simulate_ttk(w, dist_m, armored=armored,
                           target_radius=target_radius, trials=trials,
                           time_cap=time_cap, interval_mult=mult, aim=aim,
                           rng=rng, keep_samples=keep_samples)
        if best is None or res.expected_ttk < best.expected_ttk:
            best, best_mult = res, mult
    return best, best_mult
