"""Synthetic form responses independent of production field definitions."""

import csv
from pathlib import Path


START = "2026-11-21T08:00:00-08:00"
END = "2026-11-21T20:00:00-08:00"
SCHEDULES = (
    "Participant registration", "Judge registration", "Speaker registration",
    "Superadmin registration", "Volunteer registration", "Project submission form",
    "Feedback form", "Judge assignments", "Judge submissions", "Judge orientation",
    "Judge certificate", "Sponsor resume book", "Sponsor team projects",
    "Sponsor analytics", "Live check-in", "Live teams",
)
DESCRIPTIONS = (
    "Participant registration introduction", "Judge registration introduction",
    "Speaker registration introduction", "Superadmin registration introduction",
    "Volunteer registration introduction", "Feedback form introduction",
    "Project submission instructions", "Event rules", "Venue information",
    "Code of conduct", "Judge orientation guide",
)


def response(**overrides):
    row = {
        "Timestamp": "11/01/2026 10:00:00",
        "Tenant ID": "example-hack",
        "Organization name": "Example Hack",
        "Website URL": "https://example.org",
        "Contact email": "team@example.org",
        "Discord invite URL": "",
        "Instagram URL": "",
        "LinkedIn URL": "",
        "Devpost event URL": "",
        "Brand heart or symbol": "",
        "Logo URL": "https://example.org/logo.png",
        "Google Calendar ID": "example@group.calendar.google.com",
        "Event name": "Example Hack 2026",
        "Event start": START,
        "Event end": END,
        "Submission deadline": "2026-11-21T19:00:00-08:00",
        "Git commit grace period (minutes)": "15",
        "Registration opening override (advanced)": "",
    }
    for title in SCHEDULES:
        row[title + " opens"] = START
        row[title + " closes"] = END
    for title in DESCRIPTIONS:
        row[title] = '# Welcome\r\n\r\nSay "hello, tenant".\r\n  Keep indentation.\r\n'
    row.update(overrides)
    return row


def write_csv(path: Path, rows=None, headers=None, bom=False):
    rows = [response()] if rows is None else rows
    headers = list(response()) if headers is None else headers
    with path.open("w", encoding="utf-8-sig" if bom else "utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(rows if rows and isinstance(rows[0], list) else
                         [[row.get(header, "") for header in headers] for row in rows])
    return path
