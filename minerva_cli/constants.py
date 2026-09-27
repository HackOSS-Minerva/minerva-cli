"""Shared tenant contract and fixed publication settings."""

import re
from pathlib import Path

MINERVA_CHECKOUT = Path(__file__).resolve().parents[2] / "minerva"
MINERVA_REPOSITORY = "HackOSS-Minerva/minerva"
BASE_BRANCH = "main"

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
