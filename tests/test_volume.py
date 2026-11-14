"""Tests for the percent <-> dB conversion and volume stepping. These need no device and no dependencies."""

import pytest

from volume import LOWER_VOLUME_MAP, db_to_percent, percent_to_db, step_percent


def test_anchor_points():
    assert percent_to_db(0) == -127.5
    assert percent_to_db(19) == -57.5
    assert percent_to_db(20) == pytest.approx(-57.0)
    assert percent_to_db(95) == pytest.approx(-4.0)
    assert percent_to_db(100) == 0.0


def test_out_of_range_input_is_clamped():
    assert percent_to_db(-10) == -127.5
    assert percent_to_db(250) == 0.0
    assert db_to_percent(-500) == 0.0
    assert db_to_percent(12) == 100.0


def test_percent_to_db_never_decreases():
    values = [percent_to_db(p) for p in range(101)]
    assert values == sorted(values)


@pytest.mark.parametrize("pct", range(20, 101))
def test_round_trip_above_the_table(pct):
    assert db_to_percent(percent_to_db(pct)) == pytest.approx(pct)


@pytest.mark.parametrize("pct", sorted(LOWER_VOLUME_MAP))
def test_round_trip_inside_the_table(pct):
    # 10 -> 11 -> 12 are only 0.5 dB apart; the table must still map each dB back to its own percent.
    assert db_to_percent(LOWER_VOLUME_MAP[pct]) == pct


@pytest.mark.parametrize("relative", [False, True])
def test_stepping_up_always_moves_until_the_top(relative):
    pct, seen = 0, [0]
    while pct < 100:
        nxt = step_percent(pct, 1, relative=relative)
        assert nxt > pct, f"stuck at {pct}%"
        pct = nxt
        seen.append(pct)
    assert pct == 100
    assert step_percent(100, 1, relative=relative) == 100


@pytest.mark.parametrize("relative", [False, True])
def test_stepping_down_always_moves_until_the_bottom(relative):
    pct = 100
    while pct > 0:
        nxt = step_percent(pct, -1, relative=relative)
        assert nxt < pct, f"stuck at {pct}%"
        pct = nxt
    assert pct == 0
    assert step_percent(0, -1, relative=relative) == 0


def test_absolute_step_is_exactly_one_percent():
    assert step_percent(42, 1, relative=False) == 43
    assert step_percent(42, -1, relative=False) == 41


def test_relative_step_is_about_one_db_in_the_linear_region():
    start = 50
    after = step_percent(start, 1, relative=True)
    assert 0.5 <= percent_to_db(after) - percent_to_db(start) <= 1.5


def test_step_result_is_always_an_int_in_range():
    for pct in range(101):
        for direction in (1, -1):
            for relative in (False, True):
                result = step_percent(pct, direction, relative=relative)
                assert isinstance(result, int) and 0 <= result <= 100
