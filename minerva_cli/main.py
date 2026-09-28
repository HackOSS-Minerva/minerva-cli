"""Tenant configuration commands for Minerva."""

import logging
from pathlib import Path
from typing import Annotated

import typer

from . import constants
from .generate import build_plan
from .git import preflight, publish, validate_checkout
from .tenants import parse_tenants

logger = logging.getLogger(__name__)

app = typer.Typer(no_args_is_help=True, add_completion=False)
tenants = typer.Typer(no_args_is_help=True)
app.add_typer(tenants, name="tenants", help="Manage tenant configuration.")


@tenants.command()
def sync(
    csv: Annotated[Path, typer.Argument(help="Google Forms response CSV.")],
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show changes without writing or fetching.")
    ] = False,
    draft: Annotated[bool, typer.Option("--draft", help="Create a draft PR.")] = False,
) -> None:
    """Generate a tenant configuration PR from CSV."""
    try:
        parsed = parse_tenants(csv.resolve())
        repo = constants.MINERVA_CHECKOUT.resolve()
        validate_checkout(repo)
        if not dry_run:
            preflight(repo)
        plan = build_plan(repo, parsed)
        logger.info("Processed tenants: %d", len(plan.processed_slugs))
        if not plan.changes:
            logger.info("No changes; no branch or PR created.")
        elif dry_run:
            logger.info("Dry-run; files that would change:")
            for path in plan.changes:
                logger.info("  %s", path)
        else:
            logger.info("Created PR: %s", publish(repo, plan, draft=draft))
    except (ValueError, OSError, RuntimeError) as error:
        logger.error("%s", error)
        raise typer.Exit(code=1) from error


def main() -> None:
    logging.basicConfig(level=logging.INFO, format=constants.LOG_FORMAT)
    app()


if __name__ == "__main__":
    main()
