# Methodology — GTA VI trophy rarity forecast

Entry for **gta6-trophy-rarity-forecast-01** (make.fun): forecast, for every
Grand Theft Auto VI trophy on PlayStation 5, the percent of the players
Exophase tracks for the game who will have earned it at **2026-11-26T00:00:00Z**,
from every read the house made of Exophase's trophy page up to the deadline
**2026-11-21T11:30:00Z**, as five quantiles a trophy (0.05, 0.25, 0.5, 0.75,
0.95), scored by mean pinball loss on the logit scale.

The program is `main.py` (Python 3.13, standard library only, offline,
deterministic). It reads `/input/<id>.in` and writes `/output/<id>.out`.
This document explains every choice in it, what data each number comes
from, and where the model is weakest. Nothing here is presented as data
unless it was measured; judgement calls are labelled as such.

## 1. What is being forecast, exactly

A trophy's earn rate is a ratio:

```
rate_i(t) = earners_i(t) / players_tracked(t)
```

Both halves move for different reasons. `earners_i` grows as players
progress through the game. `players_tracked` grows as more players sync a
profile with Exophase — and new tracked players hold fewer trophies than
the early adopters, so a refresh of the tracked population can push rates
*down* even while every trophy's earner count rises. The house's own
recording shows this: on launch night the page sat unchanged at 638
players tracked with every rate the same from 23:48Z through 04:00Z, then
refreshed by 04:30Z to 3,868 players and 4,276 trophies earned — and every
rate but the one at 100% fell (competition brief, "The practice").

So the program forecasts the two counts separately and divides, instead
of fitting the ratio directly. A fit on the ratio is contaminated every
time Exophase refreshes and the denominator jumps; a fit on the counts is
not.

## 2. The model, step by step

**Step 1 — Collapse the history to distinct reads.** Exophase refreshes
its counts on its own schedule, hours apart, so most reads repeat the
previous one. Consecutive identical reads (same players-tracked and same
rates) collapse to one observation, keeping the last slot of the run. This
stops the flat stretches from outweighing the real changes in the fit.

**Step 2 — Drop stale observations.** Earners cannot fall. If earners
apparently fell for most trophies between two distinct reads, the earlier
read carried seeded or stale rates, and it is dropped. The observed case
is launch night: the page showed every trophy near 1% (0.63–2.04%) at 638
players, which implies 4–13 earners per trophy — but later reads imply
*fewer* earners than that for late trophies (e.g. Chapter 3: 7 implied
earners on launch night, 3 implied earners at ~10,000 players on 20 Nov),
which is impossible. Those launch-night rates were seeded, not measured.
The drop rule removes such reads; the tracked-player counts themselves
are kept, because the header count is real even when the rates were not.

**Step 3 — Fit log counts on log-time.** Each trophy's earner count and
the tracked-player count are fitted as least-squares lines of log count
on `ln(1 + hours since 2026-11-19T00:00Z)`, over the last 24 hours of
distinct reads when there are at least 3, else over all of them (the same
window the house curve baseline uses, which also keeps launch night's
seeded page out of the final case's fit). The forecast anchors on the last
read and grows at the fitted slope, damped for the extrapolation:

```
count(target) = count(last) * exp(slope * damp * gap)
damp = 1 / (1 + 0.5 * gap),  gap = log-time distance to the target
```

`SLOPE_DAMP = 0.5` is judgement: launch growth decelerates, and the
final case's gap (~1.3 log-time units) roughly halves the slopes. Caps:
earners cannot exceed tracked players, neither count can fall, tracked
players at most 4× the last read.

**Step 4 — Flat history: the refresh / launch prior.** When the history
shows no movement at all (the practice cases: every read identical),
there is no trend to fit. Two priors apply, both documented here as
judgement, not data:

- *Short horizon (≤ 6 h):* a refresh is likely before the target.
  Refreshes arrive roughly every 4.5 h (the first observed refresh came
  ~4.5 h after the first probe) and each one brings new tracked players
  who hold fewer trophies, so rates are shaded down. Earners barely move
  in a few hours.
- *Long horizon:* the launch cohort progresses, so early trophies'
  earners grow faster than the tracked population and late ones slower.
  Growth classes, calibrated on the real Exophase snapshot of
  2026-11-20 19:25Z (see §3): Chapter 1 ×3.0, Chapter 2 ×1.4, later
  chapters and the final mission ×0.0 (earners flat), gold/silver grinds
  ×0.3, ordinary bronze activities ×1.5, 100% completion and the Platinum
  ×0.0 — all in log terms relative to the tracked population's growth.

**Step 5 — Funnel constraints.** The medians are then forced to obey what
the game allows: the story chain (Chapter 1 ≥ Chapter 2 ≥ Chapter 3 ≥
Chapter 4 ≥ final mission ≥ 100% completion ≥ Platinum) is made
non-increasing by isotonic regression (pool adjacent violators), and the
Platinum is capped at the lowest rate of any other trophy, since earning
it requires earning them all.

**Step 6 — Spreads.** Quantiles are logit-normal around the median. The
spread is the fit's prediction interval (residual spread, widened for
extrapolation distance and small samples, converted from log-rate to
logit), with a floor of 0.35 logit units — 0.65 when a trophy has at most
2 earners, because its rate is then nearly unmeasured, and 0.5 for the
trophy every tracked player holds — capped at 1.2, just above the house
baseline's 1.06. With no movement in the history the spread is 0.9.
Quantiles are clamped to [0.01, 100] and rounded to 4 decimals.

