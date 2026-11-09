import shlex
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

def release_cache_path(tag_name: str, directory: Path) -> Path:
    """Returns the path of the cached release."""
    return directory / ".hawkdrive" / "releases" / quote(tag_name, safe="")

def does_cache_exist(tag_name: str, directory: Path) -> bool:
    return release_cache_path(tag_name, directory).is_dir()

def pipx_scope(prefix: Path) -> str | None:
    """Identify which pipx installation owns the current environment."""
    scopes = ("user",) if sys.platform == "win32" else ("user", "global")

    for scope in scopes:
        command = ["pipx", "environment", "--value", "PIPX_LOCAL_VENVS"]
        if scope == "global":
            command.append("--global")

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            continue

        venvs_dir = result.stdout.strip()
        if venvs_dir and prefix.parent == Path(venvs_dir).resolve():
            return scope

    return None

def shell_command(args: list[str]) -> str:
    if sys.platform == "win32":
        # PowerShell needs & when the executable is quoted.
        quoted = ["'" + arg.replace("'", "''") + "'" for arg in args]
        return "& " + " ".join(quoted)

    return shlex.join(args)

