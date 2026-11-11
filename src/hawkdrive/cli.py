# src/hawkdrive/cli.py
import json
import shutil
import sys
from dataclasses import replace
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Annotated

import questionary
import typer
from mashumaro.exceptions import ExtraKeysError, InvalidFieldValue, MissingField
from packaging.version import Version
from requests import RequestException
from rich.console import Console
from rich.text import Text

from hawkdrive import dbc
from hawkdrive.config import HawkDriveConfig, get_config, write_config
from hawkdrive.const import HD_GITIGNORE_BLOCK, HAWKDRIVE_GIT_URL
from hawkdrive.github import GitHubRelease, get_release, cache_release_source, ReleaseCacheError
from hawkdrive.scaffold import apply_scaffold
from hawkdrive.util import release_cache_path, shell_command, pipx_scope

app = typer.Typer(help="Compile CAN databases and generate firmware bindings.")
app.add_typer(dbc.app, name="dbc")
console = Console(stderr=True)



@app.command()
def init(directory: Annotated[Path, typer.Argument(exists=True, file_okay=False, help="Directory where HawkDrive will be initalized."),] = Path("."), node: Annotated[
        str | None,
        typer.Option("--node", "-n", help="Node name to save in hawkdrive.json."),
] = None, vehicle: Annotated[str | None, typer.Option("--vehicle", "-v", help="Vehicle name to save in hawkdrive.json."),
] = None) -> None:
    """Initialize a repository with HawkDrive configurations."""
    console.print(Text.assemble(("HawkDrive init", "bold cyan")))

    config_path = directory / "hawkdrive.json"
    gitignore_path = directory / ".gitignore"

    if config_path.exists():
        typer.echo(f"Config already exists at {config_path}", err=True)
        raise typer.Exit(code=1)

    if node is None:
        if not sys.stdin.isatty():
            typer.echo("Pass --node when running init noninteractively.", err=True)
            raise typer.Exit(code=2)

    if vehicle is None:
        if not sys.stdin.isatty():
            typer.echo("Pass --vehicle when running init noninteractively.", err=True)
            raise typer.Exit(code=2)

    node = questionary.text("Node name").ask()

    if node is None:
        raise typer.Exit(code=130)

    node = node.strip()
    if not node:
        typer.echo("Node name cannot be empty.", err=True)
        raise typer.Exit(code=2)

    vehicle = questionary.text("Vehicle name").ask()

    if vehicle is None:
        raise typer.Exit(code=130)

    vehicle = vehicle.strip()
    if not vehicle:
        typer.echo("Vehicle name cannot be empty.", err=True)
        raise typer.Exit(code=2)

    latest_release: GitHubRelease = get_release()

    # Create config
    config = HawkDriveConfig(tag_name=latest_release.tag_name, node=node, vehicle=vehicle)
    try:
        with config_path.open("x", encoding="utf-8") as config_file:
            config_file.write(config.json_text())
    except FileExistsError:
        typer.echo(f"Config already exists at {config_path}", err=True)
        raise typer.Exit(code=1) from None
    except OSError as exc:
        typer.echo(f"Could not create {config_path}: {exc}", err=True)
        raise typer.Exit(code=1) from None

    # Add hawkdrive cache to gitignore
    if gitignore_path.exists() and gitignore_path.is_file():
        with gitignore_path.open("r+", encoding="utf-8") as gitignore_file:
            hawkdrive_block_detected: bool = False
            for line in gitignore_file:
                if line.startswith(".hawkdrive"):
                    hawkdrive_block_detected = True
            if not hawkdrive_block_detected:
                gitignore_file.write(HD_GITIGNORE_BLOCK)

    typer.secho(f"Created {config_path.resolve()}", fg=typer.colors.GREEN)

@app.command()
def pull(directory: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            help="Repository directory containing the HawkDrive cache.",
        ),
    ] = Path("."),
) -> None:
    """Pull the last HawkDrive release from Github."""
    console.print(Text.assemble(("HawkDrive pull", "bold cyan")))

    try:
        config: HawkDriveConfig = (get_config(directory))
        console.print("[cyan]Download[/]  Checking for the latest release from GitHub")
        latest_release: GitHubRelease = get_release()

        if latest_release.tag_name == config.tag_name:
            console.print(Text.assemble(
                ("OK", "bold yellow"),
                "  HawkDrive is already pinned to ",
                (latest_release.tag_name, "bold cyan"),
                ", the latest release.",
            ))
            return

        write_config(replace(config, tag_name=latest_release.tag_name), directory)
    except (
        OSError,
        ValueError,
        ExtraKeysError,
        InvalidFieldValue,
        MissingField,
        RequestException,
    ) as exc:
        console.print(Text.assemble(("Pull failed", "bold red"), f"  {exc}"))
        raise typer.Exit(code=1) from None

    console.print(Text.assemble(
        ("OK", "bold green"),
        "  Release pinned to ",
        (latest_release.tag_name, "bold cyan"),
        "\n    Run ",
        ("hawkdrive sync", "bold cyan"),
        " to apply this release to your checkout.",
    ))