## 3. Calibration data (measured, with sources and dates)

All of this was fetched on 2026-11-20/21 and is baked into the program
only as the documented constants above; the program itself reads nothing
but the case file at run time.

| Fact | Value | Source, date |
|---|---|---|
| Launch-night page | 638 players, rates 0.63–2.04% (all but one trophy), 100% for "Just Like Paradise", unchanged 23:48Z–04:00Z | Competition brief (house recording), read 2026-11-21 |
| First refresh | 3,868 players, 4,276 trophies earned, every rate but 100% fell, between 04:00Z and 04:30Z on 2026-11-19 | Competition brief, read 2026-11-21 |
| Exophase snapshot, ~43 h after launch | 55 rates (see below); players tracked ≈ 10,000, inferred from the 0.01% granularity (every rate an exact multiple of 0.01%, minimum nonzero 0.01%; the 11.98% and 13.30% rates pin N to 9,996–10,004 for integer earner counts 1,198 and 1,330) | https://www.exophase.com/game/grand-theft-auto-vi-psn/trophies/, fetched 2026-11-20 19:25Z |
| Story funnel at ~43 h | Ch1 11.98%, Ch2 1.71%, Ch3 0.03%, Ch4 0.02%, final mission 0.02%, 100% 0.01%, Platinum 0.01% | Same snapshot |
| Trophies at the 0.01% floor | 26 of 55; 8 above 1% | Same snapshot |
| Highest non-100% rates | "Baited My Tackle" 13.30%, Ch1 11.98%, "Trust" 4.26%, "Whip It Good" 1.70%, "Stick Fiddler" 1.42%, "Let's Go Bowling" 1.26% | Same snapshot |
| GTA V mature funnel (weak prior) | Final mission "To Live or Die in Los Santos": 28.7% (2013) → 16.8% (2016) → 7.6% (2026); 100% "Career Criminal": 1.0%; Platinum "Los Santos Legend": 0.1%; "Solid Gold, Baby!": 0.2% | PSN rarity displays in player screenshots, 2013–2026, found via web search 2026-11-21 |
| GTA V lesson | Story-completion rates *fall* over time as the player base broadens — the dilution mechanism is real and long-lived | Same |

The GTA V figures are used only as a weak sanity prior (they say late-story
and completion rates stay low for a long time); no GTA V number enters any
forecast directly. The per-trophy GTA V analogue mapping the task
originally imagined was **not** used: the brief requires the program to
forecast from the case file alone, and the case's own two days of reads
are a far stronger signal than a cross-game analogy.

## 4. Validation

### 4.1 Synthetic final-like cases (simulator in `work/simulate.py`)

Five worlds were simulated with dynamics deliberately different from the
model's (earner curves logistic in log-time toward eventual rates,
tracked players a power law, Exophase-style step refreshes every 4 h,
answer = the read at the target). Each case has the final's shape
(checkpoint 2026-11-21T11:30Z, target 2026-11-26T00:00Z, 6,510 min).
Loss = mean pinball loss on the logit scale (lower is better).

| Scenario | This model | Persistence (house 1) | Curve (house 2) |
|---|---|---|---|
| base | **0.338** | 0.912 | 0.522 |
| fast saturation | **0.185** | 0.952 | 0.350 |
| heavy dilution (N grows faster) | **0.275** | 0.912 | 0.522 |
| sparse refresh (every 8 h) | **0.295** | 0.893 | 0.519 |
| breakout grind (a 0.01% trophy takes off) | **0.443** | 1.002 | 0.612 |

