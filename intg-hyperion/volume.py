"""
Volume scale conversion for the AudioControl Hyperion APR-16.

The device's HTTP API only speaks integer percent (0-100). It has no call that
returns decibels, so the percent -> dB relationship was measured by hand:

    0-19 %    explicit lookup table (steps are uneven, up to ~6.5 dB apiece)
    20-95 %   straight line, -57.0 dB to -4.0 dB
    95-100 %  straight line, -4.0 dB to 0.0 dB

Everything here is pure (no I/O, no device state) so it is easy to test.
"""

from __future__ import annotations

# Measured values for the low end of the range: percent -> dB.
LOWER_VOLUME_MAP: dict[int, float] = {
    0: -127.5,
    1: -121.5,
    2: -115.0,
    3: -108.5,
    4: -102.5,
    5: -96.0,
    6: -89.5,
    7: -83.5,
    8: -77.0,
    9: -70.5,
    10: -64.0,
    11: -63.5,
    12: -63.0,
    13: -62.0,
    14: -61.5,
    15: -60.5,
    16: -60.0,
    17: -59.0,
    18: -58.0,
    19: -57.5,
}

MIN_DB = -127.5
MAX_DB = 0.0

TABLE_END_PCT = 20  # the table covers 0..19, the first linear segment starts here
KNEE_PCT = 95  # where the slope changes
TABLE_END_DB = -57.0  # dB at TABLE_END_PCT
KNEE_DB = -4.0  # dB at KNEE_PCT


def _lerp(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    """Linear interpolation of x from the range [x0, x1] onto [y0, y1]."""
    return y0 + (x - x0) / (x1 - x0) * (y1 - y0)


def percent_to_db(percent: float) -> float:
    """Convert a device volume percent (0-100) to dB."""
    pct = max(0.0, min(100.0, percent))

    if pct < TABLE_END_PCT:
        return LOWER_VOLUME_MAP[int(pct)]
    if pct >= 100.0:
        return MAX_DB
    if pct <= KNEE_PCT:
        return _lerp(pct, TABLE_END_PCT, KNEE_PCT, TABLE_END_DB, KNEE_DB)
    return _lerp(pct, KNEE_PCT, 100.0, KNEE_DB, MAX_DB)


def db_to_percent(db: float) -> float:
    """Convert dB back to a device volume percent (0-100)."""
    db = max(MIN_DB, min(MAX_DB, db))

    if db >= MAX_DB:
        return 100.0
    if db <= MIN_DB:
        return 0.0
    if db >= KNEE_DB:
        return _lerp(db, KNEE_DB, MAX_DB, KNEE_PCT, 100.0)
    if db >= TABLE_END_DB:
        return _lerp(db, TABLE_END_DB, KNEE_DB, TABLE_END_PCT, KNEE_PCT)

    # Below the linear region: pick the closest entry in the lookup table.
    return float(min(LOWER_VOLUME_MAP, key=lambda pct: abs(LOWER_VOLUME_MAP[pct] - db)))


def step_percent(current: int, direction: int, *, relative: bool) -> int:
    """
    Return the percent one volume step above (direction > 0) or below the current one.

    Absolute mode moves exactly 1 %. Relative mode aims for 1 dB and rounds to the
    nearest whole percent the device can actually set; if that rounds back to the
    current value it moves 1 % anyway so a button press is never a no-op.
    The result is clamped to 0-100.
    """
    direction = 1 if direction > 0 else -1

    if relative:
        target = round(db_to_percent(percent_to_db(current) + direction))
        if target == current:
            target = current + direction
    else:
        target = current + direction

    return max(0, min(100, target))
