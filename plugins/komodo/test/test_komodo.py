"""Tests for the komodo plugin.

Only the parts that don't need a live Komodo server are covered here: URL
building, state categorization, the merged search list and the secret lookup.
Talking to the real REST API is not exercised by this suite.
"""

import subprocess

import pytest

from conftest import load_plugin

komodo = load_plugin("komodo")


# -- urls -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "base, path, expected",
    [
        ("http://localhost:9120", "read/ListStacks", "http://localhost:9120/read/ListStacks"),
        ("http://localhost:9120/", "/read/ListStacks", "http://localhost:9120/read/ListStacks"),
        ("http://localhost:9120///", "read/ListStacks", "http://localhost:9120/read/ListStacks"),
        ("https://host/komodo", "stacks/abc", "https://host/komodo/stacks/abc"),
    ],
)
def test_join_url(base, path, expected):
    assert komodo.join_url(base, path) == expected


def test_stack_page_url():
    assert komodo.stack_page_url("http://localhost:9120", "abc123") == (
        "http://localhost:9120/stacks/abc123"
    )


def test_sync_page_url():
    assert komodo.sync_page_url("http://localhost:9120", "abc123") == (
        "http://localhost:9120/resource-syncs/abc123"
    )


def test_container_page_url_links_to_its_server():
    assert komodo.container_page_url("http://localhost:9120", "srv1", "nginx") == (
        "http://localhost:9120/servers/srv1/container/nginx"
    )


def test_container_page_url_falls_back_without_a_server():
    assert komodo.container_page_url("http://localhost:9120", "", "nginx") == (
        "http://localhost:9120"
    )


def test_container_page_url_encodes_the_container_name():
    assert komodo.container_page_url("http://localhost:9120", "srv1", "a/b") == (
        "http://localhost:9120/servers/srv1/container/a%2Fb"
    )


# -- resolve_secret -----------------------------------------------------------------------


def test_resolve_secret_uses_the_plaintext_value():
    assert komodo.resolve_secret("  s3cret  ", "", "API key") == "s3cret"
    assert komodo.resolve_secret("", "   ", "API key") == ""


def test_resolve_secret_prefers_the_command(monkeypatch):
    def fake_run(cmd, **kwargs):
        assert cmd == "pass show komodo/key"
        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout="hunter2\n", stderr=""
        )

    monkeypatch.setattr(komodo.subprocess, "run", fake_run)
    assert komodo.resolve_secret("ignored", "pass show komodo/key", "API key") == "hunter2"


def test_resolve_secret_reports_a_command_failure(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="not found\n"
        )

    monkeypatch.setattr(komodo.subprocess, "run", fake_run)
    with pytest.raises(komodo.KomodoError, match="failed to print the API key: not found"):
        komodo.resolve_secret("", "pass show komodo/key", "API key")


def test_resolve_secret_reports_an_empty_command_answer(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="   \n", stderr="")

    monkeypatch.setattr(komodo.subprocess, "run", fake_run)
    with pytest.raises(komodo.KomodoError, match="printed nothing"):
        komodo.resolve_secret("", "echo", "API secret")


# -- state categorization ------------------------------------------------------------------


def test_container_state_category_maps_every_docker_state():
    docker_states = [
        "running",
        "created",
        "restarting",
        "stopping",
        "removing",
        "paused",
        "exited",
        "dead",
        "",
    ]
    for state in docker_states:
        category = komodo.container_state_category({"state": state})
        assert category in komodo.STATE_ICONS


def test_container_state_category_is_unknown_for_anything_else():
    assert komodo.container_state_category({"state": "something-new"}) == "unknown"
    assert komodo.container_state_category({}) == "unknown"


def test_stack_state_category_maps_every_known_state():
    stack_states = [
        "deploying",
        "running",
        "paused",
        "stopped",
        "created",
        "restarting",
        "dead",
        "removing",
        "unhealthy",
        "down",
        "unknown",
    ]
    for state in stack_states:
        category = komodo.stack_state_category({"info": {"state": state}})
        assert category in komodo.STATE_ICONS


def test_sync_state_category_maps_every_known_state():
    for state in ("Syncing", "Pending", "Ok", "Failed", "Unknown"):
        category = komodo.sync_state_category({"info": {"state": state}})
        assert category in komodo.STATE_ICONS


def test_every_state_has_an_icon_file_on_disk():
    # a typo in STATE_ICONS would leave albert with no icon and no error
    for state, filename in komodo.STATE_ICONS.items():
        assert (komodo.ICON_DIR / filename).is_file(), f"{state} -> {filename} is missing"


