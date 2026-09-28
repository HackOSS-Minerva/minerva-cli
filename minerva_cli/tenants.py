"""Parse authoritative tenant answers from a Google Forms CSV export."""

import csv
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .constants import (
    DESCRIPTIONS,
    EMAIL,
    FIELDS,
    HEADERS,
    ISO_DATETIME,
    PACIFIC_DATETIME,
    PACIFIC_TIMEZONE,
    SCHEDULES,
    SLUG,
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


def parse_datetime(value: str, row: int, title: str) -> tuple[str, datetime]:
    """Preserve ISO answers; convert readable Pacific answers to offset timestamps."""
    try:
        if ISO_DATETIME.fullmatch(value):
            return value, datetime.fromisoformat(value)
        match = PACIFIC_DATETIME.fullmatch(value)
        if not match:
            raise ValueError("invalid syntax")
        date, hour, minute, period = match.groups()
        local = datetime.fromisoformat(date).replace(
            hour=int(hour) % 12 + (12 if period.upper() == "PM" else 0), minute=int(minute)
        )
    except ValueError:
        fail(row, title, "use YYYY-MM-DD, h:mm AM/PM, PT or an ISO datetime with explicit timezone")
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
            "ambiguous or nonexistent Pacific time during daylight saving; use an explicit ISO offset",
        )
    normalized = instants.pop().astimezone(zone).isoformat()
    # Fixed-offset datetimes compare by instant even across daylight-saving transitions.
    return normalized, datetime.fromisoformat(normalized)


def parse_row(answers: dict[str, str], row: int) -> TenantInput:
    config = {"event": {}, "locks": {}}
    dates = {}
    for title, key, kind, required in FIELDS:
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
            if kind == "datetime":
                value, dates[key] = parse_datetime(value, row, title)
            if kind == "integer":
                if not re.fullmatch(r"0|[1-9][0-9]{0,3}", value) or int(value) > 1440:
                    fail(row, title, "must be an integer between 0 and 1440")
                value = int(value)
        if key.startswith("event."):
            if value != "":
                config["event"][key.split(".", 1)[1]] = value
        else:
            config[key] = value
    if dates["event.endTime"] <= dates["event.startTime"]:
        fail(row, "Event end", "must be after Event start")
    if dates["event.deadline"] < dates["event.startTime"]:
        fail(row, "Submission deadline", "must be at or after Event start")
    for title, section, key in SCHEDULES:
        values = []
        instants = []
        for suffix in (" opens", " closes"):
            value = answers[title + suffix].strip()
            if not value:
                fail(row, title + suffix, "required")
            value, instant = parse_datetime(value, row, title + suffix)
            values.append(value)
            instants.append(instant)
        if instants[1] <= instants[0]:
            fail(row, title + " closes", "must be after opening time")
        config["locks"].setdefault(section, {})[key] = values
    descriptions = {filename: answers[title] for title, filename, *_ in DESCRIPTIONS}
    return TenantInput(config["slug"], config, descriptions)


def parse_tenants(path: Path) -> list[TenantInput]:
    """Validate every nonempty CSV record; never write files or mutate Git state."""
    tenants = []
    seen = set()
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
                    fail(row_number, "record", f"expected {len(headers)} cells, got {len(values)}")
                tenant = parse_row(dict(zip(headers, values, strict=True)), row_number)
                if tenant.slug in seen:
                    fail(row_number, "Tenant ID", "duplicate tenant")
                seen.add(tenant.slug)
                tenants.append(tenant)
        except csv.Error as error:
            fail(row_number, "CSV", str(error))
    return tenants
