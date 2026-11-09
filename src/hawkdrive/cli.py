# src/hawkdrive/cli.py
import json
from pathlib import Path
from typing import Annotated

import typer

from hawkdrive.const import HD_GITIGNORE_BLOCK

app = typer.Typer(help="Compile CAN databases and generate firmware bindings.")

# Register compile, generateOkay, check, and init here.

@app.command()
def init(directory: Annotated[Path, typer.Argument(exists=True, file_okay=False, help="Directory where HawkDrive will be initalized."),] = Path(".")) -> None:
    """Initialize a repository with HawkDrive configurations."""
    config_path = directory / "hawkdrive.json"
    gitignore_path = directory / ".gitignore"
    config = {
        "schema_version": 1,
    }
    try:
        with config_path.open("x", encoding="utf-8") as config_file:
            json.dump(config, config_file, indent=2)
            config_file.write("\n")
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
def generate() -> None:
    """Generate C bindings from the pinned DBC release."""
    typer.echo("HawkDrive generate is wired up.")

def main() -> None:
    app()

