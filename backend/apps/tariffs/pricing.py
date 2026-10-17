"""Price one visit from day/night tariff rows.

The function does not read the database. A tariff is a `TariffRate` with the
same fields as `tariffs.Tariff`. `tariff_from_row` copies a model instance
into that structure.

A started minute is billed from the instant it begins (`entry + i * 60s`),
not from the clock time it happens to cross. The visit is cut at each local
day/night boundary and at each `effective_from`, then the minute starts that
fall inside a piece are counted. That stays proportional to the number of
boundaries, not to the length of the stay.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MINUTE_US = 60 * 1_000_000
DAY = "day"
NIGHT = "night"


@dataclass(frozen=True)
class TariffRate:
    effective_from: datetime
    timezone: str
    day_starts_at: time
    night_starts_at: time
    day_rate_per_minute_kopecks: int
    night_rate_per_minute_kopecks: int


@dataclass(frozen=True)
class PriceSegment:
    starts_at: datetime
    minutes: int
    rate_per_minute_kopecks: int
    kind: str


@dataclass(frozen=True)
class VisitPrice:
    total_kopecks: int
    segments: tuple[PriceSegment, ...]


def tariff_from_row(row):
    return TariffRate(
        effective_from=row.effective_from,
        timezone=row.timezone,
        day_starts_at=row.day_starts_at,
        night_starts_at=row.night_starts_at,
        day_rate_per_minute_kopecks=row.day_rate_per_minute_kopecks,
        night_rate_per_minute_kopecks=row.night_rate_per_minute_kopecks,
    )


def price_visit(entered_at, exited_at, tariffs):
    _require_aware(entered_at, "entry")
    _require_aware(exited_at, "exit")
    if exited_at < entered_at:
        raise ValueError("exit is before entry")
    if _us(exited_at - entered_at) == 0:
        return VisitPrice(total_kopecks=0, segments=())

    segments = []
    for tariff, window_start, window_end in _windows(entered_at, exited_at, tariffs):
        segments.extend(_segments(entered_at, window_start, window_end, tariff))
    total = sum(segment.minutes * segment.rate_per_minute_kopecks for segment in segments)
    return VisitPrice(total_kopecks=total, segments=tuple(segments))


def _windows(entered_at, exited_at, tariffs):
    ordered = sorted(tariffs, key=_effective_from)
    covering = [tariff for tariff in ordered if tariff.effective_from <= entered_at]
    if not covering:
        raise ValueError(
            f"no tariff covers the minute starting at {entered_at.isoformat()}"
        )

    points = [entered_at]
    switch = {}
    for tariff in ordered:
        if entered_at < tariff.effective_from < exited_at:
            points.append(tariff.effective_from)
            switch[tariff.effective_from] = tariff
    points.append(exited_at)

    active = covering[-1]
    for start, end in zip(points, points[1:]):
        if end > start:
            yield active, start, end
        active = switch.get(end, active)


def _segments(entered_at, window_start, window_end, tariff):
    zone = _zone(tariff.timezone)
    cuts = _boundary_cuts(window_start, window_end, tariff, zone)
    segments = []
    for start, end in zip(cuts, cuts[1:]):
        index, count = _minute_span(entered_at, start, end)
        if count == 0:
            continue
        minute_start = entered_at + timedelta(microseconds=index * MINUTE_US)
        kind, rate = _rate_at(minute_start, tariff, zone)
        segments.append(
            PriceSegment(
                starts_at=minute_start,
                minutes=count,
                rate_per_minute_kopecks=rate,
                kind=kind,
            )
        )
    return segments


def _boundary_cuts(window_start, window_end, tariff, zone):
    start = window_start.astimezone(timezone.utc)
    end = window_end.astimezone(timezone.utc)
    cuts = [start, end]
    day = start.astimezone(zone).date()
    last = end.astimezone(zone).date()
    while day <= last:
        for clock in (tariff.day_starts_at, tariff.night_starts_at):
            local = datetime.combine(day, clock.replace(tzinfo=None), tzinfo=zone)
            instant = local.astimezone(timezone.utc)
            if start < instant < end:
                cuts.append(instant)
        day += timedelta(days=1)
    cuts.sort()
    unique = [cuts[0]]
    for instant in cuts[1:]:
        if instant != unique[-1]:
            unique.append(instant)
    return unique


def _minute_span(entered_at, window_start, window_end):
    """Minute indexes [index, index + count) whose starts lie in [window_start, window_end)."""

    index = _minute_index_at_or_after(_us(window_start - entered_at))
    end_index = _minute_index_at_or_after(_us(window_end - entered_at))
    return index, max(0, end_index - index)


def _minute_index_at_or_after(offset_us):
    """Smallest i such that i * 60s is at or after `offset_us` from entry."""

    if offset_us <= 0:
        return 0
    return (offset_us + MINUTE_US - 1) // MINUTE_US


def _rate_at(instant, tariff, zone):
    clock = instant.astimezone(zone).time()
    day_starts = tariff.day_starts_at.replace(tzinfo=None)
    night_starts = tariff.night_starts_at.replace(tzinfo=None)
    if day_starts == night_starts:
        raise ValueError("day and night boundaries must differ")
    if day_starts < night_starts:
        is_day = day_starts <= clock < night_starts
    else:
        is_day = clock >= day_starts or clock < night_starts
    if is_day:
        return DAY, tariff.day_rate_per_minute_kopecks
    return NIGHT, tariff.night_rate_per_minute_kopecks


def _effective_from(tariff):
    _require_aware(tariff.effective_from, "tariff effective_from")
    return tariff.effective_from


def _zone(name):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown tariff timezone: {name}") from exc


def _require_aware(value, label):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _us(delta):
    return (
        delta.days * 86_400 * 1_000_000
        + delta.seconds * 1_000_000
        + delta.microseconds
    )
