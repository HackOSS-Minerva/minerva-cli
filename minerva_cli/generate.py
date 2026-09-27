"""Deterministic tenant rendering and a single, Git-independent file writer."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .tenants import DESCRIPTIONS, SLUG, TenantInput


@dataclass
class SyncPlan:
    processed_slugs: list[str]
    changes: dict[Path, str]


def _safe_path(repo: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts or relative.parts[:1] != ("tenants",):
        raise ValueError(f"Unsafe tenant path: {relative}")
    target = repo
    for index, part in enumerate(relative.parts):
        target /= part
        if target.is_symlink():
            raise ValueError(f"Symlinked tenant path: {relative}")
        if index < len(relative.parts) - 1 and target.exists() and not target.is_dir():
            raise ValueError(f"Expected directory: {target}")
    if not target.resolve().is_relative_to(repo):
        raise ValueError(f"Tenant path escapes repository: {relative}")
    return target


def _read(repo: Path, relative: Path) -> bytes | None:
    target = _safe_path(repo, relative)
    if not target.exists():
        return None
    if not target.is_file():
        raise ValueError(f"Expected file: {relative}")
    return target.read_bytes()


def _mdx(content: str) -> str:
    if not content:
        return ""
    return content.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"


def _config_json(config: dict) -> str:
    content = json.dumps(config, ensure_ascii=False, indent=2, allow_nan=False) + "\n"

    def compact_schedule(match: re.Match) -> str:
        prefix, opens, closes, comma = match.groups()
        line = f"{prefix}[{opens}, {closes}]{comma}"
        return line if len(line) <= 80 else match.group(0)

    # Minerva's schedule pairs sit three levels deep. Match only timestamp arrays,
    # keeping json.dumps responsible for escaping and every other JSON value.
    return re.sub(
        r'(?m)^( {6}"[^"\n]+": )\[\n {8}("[0-9T:+.Z-]+"),\n'
        r' {8}("[0-9T:+.Z-]+")\n {6}\](,?)$',
        compact_schedule, content,
    )


def _identifier(slug: str) -> str:
    return "tenant_" + slug.replace("-", "_")


def _key(slug: str) -> str:
    return json.dumps(slug) if "-" in slug or slug[0].isdigit() else slug


def _registry(slugs: list[str]) -> str:
    lines = []
    descriptions = [(filename, Path(filename).stem.replace("-", "_"), group, export)
                    for _, filename, group, export in DESCRIPTIONS]
    for slug in slugs:
        identifier = _identifier(slug)
        prefix = f"@/tenants/{slug}"
        lines.append(f"import {identifier}_config from {json.dumps(f'{prefix}/{slug}.json')};")
        for filename, suffix, *_ in descriptions:
            lines.append(f"import {identifier}_{suffix} from {json.dumps(f'{prefix}/descriptions/{filename}')};")
    slug_line = f"export const tenantSlugs = {json.dumps(slugs)} as const;"
    lines += [""]
    if len(slug_line) <= 80:
        lines.append(slug_line)
    else:
        lines += ["export const tenantSlugs = [", *(f"  {json.dumps(slug)}," for slug in slugs), "] as const;"]
    lines += ["", "export const tenantConfigs = {"]
    for slug in slugs:
        lines.append(f"  {_key(slug)}: {_identifier(slug)}_config,")
    lines += ["};", "", "export const tenantContent = {"]
    for slug in slugs:
        identifier = _identifier(slug)
        lines.append(f"  {_key(slug)}: {{")
        for group in dict.fromkeys(item[2] for item in descriptions):
            lines.append(f"    {group}: {{")
            for _, suffix, section, export in descriptions:
                if section == group:
                    lines.append(f"      {export}: {identifier}_{suffix},")
            lines.append("    },")
        lines.append("  },")
    return "\n".join(lines + ["} as const;", ""])


def build_plan(repo: Path, tenants: list[TenantInput]) -> SyncPlan:
    """Plan all changes before any writes; callers supply validated tenant inputs."""
    repo = repo.resolve()
    root = _safe_path(repo, Path("tenants"))
    if not root.is_dir():
        raise ValueError(f"Missing tenants directory: {root}")
    slugs = set()
    for entry in root.iterdir():
        if entry.is_symlink():
            raise ValueError(f"Symlinked tenant path: {entry}")
        if entry.is_dir():
            if not SLUG.fullmatch(entry.name):
                raise ValueError(f"Invalid tenant directory: {entry.name}")
            slugs.add(entry.name)
    processed = [tenant.slug for tenant in tenants]
    if len(processed) != len(set(processed)) or any(not SLUG.fullmatch(slug) for slug in processed):
        raise ValueError("Invalid or duplicate tenant slug")
    slugs.update(processed)
    rendered = {}
    for tenant in sorted(tenants, key=lambda item: item.slug):
        base = Path("tenants") / tenant.slug
        relative = base / f"{tenant.slug}.json"
        content = _config_json(tenant.config)
        previous = _read(repo, relative)
        if previous is not None:
            try:
                existing = json.loads(previous)
                # Compare JSON values without Python's True == 1 coercion.
                if json.dumps(existing, sort_keys=True, allow_nan=False) == json.dumps(tenant.config, sort_keys=True, allow_nan=False):
                    content = previous.decode("utf-8")
            except (ValueError, UnicodeError) as error:
                raise ValueError(f"Invalid existing JSON: {relative}: {error}") from error
        rendered[relative] = content
        for _, filename, *_ in DESCRIPTIONS:
            rendered[base / "descriptions" / filename] = _mdx(tenant.descriptions[filename])
    # Every registry import must exist or be supplied by this plan.
    for slug in sorted(slugs):
        base = Path("tenants") / slug
        imports = [base / f"{slug}.json", *(base / "descriptions" / item[1] for item in DESCRIPTIONS)]
        for relative in imports:
            previous = _read(repo, relative)
            if relative not in rendered and previous is None:
                raise ValueError(f"Missing tenant import: {relative}")
    rendered[Path("tenants/generated.ts")] = _registry(sorted(slugs))
    changes = {relative: content for relative, content in rendered.items()
               if _read(repo, relative) != content.encode("utf-8")}
    return SyncPlan(sorted(processed), changes)


def apply_plan(repo: Path, plan: SyncPlan) -> None:
    """Validate every destination first, then write exact planned contents."""
    repo = repo.resolve()
    for relative in plan.changes:
        target = _safe_path(repo, relative)
        if target.exists() and not target.is_file():
            raise ValueError(f"Expected file: {relative}")
    for relative, content in plan.changes.items():
        target = _safe_path(repo, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8"))
