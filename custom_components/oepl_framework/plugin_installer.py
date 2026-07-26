"""Downloads and validates plugins from a custom GitHub repository.

This is the "mini HACS" install pipeline: download → extract → validate
``plugin.json`` → move into ``installed_plugins/<id>/``. Callers are
expected to have already obtained explicit user consent (trust
acknowledgement) before invoking this, since it executes third-party code.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import tarfile
import tempfile
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
PLUGIN_ID_RE = re.compile(r"^[a-z0-9_]+$")


class PluginInstallError(Exception):
    """Raised when a plugin cannot be downloaded, extracted or validated."""


async def async_download_tarball(hass: HomeAssistant, owner: str, repo: str, ref: str) -> Path:
    """Download and extract a repo tarball, returning the extracted dir.

    Works uniformly for branches, tags and commit SHAs.
    """
    session = async_get_clientsession(hass)
    url = f"{GITHUB_API}/repos/{owner}/{repo}/tarball/{ref}"
    try:
        response = await session.get(url)
        if response.status != 200:
            raise PluginInstallError(
                f"GitHub returned {response.status} for {owner}/{repo}@{ref}"
            )
        data = await response.read()
    except PluginInstallError:
        raise
    except Exception as err:  # noqa: BLE001 - network errors of any kind
        raise PluginInstallError(f"Failed to download {owner}/{repo}@{ref}: {err}") from err

    def _extract() -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix="oepl_framework_plugin_"))
        tarball_path = tmp_dir / "src.tar.gz"
        tarball_path.write_bytes(data)
        with tarfile.open(tarball_path, "r:gz") as tar:
            _safe_extract(tar, tmp_dir)
        tarball_path.unlink(missing_ok=True)
        # GitHub tarballs contain a single top-level "<owner>-<repo>-<sha>" dir.
        entries = [p for p in tmp_dir.iterdir() if p.is_dir()]
        if len(entries) != 1:
            raise PluginInstallError("Unexpected tarball layout")
        return entries[0]

    return await hass.async_add_executor_job(_extract)


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    """Extract guarding against path traversal ("tarslip")."""
    dest_resolved = dest.resolve()
    for member in tar.getmembers():
        member_path = (dest_resolved / member.name).resolve()
        if not str(member_path).startswith(str(dest_resolved)):
            raise PluginInstallError(f"Unsafe path in tarball: {member.name}")
    tar.extractall(dest, filter="data")


def validate_manifest(plugin_dir: Path):
    """Load and validate ``plugin.json`` inside ``plugin_dir``.

    Returns the parsed manifest dict. Raises :class:`PluginInstallError` on
    any structural problem.
    """
    manifest_path = plugin_dir / "plugin.json"
    if not manifest_path.is_file():
        raise PluginInstallError("plugin.json not found in repository root")

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as err:
        raise PluginInstallError(f"plugin.json is not valid JSON: {err}") from err

    required = ("id", "name", "version", "entry_point")
    missing = [key for key in required if key not in data]
    if missing:
        raise PluginInstallError(f"plugin.json missing required fields: {missing}")

    if not PLUGIN_ID_RE.match(data["id"]):
        raise PluginInstallError(
            f"Invalid plugin id {data['id']!r}: must match ^[a-z0-9_]+$"
        )
    if ":" not in data["entry_point"]:
        raise PluginInstallError(
            f"entry_point must be '<module>:<ClassName>', got {data['entry_point']!r}"
        )
    module_name = data["entry_point"].split(":", 1)[0]
    if not (plugin_dir / f"{module_name}.py").is_file():
        raise PluginInstallError(f"entry_point module {module_name}.py not found in repository")

    return data


async def async_install_from_github(
    hass: HomeAssistant, owner: str, repo: str, ref: str, target_root: Path
):
    """Full install pipeline. Returns a :class:`~.plugin_manager.PluginManifest`."""
    from .plugin_manager import PluginManifest  # local import avoids a cycle

    extracted_dir = await async_download_tarball(hass, owner, repo, ref)
    try:
        manifest_data = await hass.async_add_executor_job(validate_manifest, extracted_dir)
        manifest_data.setdefault("repo", f"{owner}/{repo}")
        manifest_data.setdefault("ref", ref)
        manifest = PluginManifest.from_dict(manifest_data, source="custom")

        target_dir = target_root / manifest.id

        def _install() -> None:
            target_root.mkdir(parents=True, exist_ok=True)
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.move(str(extracted_dir), str(target_dir))
            init_file = target_dir / "__init__.py"
            if not init_file.exists():
                init_file.write_text("", encoding="utf-8")

        await hass.async_add_executor_job(_install)
        return manifest
    finally:
        # extracted_dir is moved (not copied) into place on success, so this
        # cleans up the now-empty temp parent either way.
        await hass.async_add_executor_job(
            lambda: shutil.rmtree(extracted_dir.parent, ignore_errors=True)
        )


async def async_list_repos_by_prefix(
    hass: HomeAssistant, owner: str, prefix: str
) -> list[dict[str, str]]:
    """List an owner's public repos whose name starts with ``prefix``.

    Used for naming-convention plugin discovery (e.g. repos named
    ``HAOEPL-Plugin_*``). Uses the repo-listing endpoint rather than
    ``/search/repositories`` since it has friendlier unauthenticated rate
    limits for this "does the user have any matching repos" lookup.
    """
    session = async_get_clientsession(hass)
    url = f"{GITHUB_API}/users/{owner}/repos?per_page=100&type=public"
    try:
        response = await session.get(url)
        if response.status != 200:
            raise PluginInstallError(
                f"GitHub returned {response.status} listing repos for {owner}"
            )
        repos = await response.json()
    except PluginInstallError:
        raise
    except Exception as err:  # noqa: BLE001 - network errors of any kind
        raise PluginInstallError(f"Failed to list repositories for {owner}: {err}") from err

    return [
        {
            "repo": item["name"],
            "description": item.get("description") or "",
            "default_branch": item.get("default_branch") or "main",
        }
        for item in repos
        if isinstance(item, dict) and item.get("name", "").startswith(prefix)
    ]


async def async_get_latest_ref(hass: HomeAssistant, owner: str, repo: str) -> str | None:
    """Best-effort latest-release tag lookup, falling back to None."""
    session = async_get_clientsession(hass)
    url = f"{GITHUB_API}/repos/{owner}/{repo}/releases/latest"
    try:
        response = await session.get(url)
        if response.status != 200:
            return None
        data = await response.json()
        return data.get("tag_name")
    except Exception:  # noqa: BLE001 - purely informational lookup
        _LOGGER.debug("Could not determine latest release for %s/%s", owner, repo)
        return None
