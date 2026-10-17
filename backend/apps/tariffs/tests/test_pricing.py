"""Visit pricing: started minutes, local day/night boundaries, tariff changes."""

import random
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from apps.tariffs.pricing import (
    MINUTE_US,
    PriceSegment,
    TariffRate,
    price_visit,
    tariff_from_row,
)

BISHKEK = ZoneInfo("Asia/Bishkek")


def at(*parts, zone=BISHKEK):
    return datetime(*parts, tzinfo=zone)


def bishkek(**overrides):
    values = dict(
        effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
        timezone="Asia/Bishkek",
        day_starts_at=time(7, 0),
        night_starts_at=time(23, 0),
        day_rate_per_minute_kopecks=200,
        night_rate_per_minute_kopecks=100,
    )
    values.update(overrides)
    return TariffRate(**values)


def _assert_balanced(quote):
    assert type(quote.total_kopecks) is int
    assert quote.total_kopecks == sum(
        segment.minutes * segment.rate_per_minute_kopecks for segment in quote.segments
    )
    for segment in quote.segments:
        assert type(segment.minutes) is int
        assert type(segment.rate_per_minute_kopecks) is int
        assert segment.minutes > 0
        assert segment.kind in {"day", "night"}


def test_daytime_half_hour():
    quote = price_visit(at(2026, 6, 1, 10, 0), at(2026, 6, 1, 10, 30), [bishkek()])

    assert quote.segments == (
        PriceSegment(at(2026, 6, 1, 10, 0), 30, 200, "day"),
    )
    assert quote.total_kopecks == 6000
    _assert_balanced(quote)


def test_entirely_at_night():
    quote = price_visit(at(2026, 6, 1, 1, 10), at(2026, 6, 1, 1, 40), [bishkek()])

    assert quote.segments == (
        PriceSegment(at(2026, 6, 1, 1, 10), 30, 100, "night"),
    )
    assert quote.total_kopecks == 3000
    _assert_balanced(quote)


def test_day_into_night_at_23():
    quote = price_visit(at(2026, 6, 1, 22, 50), at(2026, 6, 1, 23, 10), [bishkek()])

    assert quote.segments == (
        PriceSegment(at(2026, 6, 1, 22, 50), 10, 200, "day"),
        PriceSegment(at(2026, 6, 1, 23, 0), 10, 100, "night"),
    )
    assert quote.total_kopecks == 3000
    _assert_balanced(quote)


def test_night_into_day_at_07():
    quote = price_visit(at(2026, 6, 1, 6, 50), at(2026, 6, 1, 7, 10), [bishkek()])

    assert quote.segments == (
        PriceSegment(at(2026, 6, 1, 6, 50), 10, 100, "night"),
        PriceSegment(at(2026, 6, 1, 7, 0), 10, 200, "day"),
    )
    assert quote.total_kopecks == 3000
    _assert_balanced(quote)

    started_before = price_visit(
        at(2026, 6, 1, 6, 59, 59), at(2026, 6, 1, 7, 0, 59), [bishkek()]
    )
    assert started_before.segments == (
        PriceSegment(at(2026, 6, 1, 6, 59, 59), 1, 100, "night"),
    )
    on_the_hour = price_visit(
        at(2026, 6, 1, 7, 0, 0), at(2026, 6, 1, 7, 1, 0), [bishkek()]
    )
    assert on_the_hour.segments == (
        PriceSegment(at(2026, 6, 1, 7, 0, 0), 1, 200, "day"),
    )


def test_across_midnight_stays_night():
    quote = price_visit(at(2026, 6, 1, 23, 50), at(2026, 6, 2, 0, 10), [bishkek()])

    assert quote.segments == (
        PriceSegment(at(2026, 6, 1, 23, 50), 20, 100, "night"),
    )
    assert quote.total_kopecks == 2000
    _assert_balanced(quote)


def test_control_example_splits_on_minute_starts():
    entry = at(2026, 6, 1, 22, 59, 30)
    quote = price_visit(entry, at(2026, 6, 1, 23, 1, 0), [bishkek()])

    assert quote.segments == (
        PriceSegment(entry, 1, 200, "day"),
        PriceSegment(entry + timedelta(seconds=60), 1, 100, "night"),
    )
    assert quote.segments[1].starts_at == at(2026, 6, 1, 23, 0, 30)
    assert quote.total_kopecks == 300
    _assert_balanced(quote)


