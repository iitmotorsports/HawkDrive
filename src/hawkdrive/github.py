from dataclasses import dataclass
from urllib.parse import quote

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