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


def test_procedure_page_url():
    assert komodo.procedure_page_url("http://localhost:9120", "abc123") == (
        "http://localhost:9120/procedures/abc123"
    )


def test_repo_page_url():
    assert komodo.repo_page_url("http://localhost:9120", "abc123") == (
        "http://localhost:9120/repos/abc123"
    )


def test_repo_page_url_encodes_the_id():
    assert komodo.repo_page_url("http://localhost:9120", "a/b") == (
        "http://localhost:9120/repos/a%2Fb"
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


def test_procedure_state_category_maps_every_known_state():
    for state in ("Ok", "Running", "Failed", "Unknown"):
        category = komodo.procedure_state_category({"info": {"state": state}})
        assert category in komodo.STATE_ICONS


def test_repo_state_category_maps_every_known_state():
    for state in ("Cloning", "Pulling", "Building", "Ok", "Failed", "Unknown"):
        category = komodo.repo_state_category({"info": {"state": state}})
        assert category in komodo.STATE_ICONS
    assert komodo.repo_state_category({}) == "unknown"


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


def test_procedure_subtext_includes_state_and_stage_count():
    procedure = {"info": {"state": "Failed", "stages": 3}}
    assert komodo.procedure_subtext(procedure) == "Procedure | Last run failed | 3 stages"


def test_procedure_subtext_without_info():
    assert komodo.procedure_subtext({}) == "Procedure | Unknown status"


def test_repo_subtext_includes_state_server_repository_and_latest_hash():
    repo = {
        "info": {
            "state": "Pulling",
            "server_name": "homelab",
            "repo": "bergercookie/awesome-albert-plugins",
            "branch": "master",
            "latest_hash": "abc123",
        }
    }
    assert komodo.repo_subtext(repo) == (
        "Repository | Pulling | homelab | bergercookie/awesome-albert-plugins@master | abc123"
    )


def test_repo_subtext_without_info():
    assert komodo.repo_subtext({}) == "Repository | Unknown status"


def test_repo_source_url_ignores_missing_and_non_web_links():
    assert komodo.repo_source_url({}) == ""
    non_web = {"info": {"repo_link": "git@github.com:owner/repo.git"}}
    assert komodo.repo_source_url(non_web) == ""


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


def _procedure(name, procedure_id=None):
    return {"id": procedure_id or name, "name": name, "info": {}}


def _repo(name, git_repo="", server="", repo_id=None):
    return {
        "id": repo_id or name,
        "name": name,
        "info": {"repo": git_repo, "server_name": server},
    }


def test_build_entries_covers_every_kind():
    entries = komodo.build_entries(
        [_stack("media")],
        [_container("nginx")],
        [_sync("infra")],
        [_procedure("backup")],
        [_repo("plugins")],
    )
    kinds = {entry.kind for entry in entries}
    assert kinds == {"stack", "container", "sync", "procedure", "repo"}


def test_search_entries_empty_term_groups_by_kind_then_name():
    entries = komodo.build_entries(
        [_stack("zeta"), _stack("alpha")],
        [_container("beta")],
        [_sync("gamma")],
        [_procedure("delta")],
        [_repo("epsilon")],
    )
    names = [(entry.kind, entry.data["name"]) for entry in komodo.search_entries(entries, "")]
    assert names == [
        ("stack", "alpha"),
        ("stack", "zeta"),
        ("container", "beta"),
        ("sync", "gamma"),
        ("procedure", "delta"),
        ("repo", "epsilon"),
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


def test_search_entries_also_matches_the_git_repository_of_a_repo():
    entries = komodo.build_entries(
        [], [], [], [], [_repo("plugins", git_repo="bergercookie/awesome-albert-plugins")]
    )
    matches = komodo.search_entries(entries, "awesome-albert")
    assert [entry.kind for entry in matches] == ["repo"]


def test_search_entries_drops_entries_that_do_not_match():
    entries = komodo.build_entries([_stack("media")], [], [])
    assert komodo.search_entries(entries, "nope") == []


# -- kind filtering ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "query, expected",
    [
        ("", (None, "")),
        ("   ", (None, "")),
        ("repo", ("repo", "")),
        ("repos", ("repo", "")),
        ("repository", ("repo", "")),
        ("repositories media", ("repo", "media")),
        ("stack", ("stack", "")),
        ("container media", ("container", "media")),
        ("cont", ("container", "")),
        ("cont media", ("container", "media")),
        ("sync", ("sync", "")),
        ("resource sync", ("sync", "")),
        ("resource syncs infra", ("sync", "infra")),
        ("proc", ("procedure", "")),
        ("procedures backup", ("procedure", "backup")),
        ("media", (None, "media")),
        ("my repo", (None, "my repo")),
    ],
)
def test_parse_query_recognizes_a_leading_kind(query, expected):
    assert komodo.parse_query(query) == expected


@pytest.mark.parametrize(
    "kind, expected",
    [
        (None, "repo"),
        ("repo", "container"),
        ("container", "stack"),
        ("stack", "sync"),
        ("sync", "procedure"),
        ("procedure", "repo"),
    ],
)
def test_next_kind_cycles_through_every_kind(kind, expected):
    assert komodo.next_kind(kind) == expected


def test_search_entries_filters_by_kind():
    entries = komodo.build_entries(
        [_stack("media")],
        [_container("media")],
        [_sync("media")],
        [_procedure("media")],
        [_repo("media")],
    )
    kinds = {entry.kind for entry in komodo.search_entries(entries, "", "repo")}
    assert kinds == {"repo"}


def test_search_entries_filters_by_kind_and_term():
    entries = komodo.build_entries(
        [_stack("media")],
        [_container("nginx")],
        [_sync("media")],
        [],
        [_repo("media"), _repo("other")],
    )
    matches = komodo.search_entries(entries, "media", "repo")
    assert [entry.data["name"] for entry in matches] == ["media"]


def test_search_entries_filter_without_a_term_keeps_the_kind_order():
    entries = komodo.build_entries(
        [_stack("zzz")],
        [_container("aaa")],
        [],
        [],
        [],
    )
    matches = komodo.search_entries(entries, "", "container")
    assert [entry.data["name"] for entry in matches] == ["aaa"]


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


# -- pulling images ---------------------------------------------------------------------------


class _Ctx:
    """The little of Albert's query context the items ask for."""

    trigger = "komo "
    query = ""


def _tab_query(query):
    ctx = _Ctx()
    ctx.query = query
    return komodo.Plugin()._tab_query(ctx)


def test_tab_cycles_the_kind_filter():
    assert _tab_query("") == "repo"
    assert _tab_query("repo") == "container"
    assert _tab_query("container") == "stack"
    assert _tab_query("stack") == "sync"
    assert _tab_query("sync") == "proc"
    assert _tab_query("proc") == "repo"


def test_tab_keeps_the_search_term():
    assert _tab_query("repo media") == "container media"


def test_items_use_the_tab_filter_as_their_input_action():
    plugin = komodo.Plugin()
    ctx = _Ctx()
    ctx.query = "repo"
    item = plugin._repo_item(ctx, {"id": "rp1", "name": "media", "info": {}})
    assert item.input_action_text == "container"


def test_stack_item_offers_pulling_the_images():
    plugin = komodo.Plugin()
    item = plugin._stack_item(_Ctx(), {"id": "st1", "name": "media", "info": {}})
    actions = {action.id: action.text for action in item.actions}
    assert actions["pull"] == "Pull images for media"


def test_container_item_offers_pulling_the_image():
    plugin = komodo.Plugin()
    item = plugin._container_item(
        _Ctx(), {"server_id": "srv1", "server_name": "homelab", "name": "web"}
    )
    actions = {action.id: action.text for action in item.actions}
    assert actions["pull"] == "Pull image for web"


def test_procedure_item_offers_running_it():
    plugin = komodo.Plugin()
    item = plugin._procedure_item(_Ctx(), {"id": "pr1", "name": "backup", "info": {}})
    actions = {action.id: action.text for action in item.actions}
    assert actions["run"] == "Run backup"


def test_run_procedure_executes_it(monkeypatch):
    calls = []
    monkeypatch.setattr(komodo, "run_action", lambda *args: calls.append(args[3:]))
    monkeypatch.setattr(komodo, "notify", lambda msg: None)

    plugin = komodo.Plugin()
    plugin._async = lambda work, note: work()
    plugin._run_procedure("pr1", "backup")
    assert calls == [("execute/RunProcedure", {"procedure": "pr1"})]


def test_repo_item_offers_opening_source_pulling_and_reloading():
    plugin = komodo.Plugin()
    item = plugin._repo_item(
        _Ctx(),
        {
            "id": "rp1",
            "name": "plugins",
            "info": {
                "state": "Ok",
                "repo_link": "https://github.com/bergercookie/awesome-albert-plugins",
            },
        },
    )
    actions = {action.id: action.text for action in item.actions}
    assert list(actions) == ["open", "source", "pull", "reload"]
    assert actions["open"] == "Open in browser"
    assert actions["source"] == "Open source in browser"
    assert actions["pull"] == "Pull plugins"


def test_repo_item_without_a_repo_link_has_no_source_action():
    item = komodo.Plugin()._repo_item(_Ctx(), {"id": "rp1", "name": "plugins", "info": {}})
    assert [action.id for action in item.actions] == ["open", "pull", "reload"]


def test_pull_repo_executes_it(monkeypatch):
    calls = []
    monkeypatch.setattr(komodo, "run_action", lambda *args: calls.append(args[3:]))
    monkeypatch.setattr(komodo, "notify", lambda msg: None)

    plugin = komodo.Plugin()
    plugin._async = lambda work, note: work()
    plugin._pull_repo("rp1", "plugins")
    assert calls == [("execute/PullRepo", {"repo": "rp1"})]


def test_fetch_repos_reads_the_komodo_repo_list(monkeypatch):
    fake = _fake_call({"read/ListRepos": [{"id": "rp1", "name": "plugins"}, None]})
    monkeypatch.setattr(komodo, "call", fake)
    assert komodo.fetch_repos("http://localhost:9120", "key", "secret") == [
        {"id": "rp1", "name": "plugins"}
    ]
    assert fake.calls == [("read/ListRepos", {"limit": 0})]


def test_entries_list_includes_repos(monkeypatch):
    repo = _repo("plugins", server="homelab")
    monkeypatch.setattr(komodo, "fetch_stacks", lambda *args: [])
    monkeypatch.setattr(komodo, "fetch_containers", lambda *args: [])
    monkeypatch.setattr(komodo, "fetch_syncs", lambda *args: [])
    monkeypatch.setattr(komodo, "fetch_procedures", lambda *args: [])
    monkeypatch.setattr(komodo, "fetch_repos", lambda *args: [repo])

    entries = komodo.Plugin()._entries_list()
    assert [(entry.kind, entry.data) for entry in entries] == [("repo", repo)]


def _fake_call(payloads):
    """A `call` stand-in answering with the payload registered for the path.

    The paths it was asked for are kept in its `calls` attribute.
    """
    calls = []

    def fake_call(method, base_url, api_key, api_secret, path, body=None, timeout=None):
        calls.append((path, body))
        return payloads.get(path, {})

    fake_call.calls = calls
    return fake_call


def test_service_of_container_finds_the_service_running_it():
    services = [
        {"service": "web", "container": {"name": "media-web-1"}},
        {"service": "db", "container": {"name": "media-db-1"}},
    ]
    assert komodo.service_of_container(services, "media-db-1") == "db"


def test_service_of_container_finds_the_service_of_another_replica():
    services = [{"service": "web", "container": {"name": "media-web-1"}}]
    assert komodo.service_of_container(services, "media-web-2") == "web"


def test_service_of_container_is_empty_for_an_unknown_container():
    services = [{"service": "web", "container": {"name": "media-web-1"}}]
    assert komodo.service_of_container(services, "media-db-1") == ""


def test_service_of_container_is_empty_for_a_service_without_a_container():
    assert komodo.service_of_container([{"service": "web"}], "media-web-1") == ""


def test_pull_container_image_pulls_the_service_of_its_stack(monkeypatch):
    fake = _fake_call(
        {
            "read/GetResourceMatchingContainer": {"resource": {"type": "stack", "id": "st1"}},
            "read/ListStackServices": [
                {"service": "web", "container": {"name": "media-web-1"}},
                {"service": "db", "container": {"name": "media-db-1"}},
            ],
        }
    )
    monkeypatch.setattr(komodo, "call", fake)
    pulled = []
    monkeypatch.setattr(komodo, "run_action", lambda *args: pulled.append((args[3], args[4])))

    komodo.pull_container_image(
        "http://localhost:9120", "key", "secret", "srv1", "media-db-1"
    )

    assert pulled == [
        ("execute/PullStack", {"stack": "st1", "services": ["db"]}),
    ]
    assert [path for path, _ in fake.calls] == [
        "read/GetResourceMatchingContainer",
        "read/ListStackServices",
    ]


def test_pull_container_image_pulls_a_deployment(monkeypatch):
    monkeypatch.setattr(
        komodo,
        "call",
        _fake_call(
            {
                "read/GetResourceMatchingContainer": {
                    "resource": {"type": "deployment", "id": "dep1"}
                },
            }
        ),
    )
    pulled = []
    monkeypatch.setattr(komodo, "run_action", lambda *args: pulled.append((args[3], args[4])))

    komodo.pull_container_image("http://localhost:9120", "key", "secret", "srv1", "web")

    assert pulled == [("execute/PullDeployment", {"deployment": "dep1"})]


def test_pull_container_image_refuses_a_container_without_a_server(monkeypatch):
    monkeypatch.setattr(komodo, "call", _fake_call({}))

    with pytest.raises(komodo.KomodoError, match="does not know the server"):
        komodo.pull_container_image("http://localhost:9120", "key", "secret", "", "web")


def test_pull_container_image_refuses_a_container_without_a_stack(monkeypatch):
    monkeypatch.setattr(
        komodo,
        "call",
        _fake_call({"read/GetResourceMatchingContainer": {"resource": None}}),
    )

    with pytest.raises(komodo.KomodoError, match="not part of a stack"):
        komodo.pull_container_image(
            "http://localhost:9120", "key", "secret", "srv1", "web"
        )


def test_pull_container_image_refuses_a_container_of_an_unknown_service(monkeypatch):
    monkeypatch.setattr(
        komodo,
        "call",
        _fake_call(
            {
                "read/GetResourceMatchingContainer": {
                    "resource": {"type": "stack", "id": "st1"}
                },
                "read/ListStackServices": [
                    {"service": "web", "container": {"name": "media-web-1"}},
                ],
            }
        ),
    )

    with pytest.raises(komodo.KomodoError, match="does not know which service"):
        komodo.pull_container_image(
            "http://localhost:9120", "key", "secret", "srv1", "media-db-1"
        )