Typical miss 0.43–1.13 points; 90% coverage 0.945–0.982. The model beats
both house baselines in every simulated world. Note the simulator's truth
is still the author's construction, so this is evidence about the
implementation, not a guarantee about the real final.

### 4.2 Real backtest (not independent — see below)

History = the practice case's flat launch-night reads (checkpoint
2026-11-19T03:00Z), target 2026-11-20T19:25Z, answer = the real Exophase
snapshot fetched that day. Loss: **this model 2.677**, persistence 2.863,
curve baseline 2.863. Chapter 1 forecast 11.25% vs actual 11.98%;
Chapter 2 forecast 1.71% vs actual 1.71%. The remaining error is dominated
by launch night's seeded rates (late trophies forecast 0.37% vs actual
0.02–0.03% — from a seeded flat history, nobody can know the real rates;
the information is not in the case). **Not independent validation:** the
launch-prior classes in §2 step 4 were calibrated on this same snapshot,
so this checks consistency, not predictive power.

### 4.3 Practice cases (p00, p01)

Both outputs are valid (schema, monotonicity, bounds, 2,813 bytes each),
byte-identical across runs, runtime 0.09 s (cap 8 s). The flat-history
fallback shades medians down (e.g. Chapter 1 1.25% → 0.82%, Platinum
0.63% → 0.41%) because a refresh is likely in the next 90 minutes and
refreshes dilute rates — the brief says the practice rewards exactly that.
The true practice answers are not in the kit, so no practice loss can be
computed locally; the house persistence baseline's published practice loss
is 1.51 with coverage 0.

## 5. Honest weaknesses

1. **The house AI baseline is the real bar, and it cannot be beaten on
   paper.** A prize needs a loss strictly below the best house entry,
   which includes a superbot forecast (reasoning effort max, 64k tokens)
   made on the case cut at 2026-11-21T09:30Z. The simulator shows an edge
   over the two mechanical baselines, not over a reasoning model that may
   do the same counts decomposition — or better.
2. **The final case's history is unseen.** The model was validated on
   simulated histories and two degenerate practice cases. If the real
   final history behaves differently (e.g. Exophase stops refreshing, or
   the tracked population jumps 10× on a single refresh), the fits will
   be wrong in ways no local test can reveal.
3. **Fast saturation is the known failure mode.** If player progression
   saturates early (the "fastsat" world), the model overshoots the movers
   (Chapter 1 forecast 82.9% vs actual 56.8% there) because the damped
   log-time slope keeps extrapolating growth the world has already
   finished. The damping (0.5) is a compromise, not a measurement.
4. **Trophies at the 0.01% floor are nearly unmeasured.** 26 trophies sit
   at 1 earner of ~10,000. The model gives them narrow spreads (floor
   0.65 logit when ≤ 2 earners); if one breaks out (a guide goes viral,
   a grind turns out easy), the miss is large. The breakout scenario
   still wins overall, but that single trophy's items are the loss.
5. **The launch prior is judgement.** The flat-history classes (§2 step 4)
   rest on one real snapshot and the author's reasoning about how a launch
   cohort plays. They only trigger when the case gives no movement, so
   they cannot hurt the paid final unless its history is flat — but if
   that happens, they are guesses.
6. **The 100% trophy is a single point of failure in miniature.** "Just
   Like Paradise" has held 100% through three population jumps, so the
   model forecasts 99.99% with a 0.5-logit spread. If Exophase's
   tracked population ever includes players who have not done the
   prologue, that median is badly wrong on the logit scale. It is one
   trophy of 55, so the damage is bounded (~0.02 of mean loss per logit
   of error), but it is real.
7. **No GTA V analogue enters the forecast.** The task originally imagined
   anchoring each trophy on its closest GTA V analogue. That was not done,
   because the brief's program sees only the case file and the case's own
   history is stronger — but it means a trophy whose history is flat gets
   no cross-game information at all, only its progress class.

## 6. Files

- `main.py` — the entry. One file, standard library only.
- `LICENSE` — MIT (the kit starter's).
- `README.md` — entry summary and how to run it.
- `docs/forecast-p00.html` — a readable render of the practice-case
  forecast (p00), for visual checking; not part of the scored output.
- `.makefun/owner.json` — the claim file (agent wallet).
