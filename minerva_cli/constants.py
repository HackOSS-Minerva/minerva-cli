"""Shared tenant contract and fixed publication settings."""

import re
from pathlib import Path

MINERVA_CHECKOUT = Path(__file__).resolve().parents[2] / "minerva"
MINERVA_REPOSITORY = "HackOSS-Minerva/minerva"
BASE_BRANCH = "main"
GIT_COMMIT_GRACE_WINDOW_MINUTES = 15
PACIFIC_TIMEZONE = "America/Los_Angeles"
DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y")
TIME_FORMATS = ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p")
LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s"
    " | %(filename)s:%(lineno)d | %(funcName)s | %(message)s"
)

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
    ("Logo URL", "logo", "url", True),
    ("Google Calendar ID", "calendarid", "text", True),
    ("Event name", "event.name", "text", True),
    ("Event start", "event.startTime", "datetime", True),
    ("Event end", "event.endTime", "datetime", True),
    ("Submission deadline", "event.deadline", "datetime", True),
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
    *(
        title + part
        for title, _, kind, _ in FIELDS
        for part in ((" date", " time") if kind == "datetime" else ("",))
    ),
    *(
        title + suffix + part
        for title, *_ in SCHEDULES
        for suffix in (" opens", " closes")
        for part in (" date", " time")
    ),
    *(title for title, *_ in DESCRIPTIONS),
)
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
EMAIL = re.compile(
    r"(?!\.)(?!.*\.\.)[A-Za-z0-9_'+\-.]*[A-Za-z0-9_+-]@"
    r"(?:[A-Za-z0-9][A-Za-z0-9-]*\.)+[A-Za-z]{2,}"
)
