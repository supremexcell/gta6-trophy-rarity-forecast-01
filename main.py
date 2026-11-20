"""GTA VI trophy rarity forecaster (gta6-trophy-rarity-forecast-01).

Forecasts, for every Grand Theft Auto VI trophy on PlayStation 5, the percent
of the players Exophase tracks for the game who will have earned it at the
case's target, as five quantiles (0.05, 0.25, 0.5, 0.75, 0.95) a trophy.

How the grader runs it: `python3 -P -s /bot/main.py` (PYTHONHASHSEED=0) in
python:3.13-slim, standard library only, no network. It reads every <id>.in in
the input directory (the grader runs one case at a time, with only that case's
file there) and writes <id>.out to the output directory:
{"trophies": [{"id": 1, "q": [q05, q25, q50, q75, q95]}, ...]}.

Outside the grader's container, MAKEFUN_INPUT_DIR and MAKEFUN_OUTPUT_DIR
stand in for /input and /output:
    mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py

Method (see METHODOLOGY.md for the full write-up, with sources and dates):
  1. A trophy's earn rate is a ratio: earners / players-tracked. The two move
     for different reasons (players progress through the game; new players
     join the tracked population holding fewer trophies), so the program
     forecasts the two counts separately and divides, instead of fitting the
     ratio directly. A fit on the ratio is contaminated every time Exophase
     refreshes its counts and the tracked population jumps.
  2. History is collapsed to distinct reads (Exophase refreshes its counts on
     its own schedule, hours apart, so most reads repeat the previous one),
     and an observation is dropped when earners apparently fell for most
     trophies between two reads -- earners cannot fall, so the earlier read
     carried seeded or stale rates (launch night's page, which showed every
     trophy near 1% while the tracked population was 638, is the observed
     case: later reads imply fewer earners for late trophies than it did).
  3. Each trophy's earner count and the tracked-player count are fitted as
     least-squares lines of log count on log(1 + hours since the release day
     began, 2026-11-19T00:00Z), over the last 24 hours of distinct reads when
     there are at least 3, else over all of them. The fitted slopes are
     damped for the extrapolation (growth decelerates after launch) and the
     forecasts are capped (earners cannot exceed tracked players, neither
     count can fall, tracked players at most 4x the last read).
  4. When the history shows no movement at all (the practice cases: every
     read identical), there is no trend to fit, so a refresh prior is used:
     Exophase refreshes every few hours, each refresh brings new tracked
     players who hold fewer trophies, so rates are shaded down for short
     horizons; for long horizons a launch prior lets early trophies' earners
     grow faster than the tracked population. Both priors are documented in
     METHODOLOGY.md as judgement, not data.
  5. Medians are then constrained to what the game allows: the story chain
     (Chapter 1 >= Chapter 2 >= Chapter 3 >= Chapter 4 >= final mission >=
     100% completion >= Platinum) is made non-increasing by isotonic
     regression, and the Platinum is capped at the lowest rate of any other
     trophy, since earning it requires earning them all.
  6. Spreads are honest prediction intervals: the fit's residual spread,
     widened for extrapolation distance and small samples, with a floor
     (wider when a trophy has at most 2 earners, because its rate is then
     nearly unmeasured, and for the trophy at 100%). Quantiles are
     logit-normal around the median, clamped to [0.01, 100] and rounded to
     4 decimals.

The program is deterministic: same case in, same bytes out, every run.
"""

import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so `import model`
# finds a module shipped beside this file. (This entry is one file; the line is
# kept so a future split still imports.)
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# The quantile levels the contest scores, in the order each row lists them.
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# The standard normal's quantile at each level.
Z = [-1.6448536269514722, -0.6744897501960817, 0.0, 0.6744897501960817,
     1.6448536269514722]

