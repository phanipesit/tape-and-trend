"""Walk-forward validation. Pure — no DB, no network, no clock."""
from datetime import date, timedelta

import pytest

from app.services import walkforward as wf


D0 = date(2025, 1, 1)


def sig(day, r_by_param):
    """A signal whose outcome depends on the parameter chosen."""
    return {"date": D0 + timedelta(days=day), "r": r_by_param}


def score(s, p):
    return s["r"].get(p)


# ---------------------------------------------------------------- folds

def test_test_window_never_overlaps_its_training_window():
    """The entire guarantee: the choice cannot have seen the data that judges it."""
    for f in wf.folds(D0, D0 + timedelta(days=400), 100, 50):
        assert f["train_end"] == f["test_start"]
        assert f["train_start"] < f["train_end"] < f["test_end"]


def test_test_windows_do_not_overlap_each_other():
    # Overlapping tests reuse outcomes and inflate the apparent sample.
    fs = wf.folds(D0, D0 + timedelta(days=500), 100, 50)
    for a, b in zip(fs, fs[1:]):
        assert a["test_end"] <= b["test_start"]


def test_a_period_too_short_for_one_fold_yields_none():
    assert wf.folds(D0, D0 + timedelta(days=20), 100, 50) == []


def test_step_can_be_set_independently():
    assert len(wf.folds(D0, D0 + timedelta(days=400), 100, 50, step_days=25)) > \
           len(wf.folds(D0, D0 + timedelta(days=400), 100, 50))


@pytest.mark.parametrize("tr,te", [(0, 50), (100, 0), (-1, 50)])
def test_nonsense_window_sizes_are_rejected(tr, te):
    with pytest.raises(ValueError):
        wf.folds(D0, D0 + timedelta(days=400), tr, te)


# ---------------------------------------------------------------- the core question

def test_a_genuine_edge_survives_out_of_sample():
    """Parameter A is truly better everywhere, so picking it in training pays in testing."""
    signals = [sig(d, {"A": 1.0, "B": -1.0}) for d in range(400)]
    r = wf.run(signals, ["A", "B"], score, train_days=100, test_days=50, baseline="B")
    assert r["out_of_sample"]["mean"] == pytest.approx(1.0)
    assert r["stability"]["consistency"] == 1.0        # same winner every fold
    assert r["beats_baseline"] > 0


def test_noise_shows_a_large_decay_and_unstable_choices():
    """The failure mode this exists to catch: a parameter that wins in training purely by
    chance and gives it all back afterwards."""
    import random
    rng = random.Random(7)
    signals = [sig(d, {p: rng.gauss(0, 1) for p in "ABCDE"}) for d in range(600)]
    r = wf.run(signals, list("ABCDE"), score, train_days=100, test_days=50)
    # In-sample always flatters, because the winner was chosen for being high there.
    assert r["in_sample"]["mean"] > r["out_of_sample"]["mean"]
    assert r["decay"] > 0
    # And a different parameter wins each time, which is what noise looks like.
    assert r["stability"]["consistency"] < 1.0


def test_optimising_that_cannot_beat_fixed_parameters_is_visible():
    signals = [sig(d, {"A": 0.5, "B": 0.5}) for d in range(400)]
    r = wf.run(signals, ["A", "B"], score, train_days=100, test_days=50, baseline="A")
    assert r["beats_baseline"] == pytest.approx(0.0)


# ---------------------------------------------------------------- guards

def test_thin_folds_are_skipped_not_allowed_to_vote():
    signals = [sig(d, {"A": 1.0}) for d in range(0, 400, 30)]   # ~13 signals total
    r = wf.run(signals, ["A"], score, train_days=100, test_days=50, min_train=30)
    assert r["n_folds"] == 0 and r["skipped_folds"] > 0


def test_unscorable_signals_are_dropped_not_counted_as_zero():
    signals = [sig(d, {"A": 1.0} if d % 2 else {}) for d in range(400)]
    r = wf.run(signals, ["A"], score, train_days=100, test_days=50)
    assert r["out_of_sample"]["mean"] == pytest.approx(1.0)


def test_empty_input_is_reported_not_crashed():
    assert "error" in wf.run([], ["A"], score, train_days=10, test_days=5)
    assert "error" in wf.run([sig(1, {"A": 1.0})], [], score, train_days=10, test_days=5)
