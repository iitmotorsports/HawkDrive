# HawkDrive

HawkDrive is the control system for **Illinois Tech Motorsports’ Formula SAE Electric car**. This repository holds shared resources for the car’s control modules and the `hawkdrive` command-line tool that keeps their firmware repositories in sync.

## Features

- **Pin a release per module.** Track the HawkDrive release and CAN node name in `hawkdrive.json`.
- **Share project files.** Sync common C code, lint settings, and pre-commit configuration across firmware repositories.
- **Protect local edits.** Sync reports conflicts before overwriting locally modified scaffold files.
- **Work offline after the first sync.** HawkDrive caches release sources locally and reuses them on subsequent syncs.

DBC-based CAN code generation is in development.

## Install

HawkDrive runs on **macOS, Linux, and Windows**. You’ll need **Python 3.11 or newer** and **Git**.

### pip

Install HawkDrive into a virtual environment.

**macOS and Linux**

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install "git+https://github.com/iitmotorsports/HawkDrive.git"
hawkdrive --help
```

**Windows PowerShell**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install "git+https://github.com/iitmotorsports/HawkDrive.git"
hawkdrive --help
```

Activate the environment again when you open a new terminal. To install a specific CLI release, append `@<tag>` to the Git URL.

### pipx

Use pipx if you want `hawkdrive` on your `PATH` without activating a virtual environment. Follow the [pipx installation guide](https://pipx.pypa.io/latest/how-to/install-pipx.html) for your OS, then run:

```sh
pipx install "git+https://github.com/iitmotorsports/HawkDrive.git"
hawkdrive --help
```

## Quick start

From your firmware repository:

```sh
hawkdrive init --node PDM
hawkdrive sync
```

Replace `PDM` with your module’s CAN node name, or omit `--node` to choose it interactively. Commit `hawkdrive.json`, `hawkdrive-scaffold.lock.json`, and the installed scaffold files so teammates can reproduce the setup.

To move the module to the latest stable HawkDrive release:

```sh
hawkdrive pull
hawkdrive sync
```

`pull` updates the release pin. `sync` applies that release to your checkout.

## Develop with uv

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then clone the repo and set up the development environment:

```sh
git clone https://github.com/iitmotorsports/HawkDrive.git
cd HawkDrive
uv sync
uv run hawkdrive --help
```

`uv sync` installs the locked dependencies and an editable copy of HawkDrive. Use `uv run hawkdrive` to try changes as you work. To test against a separate firmware checkout, pass its path:

```sh
uv run hawkdrive init ../PDM --node PDM
uv run hawkdrive sync ../PDM
```