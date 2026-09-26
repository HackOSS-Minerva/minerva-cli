"""Run with uv run python -m minerva_cli tenants sync CSV --repo PATH."""

import argparse
import sys
from pathlib import Path

from .generate import build_plan
from .git import preflight, publish, validate_checkout
from .tenants import parse_tenants


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="minerva_cli")
    commands = parser.add_subparsers(dest="command", required=True)
    tenants = commands.add_parser("tenants", help="manage tenant configuration")
    actions = tenants.add_subparsers(dest="action", required=True)
    sync = actions.add_parser("sync", help="generate a tenant configuration PR from CSV")
    sync.add_argument("csv", type=Path)
    sync.add_argument("--repo", type=Path, required=True, help="existing Minerva checkout root")
    sync.add_argument("--dry-run", action="store_true", help="show changes without writing or fetching")
    sync.add_argument("--base", default="main", help="checked-out base branch (default: main)")
    sync.add_argument("--draft", action="store_true", help="create a draft PR")
    args = parser.parse_args(argv)
    try:
        parsed = parse_tenants(args.csv.resolve())
        repo = args.repo.resolve()
        validate_checkout(repo)
        if not args.dry_run:
            preflight(repo, args.base)
        plan = build_plan(repo, parsed)
        print("Processed tenants: " + (", ".join(plan.processed_slugs) or "none"))
        if not plan.changes:
            print("No changes; no branch or PR created.")
        elif args.dry_run:
            print("Dry-run; files that would change:")
            for path in plan.changes:
                print(f"  {path}")
        else:
            print(publish(repo, plan, args.base, args.draft))
        return 0
    except (ValueError, OSError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