# --- Documented constants (see METHODOLOGY.md for where each comes from) ---
# Release day begins here; log-time is ln(1 + hours since this instant).
RELEASE_DAY = datetime(2026, 11, 19, 0, 0, 0, tzinfo=timezone.utc)
# How fast a fitted log-time slope is damped when extrapolating: the slope is
# divided by (1 + SLOPE_DAMP * gap), gap the log-time distance to the target.
# Launch growth decelerates; the final case's gap is ~1.3, so slopes roughly
# halve. Judgement, not data.
SLOPE_DAMP = 0.5
# Widest the tracked-player forecast may grow past its last read, in one case.
MAX_N_GROWTH = 4.0
# The tracked-player count never falls, and earners never fall either.
# --- Spread (logit units) ---
SIGMA_FLOOR = 0.35        # every trophy carries at least this much doubt
SIGMA_FEW_EARNERS = 0.65  # a trophy with at most 2 earners is nearly unmeasured
SIGMA_AT_100 = 0.5        # the trophy every tracked player holds: downside only
SIGMA_CAP = 1.2           # never wider than the house baseline's spread (1.06)
SIGMA_FLAT_HISTORY = 0.9  # no movement observed: we know almost nothing
# --- Refresh prior (flat history only; see METHODOLOGY.md) ---
# Exophase refreshes a game's counts every few hours (first observed refresh
# ~4.5 h after the first probe on launch night). Mean interval, hours.
REFRESH_INTERVAL_H = 4.5
# If a refresh happens, the tracked population multiplies by about this much
# (first observed refresh: 638 -> 3,868 players, 6.06x; later ones are smaller
# as the base grows; 3.0 is the prior). Judgement, not data.
REFRESH_N_MULT = 3.0
# Flat history + long horizon: how much faster a trophy's earners grow
# than the tracked population, in log terms, by progress class (judgement
# priors calibrated on the real Exophase snapshot of 2026-11-20 19:25Z, when
# Chapter 1 sat at 11.98% and Chapter 2 at 1.71% while late chapters were
# still ~0.02%; only used when the case gives no movement to fit).
LAUNCH_CLASS_MULT = {
    "ch1": 3.0,        # the opening chapter: the launch cohort races through
    "ch2": 1.4,        # the second chapter: far slower than the first
    "late-story": 0.0,  # later chapters and the final mission: earners flat
    "grind": 0.3,      # gold/silver grinds and collections: barely moving
    "mid": 1.5,        # ordinary bronze activities
    "end": 0.0,        # 100% completion and the Platinum: almost nobody, yet
}


def parse_time(text):
    """ISO 8601 UTC timestamp -> aware datetime."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def clamp(x, lo=0.01, hi=99.99):
    return min(hi, max(lo, x))


def logit(pct):
    return math.log(clamp(pct) / (100.0 - clamp(pct)))


def inv_logit(l):
    return 100.0 / (1.0 + math.exp(-l))


def round4(x):
    """x rounded to 4 decimals, half up, as JavaScript's Math.round does it."""
    scaled = x * 10000
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 10000
    return int(value) if value == int(value) else value


def ols(xs, ys):
    """Least squares line y = a + b*x. Returns (a, b, resid_sd, n, xbar, sxx)."""
    n = len(xs)
    xbar = sum(xs) / n
    ybar = sum(ys) / n
    sxx = sum((x - xbar) ** 2 for x in xs)
    if sxx <= 0:
        return ybar, 0.0, 0.0, n, xbar, 0.0
    b = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / sxx
    a = ybar - b * xbar
    if n > 2:
        sse = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
        sd = math.sqrt(sse / (n - 2))
    else:
        sd = 0.0
    return a, b, sd, n, xbar, sxx


def isotonic_decreasing(values):
    """Pool-adjacent-violators: smallest non-increasing sequence >= in mean.

    Returns a non-increasing list with the same length, each entry the mean of
    its pooled block. Used for the story chain, where a later chapter cannot
    be earned by more players than an earlier one.
    """
    out = []
    for v in values:
        out.append([v, 1])
        while len(out) >= 2 and out[-2][0] / out[-2][1] < out[-1][0] / out[-1][1]:
            t2, c2 = out.pop()
            t1, c1 = out.pop()
            out.append([t1 + t2, c1 + c2])
    result = []
    for total, count in out:
        result.extend([total / count] * count)
    return result