def test_minute_is_classified_by_its_start():
    night_on_the_hour = price_visit(
        at(2026, 6, 1, 23, 0, 0), at(2026, 6, 1, 23, 1, 0), [bishkek()]
    )
    assert night_on_the_hour.segments == (
        PriceSegment(at(2026, 6, 1, 23, 0, 0), 1, 100, "night"),
    )

    day_that_crosses = price_visit(
        at(2026, 6, 1, 22, 59, 59), at(2026, 6, 1, 23, 0, 59), [bishkek()]
    )
    assert day_that_crosses.segments == (
        PriceSegment(at(2026, 6, 1, 22, 59, 59), 1, 200, "day"),
    )
    assert day_that_crosses.total_kopecks == 200


def test_visit_longer_than_a_day_crosses_several_boundaries():
    quote = price_visit(at(2026, 6, 1, 22, 0), at(2026, 6, 3, 8, 0), [bishkek()])

    assert quote.segments == (
        PriceSegment(at(2026, 6, 1, 22, 0), 60, 200, "day"),
        PriceSegment(at(2026, 6, 1, 23, 0), 8 * 60, 100, "night"),
        PriceSegment(at(2026, 6, 2, 7, 0), 16 * 60, 200, "day"),
        PriceSegment(at(2026, 6, 2, 23, 0), 8 * 60, 100, "night"),
        PriceSegment(at(2026, 6, 3, 7, 0), 60, 200, "day"),
    )
    assert quote.total_kopecks == 312_000
    _assert_balanced(quote)


def test_partial_minutes_round_up_and_an_exact_minute_does_not():
    one_second = price_visit(
        at(2026, 6, 1, 10, 0, 0), at(2026, 6, 1, 10, 0, 1), [bishkek()]
    )
    exact = price_visit(
        at(2026, 6, 1, 10, 0, 0), at(2026, 6, 1, 10, 1, 0), [bishkek()]
    )
    one_extra = price_visit(
        at(2026, 6, 1, 10, 0, 0), at(2026, 6, 1, 10, 1, 1), [bishkek()]
    )

    assert one_second.segments == (PriceSegment(at(2026, 6, 1, 10, 0), 1, 200, "day"),)
    assert exact.segments == (PriceSegment(at(2026, 6, 1, 10, 0), 1, 200, "day"),)
    assert one_extra.segments == (PriceSegment(at(2026, 6, 1, 10, 0), 2, 200, "day"),)
    assert one_second.total_kopecks == 200
    assert exact.total_kopecks == 200
    assert one_extra.total_kopecks == 400


def test_tariff_change_splits_the_visit():
    first = bishkek()
    second = bishkek(
        effective_from=at(2026, 6, 1, 10, 15),
        day_rate_per_minute_kopecks=300,
        night_rate_per_minute_kopecks=50,
    )
    quote = price_visit(
        at(2026, 6, 1, 10, 0),
        at(2026, 6, 1, 10, 30),
        [second, first],
    )

    assert quote.segments == (
        PriceSegment(at(2026, 6, 1, 10, 0), 15, 200, "day"),
        PriceSegment(at(2026, 6, 1, 10, 15), 15, 300, "day"),
    )
    assert quote.total_kopecks == 7500
    _assert_balanced(quote)

    same_rate = bishkek(effective_from=at(2026, 6, 1, 10, 10))
    split = price_visit(
        at(2026, 6, 1, 10, 0), at(2026, 6, 1, 10, 20), [first, same_rate]
    )
    assert split.segments == (
        PriceSegment(at(2026, 6, 1, 10, 0), 10, 200, "day"),
        PriceSegment(at(2026, 6, 1, 10, 10), 10, 200, "day"),
    )

    between_minutes = bishkek(
        effective_from=at(2026, 6, 1, 10, 15, 30),
        day_rate_per_minute_kopecks=300,
    )
    offset = price_visit(
        at(2026, 6, 1, 10, 0),
        at(2026, 6, 1, 10, 30),
        [first, between_minutes],
    )
    assert offset.segments == (
        PriceSegment(at(2026, 6, 1, 10, 0), 16, 200, "day"),
        PriceSegment(at(2026, 6, 1, 10, 16), 14, 300, "day"),
    )


