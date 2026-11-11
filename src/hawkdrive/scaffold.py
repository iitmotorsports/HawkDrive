"""Install the shared scaffold from a cached HawkDrive release."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

LOCK_FILENAME = "hawkdrive-scaffold.lock.json"
_RESERVED = {".git", ".hawkdrive", "hawkdrive.json", LOCK_FILENAME}
_SHA256 = re.compile(r"[0-9a-f]{64}")
_VARIABLE = re.compile(r"\{\{\{([A-Z][A-Z0-9_]*)\}\}\}")


class ScaffoldError(ValueError):
    """The scaffold cannot be applied to this checkout."""


class ScaffoldConflictError(ScaffoldError):
    def __init__(self, conflicts: list[str]) -> None:
        self.conflicts = tuple(conflicts)
        paths = "\n".join(f"  {path}" for path in conflicts)
        super().__init__(
            f"Scaffold files differ from the last installed version:\n{paths}\n"
            "Review them or run hawkdrive sync --force to apply the release."
        )


@dataclass(frozen=True)
class ScaffoldResult:
    written: tuple[str, ...]
    removed: tuple[str, ...]
    unchanged: tuple[str, ...]


def apply_scaffold(
    directory: Path,
    release_directory: Path,
    tag_name: str,
    *,
    variables: dict[str, str] | None = None,
    force: bool = False,
) -> ScaffoldResult:
    """Apply the cached scaffold and record the installed file hashes."""
    variables = variables or {}
    directory = directory.resolve(strict=True)
    if not directory.is_dir():
        raise ScaffoldError(f"Expected a repository directory: {directory}")

    source_dir = release_directory / "scaffold"
    if source_dir.is_symlink() or not source_dir.is_dir():
        raise ScaffoldError(f"Release {tag_name} has no scaffold directory: {source_dir}")

    lock_path = directory / LOCK_FILENAME
    previous = _read_lock(lock_path)
    incoming: dict[str, bytes] = {}

    for source in sorted(source_dir.rglob("*")):
        if source.is_symlink():
            raise ScaffoldError(f"Scaffold source is a symlink: {source}")
        if source.is_dir():
            continue
        if not source.is_file():
            raise ScaffoldError(f"Scaffold source is not a regular file: {source}")
        name = source.relative_to(source_dir).as_posix()
        incoming[name] = _render_template(source.read_bytes(), variables)

    hashes = {name: _hash(data) for name, data in incoming.items()}
    writes: dict[str, Path] = {}
    removals: dict[str, Path] = {}
    unchanged: list[str] = []
    conflicts: list[str] = []

    # Check every destination before making any changes.
    for name in sorted(previous.keys() | incoming.keys()):
        target = _resolve_target(directory, name)
        current_hash = _file_hash(target)
        incoming_hash = hashes.get(name)

        if current_hash == incoming_hash:
            if incoming_hash is not None:
                unchanged.append(name)
            continue

        if current_hash is not None and current_hash != previous.get(name):
            conflicts.append(name)

        if incoming_hash is None:
            removals[name] = target
        else:
            writes[name] = target

    if conflicts and not force:
        raise ScaffoldConflictError(conflicts)

    for name, target in writes.items():
        _replace_file(target, incoming[name])

    for target in removals.values():
        target.unlink(missing_ok=True)

    lock_data = {"tag_name": tag_name, "files": hashes}
    lock_bytes = (json.dumps(lock_data, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if _file_hash(lock_path) != _hash(lock_bytes):
        _replace_file(lock_path, lock_bytes)

    return ScaffoldResult(tuple(writes), tuple(removals), tuple(unchanged))


def _resolve_target(directory: Path, name: str) -> Path:
    """Validate a scaffold path and resolve it inside the module directory."""
    relative = PurePosixPath(name)
    if (
        not relative.parts
        or relative.is_absolute()
        or ".." in relative.parts
        or any(":" in part or "\\" in part for part in relative.parts)
        or relative.as_posix() != name
        or relative.parts[0].lower() in _RESERVED
    ):
        raise ScaffoldError(f"Invalid scaffold destination: {name!r}")

    target = directory
    for part in relative.parts:
        target = target / part
        if target.is_symlink():
            raise ScaffoldError(f"Scaffold destination crosses a symlink: {target}")

    if not target.resolve().is_relative_to(directory):
        raise ScaffoldError(f"Scaffold destination leaves the repository: {target}")
    return target


def _read_lock(path: Path) -> dict[str, str]:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ScaffoldError(f"Expected a regular scaffold lock file: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except ValueError as exc:
        raise ScaffoldError(f"Invalid scaffold lock: {path}") from exc

    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, dict) or any(
        not isinstance(digest, str) or _SHA256.fullmatch(digest) is None
        for digest in files.values()
    ):
        raise ScaffoldError(f"Invalid scaffold lock: {path}")
    return files

def _render_template(data: bytes, variables: dict[str, str]) -> bytes:
    if b"{{{" not in data:
        return data

    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ScaffoldError("Template contains invalid UTF-8") from exc

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)

        if name not in variables:
            raise ScaffoldError(f"Unknown scaffold variable: {name}")

        return variables[name]

    return _VARIABLE.sub(replace, content).encode("utf-8")

def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_hash(path: Path) -> str | None:
    if path.is_symlink():
        raise ScaffoldError(f"Expected a regular file: {path}")
    try:
        if path.exists() and not path.is_file():
            raise ScaffoldError(f"Expected a regular file: {path}")
        return _hash(path.read_bytes())
    except FileNotFoundError:
        return None


def _replace_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".hawkdrive-", dir=path.parent) as staging:
        temp_path = Path(staging) / path.name
        temp_path.write_bytes(data)
        temp_path.replace(path)