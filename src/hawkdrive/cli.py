# src/hawkdrive/cli.py
import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer
from mashumaro.exceptions import ExtraKeysError, InvalidFieldValue, MissingField
from requests import RequestException
from rich.console import Console
from rich.text import Text

from hawkdrive.config import HawkDriveConfig, get_config, write_config
from hawkdrive.const import HD_GITIGNORE_BLOCK
from hawkdrive.github import GitHubRelease, get_release, cache_release_source, ReleaseCacheError
from hawkdrive.util import does_cache_exist

app = typer.Typer(help="Compile CAN databases and generate firmware bindings.")
console = Console(stderr=True)

@app.command()
def init(directory: Annotated[Path, typer.Argument(exists=True, file_okay=False, help="Directory where HawkDrive will be initalized."),] = Path(".")) -> None:
    """Initialize a repository with HawkDrive configurations."""
    config_path = directory / "hawkdrive.json"
    gitignore_path = directory / ".gitignore"

    latest_release: GitHubRelease = get_release()

    # Create config
    config = HawkDriveConfig(tag_name=latest_release.tag_name, node='')
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
) -> None:
    """Cache the pinned HawkDrive release for this repository."""
    try:
        config = get_config(directory)
        tag = config.tag_name

        console.print(Text.assemble(("HawkDrive sync", "bold cyan"), f"  {tag}"))

        if does_cache_exist(tag, directory):
            console.print("[bold green]OK[/]  Release already cached")
            return

        console.print("[cyan]Download[/]  Fetching the pinned release from GitHub")
        with console.status("Downloading and extracting release…", spinner="dots"):
            release = get_release(tag)
            cached_path = cache_release_source(release, directory)

        console.print(Text.assemble(("OK", "bold green"), f"  Cached at {cached_path}"))

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
def generate() -> None:
    """Generate C bindings from the pinned DBC release."""
    typer.echo("HawkDrive generate is wired up.")

def main() -> None:
    app()

