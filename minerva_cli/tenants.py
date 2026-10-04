"""Parse authoritative tenant answers from a Google Forms CSV export."""

import csv
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .constants import (
    DATE_FORMATS,
    DESCRIPTIONS,
    EMAIL,
    FIELDS,
    GIT_COMMIT_GRACE_WINDOW_MINUTES,
    HEADERS,
    PACIFIC_TIMEZONE,
    SCHEDULES,
    SLUG,
    TIME_FORMATS,
)


@dataclass
class TenantInput:
    slug: str
    config: dict
    descriptions: dict[str, str]


def fail(row: int, title: str, reason: str):
    raise ValueError(f"row {row}: {title}: {reason}")


def validate_url(value: str, row: int, title: str):
    # urlsplit strips some controls, so reject them before parsing.
    if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
        fail(row, title, "URL must not contain control characters")
    try:
        if not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value):
            raise ValueError("missing scheme")
        parts = urlsplit(value)
        if parts.scheme in {"http", "https", "ftp", "ws", "wss"}:
            # These schemes allow omitted/repeated slashes in the old URL parser.
            remainder = value.split(":", 1)[1].replace("\\", "/").lstrip("/")
            parts = urlsplit(parts.scheme + "://" + remainder)
            if not parts.hostname or any(char.isspace() for char in parts.hostname):
                raise ValueError("missing or invalid hostname")
        if parts.netloc:
            _ = parts.port  # Validate numeric port and range without network access.
    except ValueError:
        fail(row, title, "invalid absolute URL")


def _parse_part(value: str, formats: tuple[str, ...], row: int, title: str) -> datetime:
    if not value:
        fail(row, title, "required")
    for pattern in formats:
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            pass
    fail(row, title, "invalid date/time from the Form response sheet")


def parse_datetime(answers: dict[str, str], row: int, title: str) -> tuple[str, datetime]:
    """Combine native Form date/time answers using California's daylight-saving rules."""
    parts = []
    errors = []
    for suffix, formats in ((" date", DATE_FORMATS), (" time", TIME_FORMATS)):
        try:
            parts.append(_parse_part(answers[title + suffix].strip(), formats, row, title + suffix))
        except ValueError as error:
            errors.append(str(error))
    if errors:
        raise ValueError("\n".join(errors))
    date, time = parts
    local = datetime.combine(date.date(), time.time())
    try:
        zone = ZoneInfo(PACIFIC_TIMEZONE)
    except ZoneInfoNotFoundError:
        fail(row, title, "Pacific timezone data unavailable; install system timezone data")
    # Round-trip both folds: zero instants means a skipped time; two means a repeated time.
    instants = set()
    try:
        for fold in (0, 1):
            instant = local.replace(tzinfo=zone, fold=fold).astimezone(UTC)
            if instant.astimezone(zone).replace(tzinfo=None) == local:
                instants.add(instant)
    except OverflowError:
        fail(row, title, "Pacific date/time is outside the supported range")
    if len(instants) != 1:
        fail(
            row,
            title,
            "ambiguous or nonexistent Pacific time during daylight saving; choose another time",
        )
    normalized = instants.pop().astimezone(zone).isoformat()
    # Fixed-offset datetimes compare by instant even across daylight-saving transitions.
    return normalized, datetime.fromisoformat(normalized)


def parse_row(answers: dict[str, str], row: int) -> TenantInput:
    config = {
        "event": {"gitCommitGraceWindowMinutes": GIT_COMMIT_GRACE_WINDOW_MINUTES},
        "locks": {},
    }
    dates = {}
    errors = []
    for title, key, kind, required in FIELDS:
        try:
            if kind == "datetime":
                value, dates[key] = parse_datetime(answers, row, title)
                config["event"][key.split(".", 1)[1]] = value
                continue
            value = answers[title].strip()
            if required and not value:
                fail(row, title, "required")
            if value:
                if kind == "slug" and not SLUG.fullmatch(value):
                    fail(row, title, "expected lowercase letters, digits and single hyphens")
                if kind == "url":
                    validate_url(value, row, title)
                if kind == "email" and not EMAIL.fullmatch(value):
                    fail(row, title, "invalid email")
        except ValueError as error:
            errors.extend(str(error).splitlines())
            continue
        if key.startswith("event."):
            if value != "":
                config["event"][key.split(".", 1)[1]] = value
        else:
            config[key] = value
    if "event.startTime" in dates:
        start = dates["event.startTime"]
        if "event.endTime" in dates and dates["event.endTime"] <= start:
            errors.append(f"row {row}: Event end: must be after Event start")
        if "event.deadline" in dates and dates["event.deadline"] < start:
            errors.append(f"row {row}: Submission deadline: must be at or after Event start")
    for title, section, key in SCHEDULES:
        values = []
        instants = []
        for suffix in (" opens", " closes"):
            try:
                value, instant = parse_datetime(answers, row, title + suffix)
                values.append(value)
                instants.append(instant)
            except ValueError as error:
                errors.extend(str(error).splitlines())
        if len(instants) != 2:
            continue
        if instants[1] <= instants[0]:
            errors.append(f"row {row}: {title} closes: must be after opening time")
        config["locks"].setdefault(section, {})[key] = values
    if errors:
        raise ValueError("\n".join(errors))
    descriptions = {filename: answers[title] for title, filename, *_ in DESCRIPTIONS}
    return TenantInput(config["slug"], config, descriptions)


def parse_tenants(path: Path) -> list[TenantInput]:
    """Validate every nonempty CSV record; never write files or mutate Git state."""
    tenants = []
    seen = set()
    errors = []
    row_number = 1
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        try:
            headers = [header.strip() for header in next(reader, [])]
            if len(headers) != len(set(headers)):
                fail(1, "headers", "duplicate question title")
            expected = set(HEADERS)
            missing = expected - set(headers)
            unknown = set(headers) - expected - {"Timestamp"}
            if missing or unknown:
                fail(1, "headers", f"missing: {sorted(missing)}; unknown columns: {len(unknown)}")
            # Count CSV records, not physical lines inside quoted Markdown answers.
            while True:
                row_number += 1
                values = next(reader, None)
                if values is None:
                    break
                if not any(value.strip() for value in values):
                    continue
                if len(values) != len(headers):
                    errors.append(
                        f"row {row_number}: record: expected {len(headers)} cells, got {len(values)}"
                    )
                    continue
                answers = dict(zip(headers, values, strict=True))
                slug = answers["Tenant ID"].strip()
                row_errors = []
                if SLUG.fullmatch(slug):
                    if slug in seen:
                        row_errors.append("Tenant ID: duplicate tenant")
                    seen.add(slug)
                try:
                    tenants.append(parse_row(answers, row_number))
                except ValueError as error:
                    row_errors.extend(
                        line.removeprefix(f"row {row_number}: ") for line in str(error).splitlines()
                    )
                if row_errors:
                    label = f"row {row_number}"
                    if SLUG.fullmatch(slug):
                        label += f" ({slug})"
                    errors.append(label + ":\n  - " + "\n  - ".join(row_errors))
        except csv.Error as error:
            errors.append(f"row {row_number}: CSV: {error}")
    if errors:
        raise ValueError("CSV validation failed:\n" + "\n".join(errors))
    return tenants
