# Minerva CLI

Generate Minerva tenant configuration and a GitHub PR from a Google Forms CSV.

## Prerequisites

Python 3.12, uv, Git, GitHub CLI (`gh`), Minerva write access, and access to the
response sheet. Publishing uses your configured Git identity and `gh` login.

## Setup

Run from the folder where you keep your repositories; skip clones you already have.

```sh
git clone https://github.com/HackOSS-Minerva/minerva.git
git clone https://github.com/HackOSS-Minerva/minerva-cli.git
cd minerva-cli
uv sync
gh auth login
```

The CLI expects the Minerva checkout at `../minerva`, relative to the CLI repository:

```text
parent-folder/
├── minerva/
└── minerva-cli/
```

For another layout, set `MINERVA_CHECKOUT` in `minerva_cli/constants.py` to an
absolute path. Use the editable installation created by `uv sync`.

## Usage

Download the Form response sheet as CSV outside both repositories.

Use the Form's separate Date and Time questions for each opening, closing, and
event timestamp. All times are California time (automatic PST/PDT). Choose another
time if a daylight-saving transition makes it repeated or nonexistent.
Maintainers fill in `Tenant ID` in the Sheet before exporting. Keep the Sheet's
date/time column formats as `yyyy-mm-dd` and `HH:mm:ss`; US-native date and AM/PM
time exports are also accepted. Older combined date/time CSV exports must be re-exported.

From `minerva-cli`, prepare a clean Minerva checkout on `main` (preserve existing work first):

```sh
git -C ../minerva switch main
git -C ../minerva pull --ff-only
uv run minerva-cli tenants sync "/path/to/responses.csv" --dry-run
uv run minerva-cli tenants sync "/path/to/responses.csv" --draft
```

Dry-run only reads files. The second command **commits, pushes, and opens a draft PR**
against `HackOSS-Minerva/minerva:main`; omit `--draft` for a ready PR.
Included Form fields are authoritative; omitted tenants remain unchanged.
Existing `heart` and `event.openOffset` values stay unchanged; new tenants use an
empty heart and no opening override.
Failures preserve any created branch. Logs go to stderr; inspect preserved work before retrying.
For a custom checkout location, use that path in the Git commands above.

```sh
uv run minerva-cli tenants sync --help
```

## Development

```sh
uv sync --locked
uv run ruff format .
uv run ruff format --check .
uv run ruff check .
uv build
```

CI runs format, lint, and build checks on PRs and `main` pushes.
Do not commit CSV exports, credentials, local environments, or build outputs.