def test_zero_duration_is_free():
    instant = at(2026, 6, 1, 10, 0)
    quote = price_visit(instant, instant, [bishkek()])

    assert quote.total_kopecks == 0
    assert quote.segments == ()

    without_tariffs = price_visit(instant, instant, [])
    assert without_tariffs.total_kopecks == 0
    assert without_tariffs.segments == ()


def test_rejects_naive_datetimes_early_exit_and_missing_tariff():
    aware = at(2026, 6, 1, 10, 0)
    naive = datetime(2026, 6, 1, 10, 0)

    with pytest.raises(ValueError, match="entry must be timezone-aware"):
        price_visit(naive, aware, [bishkek()])
    with pytest.raises(ValueError, match="exit must be timezone-aware"):
        price_visit(aware, naive, [bishkek()])
    with pytest.raises(ValueError, match="exit is before entry"):
        price_visit(aware, at(2026, 6, 1, 9, 0), [bishkek()])
    with pytest.raises(ValueError, match="no tariff covers the minute"):
        price_visit(aware, at(2026, 6, 1, 10, 5), [])
    later = bishkek(effective_from=at(2026, 6, 1, 10, 5))
    with pytest.raises(ValueError, match="no tariff covers the minute starting at"):
        price_visit(aware, at(2026, 6, 1, 10, 10), [later])


def test_utc_instants_use_the_tariff_timezone():
    entry = datetime(2026, 6, 1, 16, 59, 30, tzinfo=timezone.utc)
    quote = price_visit(
        entry,
        datetime(2026, 6, 1, 17, 1, 0, tzinfo=timezone.utc),
        [bishkek()],
    )

    assert quote.segments == (
        PriceSegment(entry, 1, 200, "day"),
        PriceSegment(entry + timedelta(seconds=60), 1, 100, "night"),
    )
    assert quote.segments[0].starts_at.astimezone(BISHKEK).time() == time(22, 59, 30)
    assert quote.segments[1].starts_at.astimezone(BISHKEK).time() == time(23, 0, 30)
    assert quote.total_kopecks == 300
    _assert_balanced(quote)


def test_matches_a_per_minute_reference():
    tariffs = [bishkek()]
    cases = [
        (at(2026, 6, 1, 10, 0), at(2026, 6, 1, 10, 30), tariffs),
        (at(2026, 6, 1, 1, 10), at(2026, 6, 1, 1, 40), tariffs),
        (at(2026, 6, 1, 22, 50), at(2026, 6, 1, 23, 10), tariffs),
        (at(2026, 6, 1, 6, 50), at(2026, 6, 1, 7, 10), tariffs),
        (at(2026, 6, 1, 23, 50), at(2026, 6, 2, 0, 10), tariffs),
        (at(2026, 6, 1, 22, 59, 30), at(2026, 6, 1, 23, 1, 0), tariffs),
        (at(2026, 6, 1, 22, 59, 59), at(2026, 6, 1, 23, 0, 59), tariffs),
        (at(2026, 6, 1, 23, 0, 0), at(2026, 6, 1, 23, 1, 0), tariffs),
        (at(2026, 6, 1, 22, 0), at(2026, 6, 3, 8, 0), tariffs),
        (at(2026, 6, 1, 10, 0, 0), at(2026, 6, 1, 10, 0, 1), tariffs),
        (at(2026, 6, 1, 10, 0, 0), at(2026, 6, 1, 10, 1, 0), tariffs),
        (at(2026, 6, 1, 10, 0, 0), at(2026, 6, 1, 10, 1, 1), tariffs),
        (at(2026, 6, 1, 10, 0), at(2026, 6, 1, 10, 0), tariffs),
        (
            datetime(2026, 6, 1, 16, 59, 30, tzinfo=timezone.utc),
            datetime(2026, 6, 1, 17, 1, 0, tzinfo=timezone.utc),
            tariffs,
        ),
        (
            at(2026, 6, 1, 10, 0),
            at(2026, 6, 1, 10, 30),
            [bishkek(), bishkek(effective_from=at(2026, 6, 1, 10, 15), day_rate_per_minute_kopecks=300)],
        ),
    ]
    cases.extend(_random_cases(random.Random(20261017)))

    for entered_at, exited_at, schedule in cases:
        quote = price_visit(entered_at, exited_at, schedule)
        expected = _reference_price(entered_at, exited_at, schedule)
        assert quote.total_kopecks == expected.total_kopecks
        assert quote.segments == expected.segments
        _assert_balanced(quote)