CHAPTER_RE = re.compile(r"complete chapter (\d+)", re.IGNORECASE)
FINAL_MISSION_RE = re.compile(r"^complete the final mission\.?$", re.IGNORECASE)
HUNDRED_RE = re.compile(r"attain 100% completion", re.IGNORECASE)


def progress_class(trophy):
    """Which launch-growth class a trophy belongs to, from its description.

    Only used by the flat-history fallback, when the case gives no movement
    to fit. "ch1" is the opening chapter (the launch cohort races through
    it); "ch2" the second; "late-story" the later chapters and the final
    mission; "grind" the gold/silver grinds and collections; "end" 100%
    completion and the Platinum.
    """
    desc = (trophy.get("description") or "").lower()
    if trophy.get("tier") == "platinum" or "100% completion" in desc:
        return "end"
    m = CHAPTER_RE.search(desc)
    if m:
        chapter = int(m.group(1))
        if chapter == 1:
            return "ch1"
        if chapter == 2:
            return "ch2"
        return "late-story"
    if "complete the final mission" in desc:
        return "late-story"
    if trophy.get("tier") in ("gold", "silver"):
        return "grind"
    return "mid"


def forecast_case(case, name):
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    history = case["history"]
    if not history:
        raise ValueError(f"{name} has no history")
    trophies = case["trophies"]
    n_trophies = len(trophies)

    at = parse_time(case["at"])
    target = parse_time(case["target"])
    horizon_h = case["horizon_minutes"] / 60.0

    def x_of(moment):
        hours = (moment - RELEASE_DAY).total_seconds() / 3600.0
        return math.log1p(max(hours, 0.0))

    x_target = x_of(target)

    # --- 1. Collapse the history to distinct reads. ---
    # Exophase refreshes its counts hours apart; most reads repeat the one
    # before. A distinct observation keeps the LAST slot of its run: the
    # values were certainly true by then.
    distinct = []  # each: {x, at, n, rates (list, None where missing)}
    for read in history:
        rates = list(read["rates"])
        key = (read["players_tracked"], tuple(rates))
        if distinct and distinct[-1]["key"] == key:
            distinct[-1]["x"] = x_of(parse_time(read["slot"]))
            distinct[-1]["at"] = read["slot"]
        else:
            distinct.append({
                "key": key,
                "x": x_of(parse_time(read["slot"])),
                "at": read["slot"],
                "n": read["players_tracked"],
                "rates": rates,
            })
    for obs in distinct:
        obs.pop("key", None)

    # Earner counts per trophy per observation (None where the read lacked it),
    # forced non-decreasing per trophy: earners cannot fall, so a drop is a
    # rounding artefact of the page's 2 decimals.
    earners = []  # earners[i][j]: trophy i at observation j (or None)
    for i in range(n_trophies):
        series = []
        running = 0.0
        for obs in distinct:
            r = obs["rates"][i]
            if r is None:
                series.append(None)
            else:
                e = r / 100.0 * obs["n"]
                running = max(running, e)
                series.append(running)
        earners.append(series)

    # Drop a stale observation: if earners apparently fell for most trophies
    # between two distinct reads, the earlier read carried seeded rates.
    # (Launch night's page is the observed case.) Repeat until stable.
    keep = list(range(len(distinct)))
    changed = True
    while changed and len(keep) > 1:
        changed = False
        for k in range(1, len(keep)):
            prev, cur = keep[k - 1], keep[k]
            falls = 0
            seen = 0
            for i in range(n_trophies):
                a = earners[i][prev]
                b = earners[i][cur]
                if a is None or b is None:
                    continue
                seen += 1
                if b < a - 1e-9:
                    falls += 1
            if seen and falls * 2 > seen:
                keep.pop(k - 1)
                changed = True
                break
    distinct = [distinct[j] for j in keep]
    earners = [[series[j] for j in keep] for series in earners]
    n_obs = len(distinct)

    last = distinct[-1]
    x_last = last["x"]
    gap = max(x_target - x_last, 0.0)
    damp = 1.0 / (1.0 + SLOPE_DAMP * gap)

    # Last non-null rate per trophy (for the flat fallback and the 100% rule).
    last_rate = []
    for i in range(n_trophies):
        rate = None
        for obs in reversed(distinct):
            if obs["rates"][i] is not None:
                rate = obs["rates"][i]
                break
        last_rate.append(rate if rate is not None else 0.0)

    # --- 2. Fit log counts on log-time. ---
    # The last 24 hours of distinct reads when there are at least 3, else all
    # of them: the window the house curve baseline uses, which also keeps
    # launch night's seeded page out of the final case's fit.
    window = [j for j, obs in enumerate(distinct)
              if (at - parse_time(obs["at"])).total_seconds() <= 24 * 3600]
    fit_idx = window if len(window) >= 3 else list(range(n_obs))

    def fit_counts(series):
        """OLS of log count on x over the fit window. Returns fit tuple or None."""
        xs, ys = [], []
        for j in fit_idx:
            v = series[j]
            if v is None:
                continue
            xs.append(distinct[j]["x"])
            ys.append(math.log(max(v, 0.5)))
        if len(xs) < 2 or max(xs) == min(xs):
            return None
        a, b, sd, n, xbar, sxx = ols(xs, ys)
        return (a, max(b, 0.0), sd, n, xbar, sxx)

    n_series = [float(obs["n"]) for obs in distinct]
    n_fit = fit_counts(n_series)

    flat = n_obs < 3
    medians = []
    sigmas = []
    for i, trophy in enumerate(trophies):
        if flat:
            median, sigma = _flat_fallback(
                trophy, last_rate[i], earners[i][-1], last["n"],
                horizon_h, gap)
        else:
            median, sigma = _trend_forecast(
                trophy, earners[i], n_fit, distinct, fit_idx,
                x_target, x_last, gap, damp, last_rate[i])
        medians.append(median)
        sigmas.append(sigma)

    # --- 3. Funnel constraints on the medians. ---
    medians = _apply_funnel(trophies, medians)

    # --- 4. Quantiles: logit-normal around the median. ---
    rows = []
    for trophy, median, sigma in zip(trophies, medians, sigmas):
        base = logit(median)
        qs = []
        for z in Z:
            q = inv_logit(base + z * sigma)
            qs.append(round4(min(100.0, max(0.0, q))))
        # Rounding can only break monotonicity at the clamps; repair it.
        for k in range(1, len(qs)):
            qs[k] = max(qs[k], qs[k - 1])
        rows.append({"id": trophy["id"], "q": qs})
    return {"trophies": rows}


