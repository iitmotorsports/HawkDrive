import json
import re
from pathlib import Path, PureWindowsPath
from tempfile import TemporaryDirectory
from typing import Any

import typer
from cantools.database import UnsupportedDatabaseFormatError, load_string
from cantools.database.can import Database, Message, Node

app = typer.Typer(help="Compile and verify vehicle DBCs.", no_args_is_help=True)

MANIFEST = "hawkdrive-dbc.json"
OUTPUT_DIR = "compiled"
DBC_ENCODING = "cp1252"


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{label} must be a nonempty object.")
    return value


def _source_path(dbc_root: Path, source: str) -> Path:
    relative = Path(source)
    if (
        relative.is_absolute()
        or PureWindowsPath(source).drive
        or "\\" in source
        or ".." in relative.parts
        or relative.suffix.lower() != ".dbc"
    ):
        raise ValueError(f"Expected a relative .dbc path under dbc/: {source!r}")

    path = (dbc_root / relative).resolve()
    if not path.is_relative_to(dbc_root) or not path.is_file():
        raise ValueError(f"Missing or invalid DBC source: {source!r}")
    return path


def _render_vehicle(dbc_root: Path, vehicle: str, sources: list[str]) -> bytes:
    messages: list[Message] = []
    nodes: dict[str, Node] = {}
    frame_origins: dict[tuple[bool, int], str] = {}
    name_origins: dict[str, str] = {}

    for source in sources:
        path = _source_path(dbc_root, source)
        try:
            database = load_string(
                path.read_text(encoding=DBC_ENCODING),
                database_format="dbc",
                strict=True,
            )
        except UnsupportedDatabaseFormatError as exc:
            raise ValueError(f"{vehicle}/{source}: {exc}") from exc

        for node in database.nodes:
            nodes.setdefault(node.name, node)

        for message in database.messages:
            origin = f"{vehicle}/{source} ({message.name})"
            frame = (message.is_extended_frame, message.frame_id)

            if frame in frame_origins:
                kind = "extended" if message.is_extended_frame else "standard"
                raise ValueError(
                    f"Duplicate {kind} CAN ID {message.frame_id:#x}: "
                    f"{frame_origins[frame]} and {origin}"
                )

            if message.name in name_origins:
                raise ValueError(
                    f"Duplicate message name {message.name!r}: "
                    f"{name_origins[message.name]} and {origin}"
                )

            frame_origins[frame] = origin
            name_origins[message.name] = origin
            messages.append(message)

    messages.sort(key=lambda message: (message.frame_id, message.is_extended_frame))
    merged = Database(
        messages=messages,
        nodes=sorted(nodes.values(), key=lambda node: node.name),
        version="1.0.0",
        strict=True,
    )
    return merged.as_dbc_string().replace("\r\n", "\n").encode(DBC_ENCODING)


def render_outputs(root: Path) -> dict[str, bytes]:
    manifest = _object(
        json.loads((root / MANIFEST).read_text(encoding="utf-8")), MANIFEST
    )
    version = manifest.get("schema_version")
    if type(version) is not int or version != 1:
        raise ValueError(f"{MANIFEST} requires schema_version 1.")

    vehicles = _object(manifest.get("vehicles"), "vehicles")
    dbc_root = (root / "dbc").resolve()
    outputs: dict[str, bytes] = {}

    for vehicle, config in sorted(vehicles.items()):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", vehicle):
            raise ValueError(f"Invalid vehicle ID: {vehicle!r}")

        filename = f"{vehicle.lower()}.dbc"
        if filename in outputs:
            raise ValueError(f"Multiple vehicles map to {filename}.")

        label = f"vehicles.{vehicle}"
        sources = _object(config, label).get("sources")
        if (
            not isinstance(sources, list)
            or not sources
            or any(not isinstance(source, str) or not source.strip() for source in sources)
        ):
            raise ValueError(f"{label}.sources must be a nonempty list of paths.")

        outputs[filename] = _render_vehicle(dbc_root, vehicle, sources)

    return outputs

@app.command("compile")
def compile_command() -> None:
    """Write one merged DBC per vehicle."""
    root = Path.cwd()
    output_dir = root / OUTPUT_DIR

    try:
        outputs = render_outputs(root)
        output_dir.mkdir(exist_ok=True)
        with TemporaryDirectory(dir=output_dir) as temp:
            stage = Path(temp)
            for filename, data in outputs.items():
                (stage / filename).write_bytes(data)

            for filename in outputs:
                (stage / filename).replace(output_dir / filename)
                typer.echo(f"WROTE  {OUTPUT_DIR}/{filename}")
    except (OSError, ValueError) as exc:
        typer.echo(f"DBC compile failed: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("verify")
def verify_command() -> None:
    """Check that the compiled DBCs match the current sources."""
    root = Path.cwd()
    output_dir = root / OUTPUT_DIR
    needs_compile = False

    try:
        outputs = render_outputs(root)
        for filename, expected in outputs.items():
            path = output_dir / filename
            try:
                actual = path.read_bytes()
            except FileNotFoundError:
                typer.echo(f"MISSING  {OUTPUT_DIR}/{filename}", err=True)
                needs_compile = True
            else:
                if actual != expected:
                    typer.echo(f"STALE    {OUTPUT_DIR}/{filename}", err=True)
                    needs_compile = True

        obsolete = sorted(
            path.name for path in output_dir.glob("*.dbc") if path.name not in outputs
        )
    except (OSError, ValueError) as exc:
        typer.echo(f"DBC verify failed: {exc}", err=True)
        raise typer.Exit(1) from exc

    if needs_compile:
        typer.echo("Run 'hd dbc compile' and commit the updated DBCs.", err=True)
    for filename in obsolete:
        typer.echo(f"OBSOLETE {OUTPUT_DIR}/{filename} (remove this file)", err=True)
    if needs_compile or obsolete:
        raise typer.Exit(1)

    typer.echo(f"OK  {len(outputs)} vehicle DBC(s) up to date.")