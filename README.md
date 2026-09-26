# Minerva tenant sync

Internal tooling for converting Google Forms response CSVs into Minerva tenant
configuration. Maintained in the private `HackOSS-Minerva/minerva-tenant-sync`
repository; Minerva does not install or invoke this project.

## Current status

CSV parsing, generation, dry-run and Git/PR automation are implemented. Minerva
must already contain the generated registry integration before this command can
run. That separate integration is not installed yet. A pull-request test workflow
is included; its first GitHub run awaits publication.

## Setup

Use Python 3.12 and uv. Git and an authenticated GitHub account are needed to clone
this private repository. Publishing requires GitHub CLI (`gh`) and uses each operator's configured Git
name/email and existing `gh` authentication; no shared credentials are configured.

```sh
git clone https://github.com/HackOSS-Minerva/minerva-tenant-sync.git
cd minerva-tenant-sync
uv sync
```

An organization administrator must grant the relevant GitHub team write access.
Maintainers also need editor access to the Google Form and response sheet.
Both sharing steps are pending manual setup before team use.

## Operator workflow

1. Clone this repository and run `uv sync`.
2. Download the linked Google Forms response tab as CSV. Keep the download outside
   tracked repositories; do not rearrange linked response rows.
3. Prepare a clean, up-to-date local Minerva checkout on `main`. Preserve unrelated
   work first, then use `git pull --ff-only`. Do not reset or automatically stash it.
4. From the CLI checkout, run a dry-run, inspect the paths, then publish and review
   the resulting PR:

```sh
uv run python -m minerva_cli tenants sync /path/to/responses.csv --repo /path/to/minerva --dry-run
uv run python -m minerva_cli tenants sync /path/to/responses.csv --repo /path/to/minerva
```

Use `--draft` for a draft PR. To target an unmerged integration branch, check out
that branch in Minerva, update it, then pass `--base tenant-sync/registry-integration`.
The default base is `main`. Relative CSV paths are resolved from your current
directory, not from the Minerva checkout. Quote paths containing spaces.

Dry-run performs only local reads; it does not fetch, authenticate, write files or
change Git state. Normal mode requires a clean checkout (including untracked files),
fetches the base from `origin`, and requires local HEAD to equal that fetched base.
It checks `user.name`, `user.email` and `gh auth status` without changing credentials.
It never automatically switches the base, resets or stashes work.

A changed import creates `tenant-sync/<UTC timestamp>`, writes and commits only
planned tenant paths, pushes the branch, then opens a PR against the selected base.
PR creation explicitly selects origin's push repository, overriding any gh default.
An unchanged import creates no branch, commit or PR; normal preflight still runs.
Failures return a nonzero exit code with the failed stage and preserved branch.
If PR creation fails after push, the remote branch remains. Inspect that state
before retrying; the command does not retry or roll back partial work. Application
builds/tests are not automatically run or claimed in the generated PR.

Current integration prerequisites: the `tenants/generated.ts` registry must be
imported by `hooks/get-tenant.ts`, and every existing tenant must have its required
description files (including `judge-orientation.mdx`). The current main snapshot
lacks those orientation files; this tool does not silently add them to omitted
tenants. Generated JSON uses the planned standard-library indentation, which can
differ from Minerva Prettier's compact array formatting.

The parser can currently be called from Python:

```python
from pathlib import Path
from minerva_cli.tenants import parse_tenants

tenants = parse_tenants(Path("/path/to/responses.csv"))
```

Every included tenant row is authoritative; blank optional values clear values
rather than inheriting old configuration. Tenants omitted from the input are not
deletion requests. All nonempty rows are validated together; duplicate tenant IDs,
missing/unknown/duplicate question headers and invalid answers fail the import.
Error row numbers count CSV records, including the header, not physical lines
inside multiline answers. `Timestamp` is optional metadata and is ignored.

Blank optional event settings are omitted; blank links remain empty strings.
Description text is preserved exactly by the parser. File rendering owns MDX
newline normalization. URL validation rejects embedded control characters, an
intentional tightening of the old importer. Compatibility cases cover common
inputs; this is not a comprehensive RFC/WHATWG validation library.

## Tests

Pull requests run this suite on Ubuntu with Python 3.12 and uv 0.11.23. Run the same
commands locally:

```sh
uv sync --locked
uv run --locked python -m unittest discover -s tests -v
```

Tests use synthetic responses and temporary local files, without Google/GitHub
credentials, Minerva dependencies or downloaded tenant data. There are no runtime
Python dependencies. Do not commit downloaded responses, credentials or planning
artifacts. Keep local environments and caches excluded from Git.