def _trend_forecast(trophy, e_series, n_fit, distinct, fit_idx,
                   x_target, x_last, gap, damp, last_rate):
    """Median and spread from the counts fits."""
    xs, ys = [], []
    for j in fit_idx:
        v = e_series[j]
        if v is None:
            continue
        xs.append(distinct[j]["x"])
        ys.append(math.log(max(v, 0.5)))
    e_fit = None
    if len(xs) >= 2 and max(xs) != min(xs):
        a, b, sd, n, xbar, sxx = ols(xs, ys)
        e_fit = (a, max(b, 0.0), sd, n, xbar, sxx)

    last_e = None
    for v in reversed(e_series):
        if v is not None:
            last_e = v
            break
    if last_e is None:
        last_e = 0.0
    last_n = distinct[-1]["n"]

    # Tracked players at the target: anchor on the last read and grow at the
    # damped fitted slope over the gap only. (Damping the slope from the
    # origin would bend the line below the last read.)
    if n_fit is not None:
        a_n, b_n, sd_n, n_n, xb_n, sxx_n = n_fit
        n_target = float(last_n) * math.exp(b_n * damp * gap)
    else:
        n_target = float(last_n)
        sd_n, n_n, xb_n, sxx_n = 0.0, 1, x_last, 0.0
    n_target = min(max(n_target, float(last_n)), float(last_n) * MAX_N_GROWTH)

    # Earners at the target, anchored the same way.
    if e_fit is not None:
        a_e, b_e, sd_e, n_e, xb_e, sxx_e = e_fit
        e_target = last_e * math.exp(b_e * damp * gap)
        # Prediction-interval spread for log earners at the target.
        lev_e = 1.0 + 1.0 / n_e + ((x_target - xb_e) ** 2 / sxx_e if sxx_e > 0 else 0.0)
        pi_e = sd_e * math.sqrt(max(lev_e, 1.0))
    else:
        e_target = last_e
        pi_e, n_e = 0.0, 1
    e_target = min(max(e_target, last_e), n_target)

    if last_rate >= 99.99:
        # Everyone tracked holds it; earners track the population exactly.
        median = 99.99
    else:
        median = clamp(100.0 * e_target / n_target)

    # Spread: prediction intervals of both counts, combined on the log-rate
    # scale and converted to logit (d logit / d ln r = 1 / (1 - r)); small
    # samples are widened, and every trophy keeps a floor.
    lev_n = 1.0 + 1.0 / n_n + ((x_target - xb_n) ** 2 / sxx_n if sxx_n > 0 else 0.0)
    pi_n = sd_n * math.sqrt(max(lev_n, 1.0))
    small = math.sqrt(1.0 + 2.0 / max(min(n_e, n_n), 1))
    sigma = math.sqrt(pi_e ** 2 + pi_n ** 2) * small / max(1.0 - median / 100.0, 0.05)
    floor = SIGMA_FEW_EARNERS if last_e <= 2.0 else SIGMA_FLOOR
    if last_rate >= 99.99:
        floor = max(floor, SIGMA_AT_100)
    sigma = min(max(sigma, floor), SIGMA_CAP)
    return median, sigma


