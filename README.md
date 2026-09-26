# Minerva tenant sync

Internal tooling for converting Google Forms response CSVs into Minerva tenant
configuration. Maintained in the private `HackOSS-Minerva/minerva-tenant-sync`
repository; Minerva does not install or invoke this project.

## Current status

CSV parsing and validation are implemented. File generation, the command-line
entrypoint and Git/PR automation are not implemented yet. Parsing does not write
tenant files or make network requests.

## Setup

Use Python 3.12 and uv. Git and an authenticated GitHub account are needed to clone
this private repository. Future publishing uses each operator's configured Git
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
4. Once the CLI is implemented, run its dry-run against that checkout, inspect the
   planned changes, then run normal sync and review the resulting PR. Runnable CLI
   examples will be added with that implementation.

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
Description text is preserved exactly by the parser. File rendering will own MDX
newline normalization. URL validation rejects embedded control characters, an
intentional tightening of the old importer. Compatibility cases cover common
inputs; this is not a comprehensive RFC/WHATWG validation library.

## Tests

```sh
uv run --locked python -m unittest discover -s tests -v
```

Tests use synthetic responses and temporary local files, without Google/GitHub
credentials, Minerva dependencies or downloaded tenant data. There are no runtime
Python dependencies. Do not commit downloaded responses, credentials or planning
artifacts. Keep local environments and caches excluded from Git.
