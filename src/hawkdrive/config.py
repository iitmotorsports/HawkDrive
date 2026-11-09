import json
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from mashumaro.mixins.json import DataClassJSONMixin

from hawkdrive.const import CONFIG_FILENAME


@dataclass(kw_only=True)
class HawkDriveConfig(DataClassJSONMixin):
    release: str
    node: str
    schema_version: int = 1

    def json_text(self) -> str:
        return self.to_json(encoder=partial(json.dumps, indent=2)) + "\n"


def get_config(directory: Path) -> HawkDriveConfig:
    config_path = directory / CONFIG_FILENAME
    return HawkDriveConfig.from_json(config_path.read_text(encoding="utf-8"))