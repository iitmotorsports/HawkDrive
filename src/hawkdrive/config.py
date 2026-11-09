import json
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from tempfile import NamedTemporaryFile

from mashumaro.mixins.json import DataClassJSONMixin

from hawkdrive.const import CONFIG_FILENAME


@dataclass(kw_only=True)
class HawkDriveConfig(DataClassJSONMixin):
    tag_name: str
    node: str
    schema_version: int = 1

    def json_text(self) -> str:
        return self.to_json(encoder=partial(json.dumps, indent=2)) + "\n"


def get_config(directory: Path) -> HawkDriveConfig:
    config_path = directory / CONFIG_FILENAME
    return HawkDriveConfig.from_json(config_path.read_text(encoding="utf-8"))

def write_config(
    config: HawkDriveConfig,
    directory: Path = Path("."),
) -> Path:
    """Save the config, replacing an existing config if present."""
    config_path = directory / CONFIG_FILENAME
    temp_path: Path | None = None

    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=".hawkdrive-",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(config.json_text())

        temp_path.replace(config_path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    return config_path