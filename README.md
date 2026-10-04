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

Google Form responsed are updated in the linked Google Sheet. **Maintainers assign `Tenant ID` in the response Sheet.** Download a fresh CSV outside both repositories. Blank rows are skipped.

From `minerva-cli`, prepare a clean Minerva checkout on `main` (preserve existing work first):

```sh
git -C ../minerva switch main
git -C ../minerva pull --ff-only
uv run minerva-cli tenants sync "/path/to/responses.csv" --dry-run
uv run minerva-cli tenants sync "/path/to/responses.csv" --draft
```

- `--dry-run` only reads and validates the CSV, shows which Minerva files would change 
- `--draft` **commits, pushes, and opens a draft PR** against `HackOSS-Minerva/minerva:main`; omit `--draft` for a ready PR.

Included Form fields are authoritative; omitted tenants remain unchanged.

Validation errors are reported together by row and tenant before any files or Git
state change. Fix them in the Sheet or Form and export again. Invalid headers or broken CSV syntax stop parsing; date-order checks require valid dates and times.

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
