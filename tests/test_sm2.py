import pytest

from memento.sm2 import MIN_EASE, Grade, Schedule, next_ease, review


def run(qualities):
    """Apply a sequence of qualities to a new card; return each (interval, ease)."""
    schedule = Schedule()
    history = []
    for quality in qualities:
        schedule = review(schedule, quality)
        history.append((schedule.interval, schedule.ease))
    return history


def test_perfect_answers_follow_the_published_sequence():
    # Intervals 1, 6, then I(n) = I(n-1) * EF using the EF *before* the update.
    assert run([5, 5, 5, 5]) == [(1, 2.6), (6, 2.7), (16, 2.8), (45, 2.9)]


def test_good_answers_keep_ease_and_round_half_up():
    # 15 * 2.5 = 37.5 rounds to 38: halves always round up (Python's built-in
    # round() uses banker's rounding, e.g. round(6.5) == 6).
    assert run([4, 4, 4, 4]) == [(1, 2.5), (6, 2.5), (15, 2.5), (38, 2.5)]


def test_hard_answers_lower_ease_each_time():
    assert run([3, 3, 3, 3]) == [(1, 2.36), (6, 2.22), (13, 2.08), (27, 1.94)]


@pytest.mark.parametrize(
    ("quality", "delta"), [(5, 0.1), (4, 0.0), (3, -0.14), (2, -0.32), (1, -0.54), (0, -0.8)]
)
def test_ease_adjustment_for_each_quality(quality, delta):
    assert next_ease(2.5, quality) == pytest.approx(2.5 + delta)


def test_failure_resets_repetitions_but_keeps_reduced_ease():
    schedule = Schedule()
    for quality in (5, 5, 5):
        schedule = review(schedule, quality)
    assert (schedule.repetitions, schedule.interval) == (3, 16)

    failed = review(schedule, 1)
    assert failed == Schedule(repetitions=0, ease=pytest.approx(2.26), interval=1)
    # Relearning starts over at 1 day, then 6 days.
    assert review(failed, 4).interval == 1
    assert review(review(failed, 4), 4).interval == 6


def test_ease_never_drops_below_minimum():
    history = run([0] * 10)
    assert all(interval == 1 for interval, _ in history)
    assert history[-1][1] == MIN_EASE


def test_invalid_quality_is_rejected():
    with pytest.raises(ValueError):
        review(Schedule(), 6)


def test_grade_buttons_map_to_sm2_qualities():
    assert [g.quality for g in Grade] == [1, 3, 4, 5]
    assert Grade.AGAIN.quality < 3 <= Grade.HARD.quality  # only Again is a fail
