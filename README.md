# Minerva CLI

Internal tooling for converting Google Forms response CSVs into Minerva tenant
configuration. Maintained in the private `HackOSS-Minerva/minerva-cli`
repository; Minerva does not install or invoke this project.

## Setup

Use Python 3.12 and uv. Git and an authenticated GitHub account are needed to clone
this private repository. Publishing requires GitHub CLI (`gh`) and uses each operator's configured Git
name/email and existing `gh` authentication; no shared credentials are configured.

```sh
git clone https://github.com/HackOSS-Minerva/minerva-cli.git
cd minerva-cli
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
uv run minerva-cli tenants sync /path/to/responses.csv --repo /path/to/minerva --dry-run
uv run minerva-cli tenants sync /path/to/responses.csv --repo /path/to/minerva
```

Use `--draft` for a draft PR. To target an unmerged integration branch, check out
that branch in Minerva, update it, then pass `--base fardinzam/tenant-sync-integration`.
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
10 description files. The judge-orientation opening/closing schedule remains in
configuration but has no Markdown description. Generated JSON uses
two-space indentation and compacts schedule pairs when the complete line fits
Minerva's default 80-column formatting. Unchanged JSON retains its existing bytes.

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

## Build

```sh
uv sync --locked
uv build
```

There are no runtime Python dependencies. Do not commit downloaded responses,
credentials, planning artifacts, or build outputs. Keep local environments and
caches excluded from Git.
