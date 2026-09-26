"""Synthetic form responses independent of production field definitions."""

import csv
import os
import subprocess
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


def local_git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                          text=True).stdout.strip()


def git_fixture(root):
    """Local-only origin and checkout with minimal registry integration."""
    remote = root / "origin.git"
    repo = root / "checkout with spaces"
    remote.mkdir()
    repo.mkdir()
    local_git(remote, "init", "--bare", "--initial-branch=main")
    local_git(repo, "init", "--initial-branch=main")
    local_git(repo, "config", "user.name", "Test Operator")
    local_git(repo, "config", "user.email", "operator@example.org")
    local_git(repo, "config", "commit.gpgsign", "false")
    (repo / "tenants").mkdir()
    (repo / "hooks").mkdir()
    (repo / "package.json").write_text('{"name":"minerva"}\n')
    (repo / "tenants/generated.ts").write_text("export const tenantSlugs = [] as const;\n")
    (repo / "hooks/get-tenant.ts").write_text('import { tenantSlugs } from "@/tenants/generated";\n')
    local_git(repo, "add", "package.json", "tenants/generated.ts", "hooks/get-tenant.ts")
    local_git(repo, "commit", "-m", "fixture")
    local_git(repo, "remote", "add", "origin", str(remote))
    local_git(repo, "push", "-u", "origin", "main")
    return repo, remote


def git_environment(root):
    # Keep temporary Git tests independent of the developer's global config/identity.
    return {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test Operator", "GIT_AUTHOR_EMAIL": "operator@example.org",
            "GIT_COMMITTER_NAME": "Test Operator", "GIT_COMMITTER_EMAIL": "operator@example.org"}
