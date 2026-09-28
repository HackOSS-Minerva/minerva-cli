"""Small Git/gh workflow using the operator's existing identity and credentials."""

import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from .constants import BASE_BRANCH, MINERVA_REPOSITORY
from .generate import SyncPlan, apply_plan


def _run(repo: Path, *args: str, input_text: str | None = None) -> str:
    try:
        return subprocess.run(
            args,
            cwd=repo,
            input=input_text,
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        ).stdout.strip()
    except subprocess.CalledProcessError as error:
        # Command output and arguments can contain credentials or tenant data.
        raise RuntimeError(f"{args[0]} {args[1]} failed (exit {error.returncode})") from error
    except OSError as error:
        raise RuntimeError(str(error)) from error


def validate_checkout(repo: Path) -> None:
    root = Path(_run(repo, "git", "rev-parse", "--show-toplevel")).resolve()
    if root != repo.resolve():
        raise RuntimeError("Minerva checkout must point to the repository root")
    hook = repo / "hooks/get-tenant.ts"
    if not (
        (repo / "package.json").is_file()
        and (repo / "tenants/generated.ts").is_file()
        and hook.is_file()
        and re.search(r"""\bfrom\s+["']@/tenants/generated["']""", hook.read_text())
    ):
        raise RuntimeError("Minerva registry integration is missing; install it before tenant sync")


def preflight(repo: Path, base: str = BASE_BRANCH) -> None:
    stage = "base validation"
    try:
        if base.startswith("-"):
            raise RuntimeError("invalid base branch")
        _run(repo, "git", "check-ref-format", f"refs/heads/{base}")
        stage = "base branch"
        if _run(repo, "git", "symbolic-ref", "--short", "HEAD") != base:
            raise RuntimeError(f"checkout must be on {base}")
        stage = "clean worktree"
        if _run(repo, "git", "status", "--porcelain", "--untracked-files=all"):
            raise RuntimeError("a clean worktree is required, including untracked files")
        stage = "fetch"
        remote_ref = f"refs/remotes/origin/{base}"
        _run(repo, "git", "fetch", "--no-tags", "origin", f"+refs/heads/{base}:{remote_ref}")
        stage = "up-to-date base"
        if _run(repo, "git", "rev-parse", "HEAD") != _run(repo, "git", "rev-parse", remote_ref):
            raise RuntimeError(f"{base} must equal origin/{base}; update the checkout first")
        stage = "Git identity"
        for key in ("user.name", "user.email"):
            if not _run(repo, "git", "config", "--get", key):
                raise RuntimeError(f"configure {key} before publishing")
        stage = "GitHub authentication"
        _run(repo, "gh", "auth", "status")
    except RuntimeError as error:
        raise RuntimeError(f"Preflight failed at {stage}: {error}") from error


def publish(repo: Path, plan: SyncPlan, base: str = BASE_BRANCH, draft: bool = False) -> str:
    """Publish a plan after preflight; preserve local work on every failure."""
    if not plan.changes:
        return ""
    branch = "tenant-sync/" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    created = pushed = False
    try:
        stage = "origin repository"
        repository = _run(
            repo, "git", "remote", "get-url", "--push", "--all", "origin"
        ).removesuffix(".git")
        repository = re.sub(r"^git@([^:]+):", r"https://\1/", repository)
        if repository.casefold() != f"https://github.com/{MINERVA_REPOSITORY}".casefold():
            raise RuntimeError(f"origin must have one push URL targeting {MINERVA_REPOSITORY}")
        stage = "branch creation"
        _run(repo, "git", "switch", "-c", branch)
        created = True
        stage = "file write"
        apply_plan(repo, plan)
        stage = "staging"
        _run(repo, "git", "add", "--", *(str(path) for path in plan.changes))
        stage = "commit"
        title = "chore(tenants): sync configuration"
        _run(repo, "git", "commit", "-m", title)
        stage = "push"
        _run(repo, "git", "push", "--set-upstream", "origin", branch)
        pushed = True
        stage = "PR creation"
        body = (
            "### Context\nUpdate tenant configuration from the exported response CSV.\n\n"
            "### Core Changes\n"
            + "".join(
                f"- Sync `{slug}` configuration and description files.\n"
                for slug in plan.processed_slugs
            )
            + "\n### Testing & Verification\n"
            "- Validated CSV answers and generated paths; checked the clean, up-to-date base.\n"
            "- Application build and tests were not run by this command.\n\n"
            "### Impact & Edge Cases\n"
            "- Included rows are authoritative; omitted tenants remain unchanged.\n"
        )
        args = [
            "gh",
            "pr",
            "create",
            "--repo",
            MINERVA_REPOSITORY,
            "--base",
            base,
            "--head",
            branch,
            "--title",
            title,
            "--body-file",
            "-",
        ]
        if draft:
            args.append("--draft")
        return _run(repo, *args, input_text=body)
    except (RuntimeError, OSError, ValueError) as error:
        preserved = f"; preserved {'pushed ' if pushed else ''}branch {branch}" if created else ""
        raise RuntimeError(f"Sync failed at {stage}{preserved}: {error}") from error