def test_tariff_from_row_copies_model_fields():
    row = SimpleNamespace(
        effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
        timezone="Asia/Bishkek",
        day_starts_at=time(7, 0),
        night_starts_at=time(23, 0),
        day_rate_per_minute_kopecks=200,
        night_rate_per_minute_kopecks=100,
    )

    assert tariff_from_row(row) == bishkek()


def _random_cases(rng):
    base = bishkek()
    cases = []
    for _ in range(40):
        entry = at(
            2026,
            6,
            rng.randint(1, 25),
            rng.randint(0, 23),
            rng.randint(0, 59),
            rng.randint(0, 59),
        )
        if rng.random() < 0.3:
            entry = entry.astimezone(timezone.utc)
        duration = rng.randint(0, 3 * 24 * 3600)
        exit_at = entry + timedelta(seconds=duration)
        schedule = [base]
        if duration > 120 and rng.random() < 0.5:
            shift = rng.randint(60, duration - 60)
            schedule.append(
                bishkek(
                    effective_from=entry + timedelta(seconds=shift),
                    day_rate_per_minute_kopecks=rng.choice([150, 250, 400]),
                    night_rate_per_minute_kopecks=rng.choice([50, 80, 120]),
                )
            )
        cases.append((entry, exit_at, schedule))
    return cases


def _reference_price(entered_at, exited_at, tariffs):
    """Independent minute loop. The production code must not do this."""

    duration_us = _duration_us(exited_at - entered_at)
    if duration_us == 0:
        from apps.tariffs.pricing import VisitPrice

        return VisitPrice(0, ())
    count = (duration_us + MINUTE_US - 1) // MINUTE_US
    segments = []
    for index in range(count):
        start = entered_at + timedelta(microseconds=index * MINUTE_US)
        tariff = max(
            (item for item in tariffs if item.effective_from <= start),
            key=lambda item: item.effective_from,
        )
        clock = start.astimezone(ZoneInfo(tariff.timezone)).time()
        if tariff.day_starts_at <= clock < tariff.night_starts_at:
            kind = "day"
            rate = tariff.day_rate_per_minute_kopecks
        else:
            kind = "night"
            rate = tariff.night_rate_per_minute_kopecks
        if (
            segments
            and segments[-1].kind == kind
            and segments[-1].rate_per_minute_kopecks == rate
            and segments[-1].starts_at + timedelta(minutes=segments[-1].minutes) == start
            and _same_tariff_run(segments[-1], tariff, entered_at, tariffs)
        ):
            previous = segments[-1]
            segments[-1] = PriceSegment(
                previous.starts_at,
                previous.minutes + 1,
                previous.rate_per_minute_kopecks,
                previous.kind,
            )
        else:
            segments.append(PriceSegment(start, 1, rate, kind))
    total = sum(segment.minutes * segment.rate_per_minute_kopecks for segment in segments)
    from apps.tariffs.pricing import VisitPrice

    return VisitPrice(total, tuple(segments))


def _same_tariff_run(segment, tariff, entered_at, tariffs):
    """Keep a new tariff row as its own segment even when the rate is unchanged."""

    probe = segment.starts_at
    active = max(
        (item for item in tariffs if item.effective_from <= probe),
        key=lambda item: item.effective_from,
    )
    return active.effective_from == tariff.effective_from


def _duration_us(delta):
    return delta.days * 86_400 * 1_000_000 + delta.seconds * 1_000_000 + delta.microseconds