# -- subtext --------------------------------------------------------------------------------


def test_stack_subtext_includes_server_state_and_services():
    stack = {
        "info": {
            "server_name": "homelab",
            "state": "running",
            "services": [{"service": "web"}, {"service": "db"}],
        }
    }
    assert komodo.stack_subtext(stack) == "Stack | homelab | RUNNING | web, db"


def test_stack_subtext_counts_many_services_instead_of_naming_them():
    services = [{"service": f"svc{i}"} for i in range(5)]
    stack = {"info": {"state": "running", "services": services}}
    assert komodo.stack_subtext(stack) == "Stack | RUNNING | 5 services"


def test_container_subtext_includes_server_state_and_image():
    container = {"server_name": "homelab", "state": "running", "image": "nginx:latest"}
    assert (
        komodo.container_subtext(container) == "Container | homelab | RUNNING | nginx:latest"
    )


def test_sync_subtext_prefers_the_last_sync_message():
    sync = {"info": {"state": "Pending", "last_sync_message": "3 changes"}}
    assert komodo.sync_subtext(sync) == "Resource Sync | Changes pending | 3 changes"


def test_sync_subtext_falls_back_to_the_last_sync_hash():
    sync = {"info": {"state": "Ok", "last_sync_hash": "abc123"}}
    assert komodo.sync_subtext(sync) == "Resource Sync | Up to date | last sync abc123"


# -- fuzzy_score ------------------------------------------------------------------------------


def test_fuzzy_score_prefers_exact_and_prefix_matches():
    assert komodo.fuzzy_score("media", "media") == 1.0
    assert komodo.fuzzy_score("med", "media") == 0.95
    assert komodo.fuzzy_score("", "media") == 1.0
    assert komodo.fuzzy_score("media", "") == 0.0


def test_fuzzy_score_matches_a_subsequence():
    assert komodo.fuzzy_score("ma", "media") > 0


def test_fuzzy_score_rejects_unrelated_strings():
    assert komodo.fuzzy_score("media", "nginx") == 0.0


# -- build_entries / search_entries --------------------------------------------------------


def _stack(name, server="", stack_id=None):
    return {"id": stack_id or name, "name": name, "info": {"server_name": server}}


def _container(name, server="", server_id="srv"):
    return {"name": name, "server_name": server, "server_id": server_id}


def _sync(name, sync_id=None):
    return {"id": sync_id or name, "name": name, "info": {}}


def test_build_entries_covers_every_kind():
    entries = komodo.build_entries([_stack("media")], [_container("nginx")], [_sync("infra")])
    kinds = {entry.kind for entry in entries}
    assert kinds == {"stack", "container", "sync"}


def test_search_entries_empty_term_groups_by_kind_then_name():
    entries = komodo.build_entries(
        [_stack("zeta"), _stack("alpha")],
        [_container("beta")],
        [_sync("gamma")],
    )
    names = [(entry.kind, entry.data["name"]) for entry in komodo.search_entries(entries, "")]
    assert names == [
        ("stack", "alpha"),
        ("stack", "zeta"),
        ("container", "beta"),
        ("sync", "gamma"),
    ]


def test_search_entries_filters_by_name():
    entries = komodo.build_entries([_stack("media")], [_container("nginx")], [_sync("infra")])
    matches = komodo.search_entries(entries, "ngin")
    assert [entry.data["name"] for entry in matches] == ["nginx"]


def test_search_entries_also_matches_the_server_name():
    entries = komodo.build_entries(
        [], [_container("web", server="raspberrypi")], []
    )
    matches = komodo.search_entries(entries, "raspberrypi")
    assert [entry.data["name"] for entry in matches] == ["web"]


def test_search_entries_drops_entries_that_do_not_match():
    entries = komodo.build_entries([_stack("media")], [], [])
    assert komodo.search_entries(entries, "nope") == []


# -- update_error ---------------------------------------------------------------------------


def test_update_error_uses_the_last_failed_logs_stderr():
    update = {
        "logs": [
            {"stage": "pull", "success": True, "stdout": "ok", "stderr": ""},
            {"stage": "up", "success": False, "stdout": "", "stderr": "port already in use"},
        ]
    }
    assert komodo.update_error(update) == "port already in use"


def test_update_error_falls_back_when_there_are_no_logs():
    assert "failed" in komodo.update_error({})