@app.command()
def clean(
    directory: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            help="Repository directory containing the HawkDrive cache.",
        ),
    ] = Path("."),
) -> None:
    """Remove cached HawkDrive releases from this repository."""
    cache_root = directory / ".hawkdrive"
    releases_dir = cache_root / "releases"

    console.print(Text.assemble(("HawkDrive clean", "bold cyan"), f"  {directory.resolve()}"))

    try:
        if cache_root.is_symlink() or releases_dir.is_symlink():
            raise OSError(f"Refusing to clean a symlinked cache: {releases_dir}")

        if not releases_dir.exists():
            console.print("[bold green]OK[/]  No cached releases to remove")
            return

        console.print(Text.assemble(("Remove", "cyan"), f"  {releases_dir}"))
        shutil.rmtree(releases_dir)

    except OSError as exc:
        console.print(Text.assemble(("Clean failed", "bold red"), f"  {exc}"))
        raise typer.Exit(code=1) from None

    console.print("[bold green]OK[/]  Release cache cleared")

@app.command()
def sync(
    directory: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            help="Repository directory containing hawkdrive.json.",
        ),
    ] = Path("."),
    force: Annotated[
        bool,
        typer.Option("--force", help="Apply the scaffold despite local file conflicts."),
    ] = False,
) -> None:
    """Cache the pinned HawkDrive release and apply its scaffold."""
    try:
        config = get_config(directory)
        tag = config.tag_name
        cached_path = release_cache_path(tag, directory)

        console.print(Text.assemble(("HawkDrive sync", "bold cyan"), f"  {tag}"))

        if cached_path.is_dir():
            console.print("[bold green]OK[/]  Release already cached")
        else:
            console.print("[cyan]Download[/]  Fetching the pinned release from GitHub")
            with console.status("Downloading and extracting release…", spinner="dots"):
                release = get_release(tag)
                cached_path = cache_release_source(release, directory)

            console.print(Text.assemble(("OK", "bold green"), f"  Cached at {cached_path}"))

        console.print("[cyan]Scaffold[/]  Applying shared files")
        result = apply_scaffold(directory, cached_path, tag, force=force, variables={
            "NODE": config.node,
            "VEHICLE": config.vehicle,
        })

        for path in result.written:
            console.print(Text.assemble(("  Write ", "green"), path))

        for path in result.removed:
            console.print(Text.assemble(("  Remove ", "yellow"), path))

        summary = (
            f"  Scaffold synced · {len(result.written)} written, "
            f"{len(result.removed)} removed, {len(result.unchanged)} unchanged"
        )
        console.print(Text.assemble(("OK", "bold green"), summary))

    except (
        OSError,
        ValueError,
        ExtraKeysError,
        InvalidFieldValue,
        MissingField,
        RequestException,
        ReleaseCacheError,
    ) as exc:
        console.print(Text.assemble(("Sync failed", "bold red"), f"  {exc}"))
        raise typer.Exit(code=1) from None

@app.command()
def upgrade() -> None:
    """Check for a newer HawkDrive CLI and show how to install it."""
    console.print("[bold cyan]HawkDrive upgrade[/]")

    try:
        installed = distribution("hawkdrive")
        origin = json.loads(installed.read_text("direct_url.json") or "{}")

        if origin.get("dir_info", {}).get("editable"):
            console.print("[cyan]Editable install[/]  From your HawkDrive checkout, run:")
            console.print(Text("  git pull --ff-only\n  uv sync"))
            return

        latest_tag = get_release().tag_name
        if Version(latest_tag) <= Version(installed.version):
            console.print(Text.assemble(
                ("OK", "bold green"),
                f"  No newer stable release. Installed {installed.version}; "
                f"latest stable is {latest_tag}.",
            ))
            return

        package_spec = f"{HAWKDRIVE_GIT_URL}@{latest_tag}"
        prefix = Path(sys.prefix).resolve()
        pipx_metadata = prefix / "pipx_metadata.json"
        command = None

        if pipx_metadata.is_file():
            metadata = json.loads(pipx_metadata.read_text(encoding="utf-8"))
            main_package = metadata.get("main_package", {})

            if main_package.get("package") == "hawkdrive" and prefix.name == "hawkdrive":
                scope = pipx_scope(prefix)
                if scope == "user":
                    command = ["pipx", "install", "--force", package_spec]
                elif scope == "global":
                    command = ["sudo", "pipx", "install", "--global", "--force", package_spec]

        elif (installed.read_text("INSTALLER") or "").strip() == "pip":
            command = [
                sys.executable, "-m", "pip", "install", "--upgrade", package_spec,
            ]

    except (OSError, ValueError, PackageNotFoundError, RequestException) as exc:
        console.print(Text.assemble(("Upgrade check failed", "bold red"), f"  {exc}"))
        raise typer.Exit(code=1) from None

    console.print(Text.assemble(
        ("Update available", "bold yellow"),
        f"  {installed.version} → {latest_tag}",
    ))

    if command is None:
        console.print(Text(
            f"Could not determine an upgrade command for {sys.prefix}.\n"
            "Install the new release using the tool that installed this copy."
        ))
        return

    console.print(Text.assemble(
        "  Run: ",
        (shell_command(command), "bold cyan"),
    ))

def main() -> None:
    app()

