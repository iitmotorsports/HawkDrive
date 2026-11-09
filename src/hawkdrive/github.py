from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote
from zipfile import ZipFile, BadZipFile

import requests
from mashumaro import DataClassDictMixin

from hawkdrive.const import RELEASES_URL

@dataclass(frozen=True)
class GitHubReleaseAsset:
    id: int
    name: str
    digest: str | None = None


@dataclass(frozen=True)
class GitHubRelease(DataClassDictMixin):
    tag_name: str
    draft: bool
    prerelease: bool
    assets: list[GitHubReleaseAsset]
    zipball_url: str

def get_release(tag: str | None = None) -> GitHubRelease:
    """Fetch a pinned release, or GitHub's latest stable release."""
    endpoint = "latest" if tag is None else f"tags/{quote(tag, safe='')}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
    }
    response = requests.get(f"{RELEASES_URL}/{endpoint}", headers=headers, timeout=15)
    response.raise_for_status()
    return GitHubRelease.from_dict(response.json())

class ReleaseCacheError(RuntimeError):
    pass

def cache_release_source(release: GitHubRelease, directory: Path) -> Path:
    releases_dir = directory / ".hawkdrive" / "releases"
    destination = releases_dir / quote(release.tag_name, safe="")

    if destination.exists():
        return destination

    headers = {"X-GitHub-Api-Version": "2026-03-10"}

    try:
        releases_dir.mkdir(parents=True, exist_ok=True)

        with TemporaryDirectory(prefix=".download-", dir=releases_dir) as temp_dir:
            staging = Path(temp_dir)
            zip_path = staging / "source.zip"
            extract_dir = staging / "extracted"

            with requests.get(
                release.zipball_url,
                headers=headers,
                stream=True,
                timeout=(10, 60),
            ) as response:
                response.raise_for_status()
                with zip_path.open("wb") as archive_file:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        archive_file.write(chunk)

            with ZipFile(zip_path) as archive:
                archive.extractall(extract_dir)

            roots = list(extract_dir.iterdir())
            if len(roots) != 1 or not roots[0].is_dir():
                raise ReleaseCacheError(
                    f"Unexpected source archive layout for {release.tag_name}"
                )

            try:
                roots[0].rename(destination)
            except OSError:
                # Another sync may have published this release first.
                if not destination.is_dir():
                    raise

    except (requests.RequestException, BadZipFile, OSError) as exc:
        raise ReleaseCacheError(
            f"Could not cache HawkDrive release {release.tag_name}: {exc}"
        ) from exc

    return destination