def _flat_fallback(trophy, rate, last_e, last_n, horizon_h, gap):
    """No movement in the history: use the refresh / launch priors.

    Short horizon: a refresh is likely before the target, new tracked
    players hold fewer trophies, earners barely move -- rates shade down.
    Long horizon: the launch cohort progresses, so early trophies' earners
    grow faster than the tracked population; late ones grow slower.
    """
    p_refresh = 1.0 - math.exp(-horizon_h / REFRESH_INTERVAL_H)
    n_mult = 1.0 + p_refresh * (REFRESH_N_MULT - 1.0)
    if horizon_h <= 6.0:
        e_mult = 1.0 + 0.1 * p_refresh
    else:
        cls = progress_class(trophy)
        # Earners grow (class multiple) x as fast as the population, in logs.
        e_mult = math.exp(LAUNCH_CLASS_MULT[cls] * math.log(n_mult))
    if rate >= 99.99:
        return 99.99, SIGMA_AT_100
    last_e = last_e if last_e is not None else 0.0
    e_target = max(last_e * e_mult, last_e)
    n_target = last_n * n_mult
    median = clamp(100.0 * e_target / n_target)
    return median, SIGMA_FLAT_HISTORY


def _apply_funnel(trophies, medians):
    """Enforce what the game allows on the medians."""
    out = list(medians)
    # Story chain: chapters in order, then the final mission, 100%, Platinum.
    chain = []  # (position in trophies, key) in story order
    for pos, trophy in enumerate(trophies):
        desc = (trophy.get("description") or "").lower().strip()
        m = CHAPTER_RE.search(desc)
        if m:
            chain.append((pos, (0, int(m.group(1)))))
        elif FINAL_MISSION_RE.match(desc):
            # Only the exact final mission: "Complete the final mission for
            # Randy" is a stranger finale, not the story's end.
            chain.append((pos, (1, 0)))
        elif HUNDRED_RE.search(desc):
            chain.append((pos, (2, 0)))
        elif trophy.get("tier") == "platinum":
            chain.append((pos, (3, 0)))
    chain.sort(key=lambda item: item[1])
    if len(chain) >= 2:
        fixed = isotonic_decreasing([out[pos] for pos, _ in chain])
        for (pos, _), value in zip(chain, fixed):
            out[pos] = value
    # The Platinum needs every other trophy, so it cannot exceed the lowest.
    plat = [pos for pos, t in enumerate(trophies) if t.get("tier") == "platinum"]
    if plat:
        lowest = min(v for pos, v in enumerate(out) if pos not in plat)
        out[plat[0]] = min(out[plat[0]], lowest)
    return out


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
