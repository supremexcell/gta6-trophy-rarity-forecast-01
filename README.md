# gta6-trophy-rarity-forecast-01

[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/supremexcell/gta6-trophy-rarity-forecast-01/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/supremexcell/gta6-trophy-rarity-forecast-01/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

A forecaster for **Grand Theft Auto VI** (PlayStation 5) trophy earn rates:
given every read the house made of [Exophase's GTA VI trophy page](https://www.exophase.com/game/grand-theft-auto-vi-psn/trophies/)
up to the case's checkpoint, it forecasts each of the **55 trophies'** earn
rate (the percent of tracked players who hold it) at the case's target as
five quantiles (5%, 25%, 50%, 75%, 95%), scored by mean pinball loss on the
logit scale. The final case forecasts **2026-11-26T00:00:00Z**, a week after
launch, from the reads up to the deadline **2026-11-21T11:30:00Z**.

## The idea in one paragraph

A trophy's earn rate is a ratio — earners over players tracked — and the
two halves move for different reasons: players progress through the game
while new players join the tracked population holding fewer trophies, so
a refresh of Exophase's counts can push rates *down* even as every
trophy's earner count rises. The program therefore forecasts the two
counts separately and divides, instead of fitting the ratio directly. It
collapses the history to distinct reads (Exophase refreshes hours apart),
drops seeded/stale reads (launch night's page showed every trophy near
1%, which later reads prove impossible), fits log counts on log-time over
the last 24 hours of reads with a damped slope, and constrains the
medians to the story funnel (Chapter 1 ≥ Chapter 2 ≥ … ≥ final mission ≥
100% ≥ Platinum). Spreads are honest prediction intervals. Full write-up,
calibration data with sources and dates, validation, and weaknesses:
**[METHODOLOGY.md](METHODOLOGY.md)**.

## Run it (offline, no build step)

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

`main.py` (Python 3.13, standard library only) reads every `<id>.in` in
the input directory and writes `<id>.out` — `{"trophies": [{"id": 1, "q":
[q05, q25, q50, q75, q95]}, ...]}` — to the output directory.
Deterministic: two runs on the same case write the same bytes. Runtime
~0.1 s per case (cap 8 s).

## Validation (local; the server grades the real final)

- Five simulated final-like worlds (dynamics deliberately different from
  the model's): this model beats both house baselines in all five —
  loss 0.19–0.44 vs persistence 0.89–1.00 and the curve baseline
  0.35–0.61. Typical miss 0.43–1.13 points, 90% coverage 0.945–0.982.
- Real backtest (flat launch-night history → the real Exophase snapshot
  of 2026-11-20 19:25Z): loss 2.68 vs persistence 2.86. Chapter 1
  forecast 11.25% vs actual 11.98%; Chapter 2 forecast 1.71% vs actual
  1.71%. (Not independent: the launch prior was calibrated on that
  snapshot — see METHODOLOGY.md §4.2.)
- Practice cases p00/p01: valid output, byte-identical across runs.

## What it does not do

No network at run time, no model calls, no GTA V analogue table — the
program forecasts from the case file alone, as the brief requires. The
one outside input is the documented constants in `main.py` (refresh
interval, damping, launch-prior classes), each sourced in METHODOLOGY.md.
