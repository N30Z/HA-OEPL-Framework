import pytest

from custom_components.oepl_framework.plugin_installer import (
    PluginInstallError,
    async_list_repos_by_prefix,
    validate_manifest,
)


def test_validate_manifest_missing_file(tmp_path):
    with pytest.raises(PluginInstallError):
        validate_manifest(tmp_path)


def test_validate_manifest_invalid_id(tmp_path):
    (tmp_path / "plugin.json").write_text(
        '{"id": "Bad-ID", "name": "x", "version": "1.0", "entry_point": "plugin:X"}'
    )
    (tmp_path / "plugin.py").write_text("class X: pass\n")
    with pytest.raises(PluginInstallError):
        validate_manifest(tmp_path)


def test_validate_manifest_missing_entry_point_module(tmp_path):
    (tmp_path / "plugin.json").write_text(
        '{"id": "good_id", "name": "x", "version": "1.0", "entry_point": "plugin:X"}'
    )
    with pytest.raises(PluginInstallError):
        validate_manifest(tmp_path)


def test_validate_manifest_valid(tmp_path):
    (tmp_path / "plugin.json").write_text(
        '{"id": "good_id", "name": "x", "version": "1.0", "entry_point": "plugin:X"}'
    )
    (tmp_path / "plugin.py").write_text("class X: pass\n")
    data = validate_manifest(tmp_path)
    assert data["id"] == "good_id"


async def test_list_repos_by_prefix_filters_by_name(hass, aioclient_mock):
    aioclient_mock.get(
        "https://api.github.com/users/N30Z/repos",
        json=[
            {"name": "HAOEPL-Plugin_AWSH", "description": "AWSH plugin", "default_branch": "main"},
            {"name": "HAOEPL-Plugin_Bambulab", "description": None, "default_branch": "main"},
            {"name": "SomethingElse", "description": "not a plugin", "default_branch": "main"},
        ],
    )

    repos = await async_list_repos_by_prefix(hass, "N30Z", "HAOEPL-Plugin_")

    names = {item["repo"] for item in repos}
    assert names == {"HAOEPL-Plugin_AWSH", "HAOEPL-Plugin_Bambulab"}
    descriptions = {item["repo"]: item["description"] for item in repos}
    assert descriptions["HAOEPL-Plugin_AWSH"] == "AWSH plugin"
    assert descriptions["HAOEPL-Plugin_Bambulab"] == ""


async def test_list_repos_by_prefix_raises_on_error_status(hass, aioclient_mock):
    aioclient_mock.get("https://api.github.com/users/unknown-owner/repos", status=404)

    with pytest.raises(PluginInstallError):
        await async_list_repos_by_prefix(hass, "unknown-owner", "HAOEPL-Plugin_")
