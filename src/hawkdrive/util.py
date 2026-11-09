from pathlib import Path
from urllib.parse import quote

def release_cache_path(tag_name: str, directory: Path) -> Path:
    """Returns the path of the cached release."""
    return directory / ".hawkdrive" / "releases" / quote(tag_name, safe="")

def does_cache_exist(tag_name: str, directory: Path) -> bool:
    return release_cache_path(tag_name, directory).is_dir()