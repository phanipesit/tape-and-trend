"""Walk-forward validation: choose parameters on past data, judge them on future data.

Every optimisation in this project has produced a number that looked good and did not
survive. The stop/target sweep's best cell scored +0.189 R combined and +0.040 in 2026 --
its out-of-sample half. `rsi_overbought` measured +0.566 R on 33 signals and -0.223 on
626. `breakout_20d x RISK_OFF` cleared zero at n=25 and has been decaying since. Each was
caught by hand, afterwards.

Walk-forward makes that automatic. History is cut into consecutive folds; parameters are
chosen on each fold's training window and scored only on the test window that follows it,
which the choice could not have seen. Repeat, and the aggregate of those test scores is
an honest estimate of what the *procedure of optimising* actually earns -- as opposed to
what the best cell of a grid claims in hindsight.

Three numbers come out, and the gaps between them are the point:

  in_sample     what the chosen parameters scored on the data that chose them. Always
                the most flattering, and the one people quote.
  out_of_sample what those same parameters then earned on unseen data. The honest one.
  baseline      fixed parameters, never optimised. If optimising cannot beat this, the
                optimisation is noise with extra steps.

`stability` counts how often the winning parameters change between folds. A genuine edge
keeps picking roughly the same settings; noise picks a different winner every time, and
that instability is itself evidence -- visible before any out-of-sample number arrives.

Pure: no DB, no network, no clock. Callers supply signals and a scoring function.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from statistics import mean, pstdev


def folds(start: date, end: date, train_days: int, test_days: int,
          step_days: int | None = None) -> list[dict]:
    """Consecutive train/test windows across [start, end].

    Test windows follow their training window and never overlap it, which is the whole
    guarantee. `step_days` defaults to the test length, so successive test windows tile
    the period without overlapping each other either -- overlapping tests would reuse the
    same outcomes and quietly inflate the sample.
    """
    if train_days <= 0 or test_days <= 0:
        raise ValueError("train_days and test_days must be positive")
    step = step_days or test_days
    out, cursor = [], start
    while cursor + timedelta(days=train_days + test_days) <= end:
        tr_end = cursor + timedelta(days=train_days)
        out.append({"train_start": cursor, "train_end": tr_end,
                    "test_start": tr_end, "test_end": tr_end + timedelta(days=test_days)})
        cursor += timedelta(days=step)
    return out


def _stats(vals: list[float]) -> dict:
    if not vals:
        return {"n": 0, "mean": None, "ci_low": None, "ci_high": None}
    m, n = mean(vals), len(vals)
    half = 1.96 * pstdev(vals) / (n ** 0.5) if n > 1 else None
    return {"n": n, "mean": round(m, 4),
            "ci_low": None if half is None else round(m - half, 4),
            "ci_high": None if half is None else round(m + half, 4)}


def run(signals: list[dict], grid: list, score, *, train_days: int, test_days: int,
        baseline=None, step_days: int | None = None, min_train: int = 30,
        min_test: int = 10) -> dict:
    """Walk `grid` forward over `signals`.

    signals  dicts carrying at least a `date`.
    grid     candidate parameter sets, opaque to this module.
    score    score(signal, params) -> float R multiple, or None if unscorable.
    baseline a fixed parameter set, evaluated on the same test windows for comparison.

    Folds too thin to support a choice are skipped rather than allowed to vote on
    whatever handful of signals they happen to contain.
    """
    if not signals or not grid:
        return {"folds": [], "error": "no signals or empty grid"}

    dates = sorted(s["date"] for s in signals)
    windows = folds(dates[0], dates[-1], train_days, test_days, step_days)

    def scored(subset, params):
        return [r for r in (score(s, params) for s in subset) if r is not None]

    results, chosen, skipped = [], [], 0
    for w in windows:
        tr = [s for s in signals if w["train_start"] <= s["date"] < w["train_end"]]
        te = [s for s in signals if w["test_start"] <= s["date"] < w["test_end"]]
        if len(tr) < min_train or len(te) < min_test:
            skipped += 1
            continue

        ranked = []
        for p in grid:
            v = scored(tr, p)
            if v:
                ranked.append((mean(v), p))
        if not ranked:
            skipped += 1
            continue
        best_train, best = max(ranked, key=lambda x: x[0])

        oos = scored(te, best)
        row = {"train_start": str(w["train_start"]), "test_start": str(w["test_start"]),
               "test_end": str(w["test_end"]), "n_train": len(tr), "n_test": len(oos),
               "chosen": best, "in_sample": round(best_train, 4),
               "out_of_sample": round(mean(oos), 4) if oos else None}
        if baseline is not None:
            base = scored(te, baseline)
            row["baseline"] = round(mean(base), 4) if base else None
        results.append(row)
        chosen.append(repr(best))

    ins = [r["in_sample"] for r in results if r["in_sample"] is not None]
    oos = [r["out_of_sample"] for r in results if r["out_of_sample"] is not None]
    base = [r["baseline"] for r in results if r.get("baseline") is not None]
    counts = Counter(chosen)

    return {
        "folds": results, "n_folds": len(results), "skipped_folds": skipped,
        "in_sample": _stats(ins), "out_of_sample": _stats(oos), "baseline": _stats(base),
        # The number that matters: how much of the in-sample result evaporated.
        "decay": (round(mean(ins) - mean(oos), 4) if ins and oos else None),
        "beats_baseline": (round(mean(oos) - mean(base), 4) if oos and base else None),
        "stability": {
            "distinct_choices": len(counts),
            "most_common": counts.most_common(1)[0] if counts else None,
            # 1.0 = the same parameters won every fold; near 0 = a different winner each
            # time, which is what noise looks like.
            "consistency": round(counts.most_common(1)[0][1] / len(chosen), 3) if chosen else None,
        },
    }
