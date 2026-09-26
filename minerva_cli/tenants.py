"""Parse authoritative tenant answers from a Google Forms CSV export."""

import csv
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit


# Question title, config path, validation kind, required answer.
FIELDS = (
    ("Tenant ID", "slug", "slug", True),
    ("Organization name", "name", "text", True),
    ("Website URL", "domain", "url", True),
    ("Contact email", "email", "email", True),
    ("Discord invite URL", "discord", "url", False),
    ("Instagram URL", "instagram", "url", False),
    ("LinkedIn URL", "linkedin", "url", False),
    ("Devpost event URL", "devpost", "url", False),
    ("Brand heart or symbol", "heart", "text", False),
    ("Logo URL", "logo", "url", True),
    ("Google Calendar ID", "calendarid", "text", True),
    ("Event name", "event.name", "text", True),
    ("Event start", "event.startTime", "datetime", True),
    ("Event end", "event.endTime", "datetime", True),
    ("Submission deadline", "event.deadline", "datetime", True),
    ("Git commit grace period (minutes)", "event.gitCommitGraceWindowMinutes", "integer", False),
    ("Registration opening override (advanced)", "event.openOffset", "text", False),
)
# Question prefix, config section, lock key. Each lock has opens/closes answers.
SCHEDULES = (
    ("Participant registration", "forms", "participant"),
    ("Judge registration", "forms", "judge"),
    ("Speaker registration", "forms", "speaker"),
    ("Superadmin registration", "forms", "superadmin"),
    ("Volunteer registration", "forms", "volunteer"),
    ("Project submission form", "forms", "submission"),
    ("Feedback form", "forms", "feedback"),
    ("Judge assignments", "judge", "assignments"),
    ("Judge submissions", "judge", "submissions"),
    ("Judge orientation", "judge", "orientation"),
    ("Judge certificate", "judge", "certificate"),
    ("Sponsor resume book", "sponsor", "resume-book"),
    ("Sponsor team projects", "sponsor", "team-projects"),
    ("Sponsor analytics", "sponsor", "analytics"),
    ("Live check-in", "live", "checkin"),
    ("Live teams", "live", "teams"),
)
# Question title, filename/input key, registry group, registry export key.
DESCRIPTIONS = (
    ("Participant registration introduction", "participants.mdx", "headers", "participant"),
    ("Judge registration introduction", "judges.mdx", "headers", "judge"),
    ("Speaker registration introduction", "speakers.mdx", "headers", "speaker"),
    ("Superadmin registration introduction", "superadmins.mdx", "headers", "superadmin"),
    ("Volunteer registration introduction", "volunteers.mdx", "headers", "volunteer"),
    ("Feedback form introduction", "feedback.mdx", "headers", "feedback"),
    ("Project submission instructions", "submission.mdx", "headers", "submission"),
    ("Event rules", "rules.mdx", "markdown", "rules"),
    ("Venue information", "venue.mdx", "markdown", "venue"),
    ("Code of conduct", "code-of-conduct.mdx", "markdown", "codeOfConduct"),
    ("Judge orientation guide", "judge-orientation.mdx", "markdown", "orientation"),
)
HEADERS = (
    *(title for title, *_ in FIELDS),
    *(title + suffix for title, *_ in SCHEDULES for suffix in (" opens", " closes")),
    *(title for title, *_ in DESCRIPTIONS),
)
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
EMAIL = re.compile(
    r"(?!\.)(?!.*\.\.)[A-Za-z0-9_'+\-.]*[A-Za-z0-9_+-]@"
    r"(?:[A-Za-z0-9][A-Za-z0-9-]*\.)+[A-Za-z]{2,}"
)
ISO_DATETIME = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?"
    r"(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)", re.ASCII
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
            parts.port  # Validate numeric port and range without network access.
    except ValueError:
        fail(row, title, "invalid absolute URL")


def validate_datetime(value: str, row: int, title: str) -> datetime:
    try:
        if not ISO_DATETIME.fullmatch(value):
            raise ValueError("missing explicit timezone or invalid syntax")
        return datetime.fromisoformat(value)
    except ValueError:
        fail(row, title, "invalid ISO datetime with explicit timezone")


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
                dates[key] = validate_datetime(value, row, title)
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
            values.append(value)
            instants.append(validate_datetime(value, row, title + suffix))
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
                fail(1, "headers", f"missing: {sorted(missing)}; unknown: {sorted(unknown)}")
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
                tenant = parse_row(dict(zip(headers, values)), row_number)
                if tenant.slug in seen:
                    fail(row_number, "Tenant ID", "duplicate tenant")
                seen.add(tenant.slug)
                tenants.append(tenant)
        except csv.Error as error:
            fail(row_number, "CSV", str(error))
    return tenants
