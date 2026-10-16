"""Tests for the dockge plugin.

Only the parts that don't need a live dockge are covered here: the URL and state
mangling, the password lookup, and the socket.io bookkeeping. The protocol
itself is exercised against a fake server by the e2e harness.
"""

import pytest

pytest.importorskip("socketio", reason="dockge needs python-socketio")

from conftest import load_plugin

dockge = load_plugin("dockge")


# -- stack_url -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "base, name, expected",
    [
        ("http://localhost:5001", "media", "http://localhost:5001/compose/media"),
        ("http://localhost:5001/", "media", "http://localhost:5001/compose/media"),
        ("http://localhost:5001///", "media", "http://localhost:5001/compose/media"),
        # a subpath deployment keeps its prefix
        ("https://host/dockge", "media", "https://host/dockge/compose/media"),
        # and the stack name is url-encoded, since dockge's route is a path param
        ("http://localhost:5001", "my stack", "http://localhost:5001/compose/my%20stack"),
        ("http://localhost:5001", "a/b", "http://localhost:5001/compose/a%2Fb"),
    ],
)
def test_stack_url(base, name, expected):
    assert dockge.stack_url(base, name) == expected


# -- state_of -------------------------------------------------------------------------------


def _services(stack, **services):
    """The {stack: {service: [state, ...]}} shape `state_of` expects."""
    return {stack: services}


def test_state_of_prefers_the_most_informative_container():
    # one healthy and one unhealthy container: the broken one is the news
    stack = {"status": 3}
    services = _services("media", media=["RUNNING", "HEALTHY"], jellyfin=["UNHEALTHY"])
    assert dockge.state_of("media", stack, services) == "unhealthy"


def test_state_of_falls_back_to_the_dockge_status():
    # a draft stack is not deployed, so it has no containers to ask
    assert dockge.state_of("scratch", {"status": 1}, {}) == "draft"
    assert dockge.state_of("scratch", {"status": 3}, {}) == "running"
    assert dockge.state_of("scratch", {"status": 4}, {}) == "exited"
    # status 2 is CREATED_STACK, which dockge names "created_stack"
    assert dockge.state_of("scratch", {"status": 2}, {}) == "created_stack"
    assert dockge.state_of("scratch", {"status": 0}, {}) == "unknown"


def test_state_of_ignores_healthcheck_noise():
    # a running container with no healthcheck reports "none" - that is not a state
    stack = {"status": 3}
    services = _services("media", media=["RUNNING", "none"])
    assert dockge.state_of("media", stack, services) == "running"


def test_state_of_survives_a_stack_dockge_told_us_nothing_about():
    assert dockge.state_of("x", {}, {}) == "unknown"
    assert dockge.state_of("x", {"status": 99}, {}) == "unknown"


def test_state_of_is_case_insensitive():
    assert dockge.state_of("x", {"status": 3}, _services("x", a=["Running"])) == "running"


# -- summarize ------------------------------------------------------------------------------


def test_summarize_counts_repeated_states():
    # sorted, so that the summary of an unchanged stack does not jump around
    states = ["running", "exited", "running", "running"]
    assert dockge.summarize(states) == "EXITED, 3x RUNNING"


def test_summarize_of_a_single_state_does_not_count():
    assert dockge.summarize(["running"]) == "RUNNING"
    assert dockge.summarize([]) == ""


# -- resolve_password -----------------------------------------------------------------------


def test_resolve_password_uses_the_plaintext_password():
    assert dockge.resolve_password("  s3cret  ", "") == "s3cret"
    assert dockge.resolve_password("", "   ") == ""


def test_resolve_password_prefers_the_rbw_entry(monkeypatch):
    # the entry wins over the plaintext one, so the password can stay out of the
    # albert config
    monkeypatch.setattr(dockge.shutil, "which", lambda name: "/usr/bin/rbw")

    def fake_run(cmd, **kwargs):
        assert cmd == ["rbw", "get", "dockge"]
        return subprocess_result(b"  hunter2\n")

    monkeypatch.setattr(dockge.subprocess, "run", fake_run)
    assert dockge.resolve_password("ignored", "dockge") == "hunter2"


def subprocess_result(stdout, returncode=0, stderr=b""):
    import subprocess

    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_resolve_password_complains_when_rbw_is_missing(monkeypatch):
    monkeypatch.setattr(dockge.shutil, "which", lambda name: None)
    with pytest.raises(dockge.DockgeError, match="rbw command is not installed"):
        dockge.resolve_password("", "dockge")


def test_resolve_password_reports_an_rbw_failure(monkeypatch):
    monkeypatch.setattr(dockge.shutil, "which", lambda name: "/usr/bin/rbw")

    def fake_run(cmd, **kwargs):
        return subprocess_result(b"", returncode=1, stderr=b"not found\n")

    monkeypatch.setattr(dockge.subprocess, "run", fake_run)
    with pytest.raises(dockge.DockgeError, match="failed: not found"):
        dockge.resolve_password("", "dockge")


# -- icons ----------------------------------------------------------------------------------


def test_every_state_has_an_icon_file_on_disk():
    # a typo in STATE_ICONS would leave albert with no icon and no error
    for state, filename in dockge.STATE_ICONS.items():
        assert (dockge.ICON_DIR / filename).is_file(), f"{state} -> {filename} is missing"


def test_every_container_state_dockge_reports_maps_to_an_icon():
    # the states docker actually uses, as of dockge's agent socket handler
    docker_states = [
        "created",
        "restarting",
        "running",
        "removing",
        "paused",
        "exited",
        "dead",
        "starting",
        "healthy",
        "unhealthy",
    ]
    for state in docker_states:
        assert state in dockge.STATE_ICONS, f"{state} has no icon"


def test_a_container_without_a_healthcheck_gets_no_icon():
    # "none" is dockge's way of saying "no healthcheck configured" - a stack whose
    # only container reports it has no state of its own, so it needs no icon
    assert "none" in dockge.STATE_NOISE
    assert "none" not in dockge.STATE_ICONS


# -- _disconnect ---------------------------------------------------------------------------


class _FakeEio:
    def __init__(self, calls):
        self.calls = calls

    def disconnect(self, abort=False):
        self.calls.append(("eio.disconnect", abort))


class _FakeClient:
    """A socketio client that records how it was closed."""

    def __init__(self):
        self.calls = []
        self.eio = _FakeEio(self.calls)

    def disconnect(self):
        raise AssertionError(
            "socketio's disconnect() joins the read loop, which sits in a long poll "
            "and only returns once the server pings - a full ping interval per reconnect"
        )


def test_disconnect_closes_the_engine_without_waiting():
    fake = _FakeClient()
    assert dockge.DockgeClient._disconnect(fake) is None
    assert fake.calls == [("eio.disconnect", True)]


def test_disconnect_tolerates_a_broken_client():
    class Broken:
        class eio:
            @staticmethod
            def disconnect(abort=False):
                raise OSError("socket already gone")

    assert dockge.DockgeClient._disconnect(Broken()) is None


def test_disconnect_of_nothing():
    assert dockge.DockgeClient._disconnect(None) is None


# -- credentials ----------------------------------------------------------------------------


def _failing_login(client):
    """Make *client*'s login call come back the way dockge refuses one."""

    class Ack:
        @staticmethod
        def call(sio, event, data, timeout):
            return {"ok": False, "msg": "authIncorrectCreds"}

    client._call = Ack.call


def test_a_refused_login_says_where_to_look():
    client = dockge.DockgeClient()
    _failing_login(client)
    settings = dockge.Settings("http://dockge:5001", "admin", "wrong", "")

    with pytest.raises(dockge.DockgeError) as exc:
        client._login(None, settings)

    message = str(exc.value)
    assert "http://dockge:5001" in message
    assert "authIncorrectCreds" in message
    # it must not assert the user configured a password, since a dockge without
    # authentication is a perfectly good setup
    assert "authentication enabled" in message


def test_an_autologin_during_the_grace_period_saves_the_login(monkeypatch):
    # dockge pushes `autoLogin` instead of acknowledging the login when it runs
    # without authentication, so we must give it a moment before calling it a day
    monkeypatch.setattr(dockge, "DISABLED_AUTH_TIMEOUT", 0.05)
    client = dockge.DockgeClient()
    _failing_login(client)

    import threading

    timer = threading.Timer(0.01, client._on_auto_login)
    timer.start()
    try:
        # the credentials are empty on purpose - that is the whole point here
        client._login(None, dockge.Settings("http://dockge:5001", "", "", ""))
    finally:
        timer.join()


def test_a_silent_server_is_called_a_refused_login(monkeypatch):
    monkeypatch.setattr(dockge, "DISABLED_AUTH_TIMEOUT", 0.05)
    client = dockge.DockgeClient()
    _failing_login(client)

    with pytest.raises(dockge.DockgeError, match="refused the login"):
        client._login(None, dockge.Settings("http://dockge:5001", "", "", ""))


def test_the_autologin_flag_is_per_connection():
    # it is cleared by _connect, so a stale one cannot mask the next login attempt
    client = dockge.DockgeClient()
    client._on_auto_login()
    assert client._auto_login.is_set()


# -- the wire protocol -----------------------------------------------------------------------
#
# These exist because the plugin shipped with a bug that 27 other tests happily
# walked past: it listened for a top-level "stackList" event, which dockge never
# sends. `emitAgent()` re-wraps every push as socket.emit("agent", event, ...),
# so the plugin connected, logged in, asked for the stack list, and then sat
# there with an empty result and no error. A test that only stubs `_call` and
# calls the handlers directly cannot see that, so these drive the registration
# and the push shape that dockge really uses.

STACKLIST_PUSH = {
    "ok": True,
    "stackList": {
        "my-app": {
            "name": "my-app",
            "status": 2,
            "tags": [],
            "isManagedByDockge": True,
            "composeFileName": "compose.yaml",
            "endpoint": "",
        }
    },
}


class FakeSio:
    """Just enough of socket.io.Client to see what the plugin subscribes to."""

    def __init__(self, *args, **kwargs):
        self.handlers = {}

    def on(self, event, handler):
        self.handlers[event] = handler

    def connect(self, *args, **kwargs):
        return None

    def disconnect(self, *args, **kwargs):
        return None

    def push(self, event, *args):
        """Deliver a push the way dockge would."""
        self.handlers[event](*args)


def test_the_plugin_subscribes_to_the_agent_event_and_not_to_stacklist(monkeypatch):
    client = dockge.DockgeClient()
    fake = FakeSio()
    monkeypatch.setattr(dockge.socketio, "Client", lambda *a, **kw: fake)
    monkeypatch.setattr(client, "_login", lambda sio, settings: None)

    client._connect(dockge.Settings("http://dockge:5001", "admin", "pw", ""))

    assert "agent" in fake.handlers, "must listen for dockge's agent-wrapped pushes"
    assert "stackList" not in fake.handlers, (
        "dockge never emits a top-level stackList event; listening for it means "
        "the plugin silently never receives anything"
    )


def test_a_dockge_style_push_fills_the_stack_list(monkeypatch):
    client = dockge.DockgeClient()
    fake = FakeSio()
    monkeypatch.setattr(dockge.socketio, "Client", lambda *a, **kw: fake)
    monkeypatch.setattr(client, "_login", lambda sio, settings: None)
    client._connect(dockge.Settings("http://dockge:5001", "admin", "pw", ""))

    # exactly what the server puts on the wire: event "agent", "stackList" first
    fake.push("agent", "stackList", STACKLIST_PUSH)

    snap = client.snapshot()
    assert snap.error is None
    assert sorted(snap.stacks) == ["my-app"]
    assert dockge.state_of("my-app", snap.stacks["my-app"], snap.services) == "created_stack"


def test_the_endpoint_field_emitted_by_dockge_is_harmless(monkeypatch):
    # emitAgent() injects `endpoint` into the payload object
    client = dockge.DockgeClient()
    fake = FakeSio()
    monkeypatch.setattr(dockge.socketio, "Client", lambda *a, **kw: fake)
    monkeypatch.setattr(client, "_login", lambda sio, settings: None)
    client._connect(dockge.Settings("http://dockge:5001", "admin", "pw", ""))

    push = {"ok": True, "stackList": dict(STACKLIST_PUSH["stackList"], _endpoint="")}
    fake.push("agent", "stackList", push)
    assert sorted(client.snapshot().stacks) == ["my-app"]


def test_auto_login_also_arrives_wrapped_in_an_agent_push(monkeypatch):
    client = dockge.DockgeClient()
    fake = FakeSio()
    monkeypatch.setattr(dockge.socketio, "Client", lambda *a, **kw: fake)
    monkeypatch.setattr(client, "_login", lambda sio, settings: None)
    client._connect(dockge.Settings("http://dockge:5001", "", "", ""))

    assert not client._auto_login.is_set()
    fake.push("agent", "autoLogin")
    assert client._auto_login.is_set()


def test_an_unknown_agent_push_is_ignored(monkeypatch):
    client = dockge.DockgeClient()
    fake = FakeSio()
    monkeypatch.setattr(dockge.socketio, "Client", lambda *a, **kw: fake)
    monkeypatch.setattr(client, "_login", lambda sio, settings: None)
    client._connect(dockge.Settings("http://dockge:5001", "admin", "pw", ""))

    fake.push("agent", "terminalWrite", "x", "some output")
    fake.push("agent", "stackList", STACKLIST_PUSH)
    assert sorted(client.snapshot().stacks) == ["my-app"]


def test_a_failed_stacklist_push_does_not_wipe_the_known_stacks(monkeypatch):
    client = dockge.DockgeClient()
    fake = FakeSio()
    monkeypatch.setattr(dockge.socketio, "Client", lambda *a, **kw: fake)
    monkeypatch.setattr(client, "_login", lambda sio, settings: None)
    client._connect(dockge.Settings("http://dockge:5001", "admin", "pw", ""))

    fake.push("agent", "stackList", STACKLIST_PUSH)
    fake.push("agent", "stackList", {"ok": False, "msg": "no docker"})
    assert sorted(client.snapshot().stacks) == ["my-app"]


def test_a_malformed_stacklist_push_is_ignored(monkeypatch):
    client = dockge.DockgeClient()
    fake = FakeSio()
    monkeypatch.setattr(dockge.socketio, "Client", lambda *a, **kw: fake)
    monkeypatch.setattr(client, "_login", lambda sio, settings: None)
    client._connect(dockge.Settings("http://dockge:5001", "admin", "pw", ""))

    fake.push("agent", "stackList", "not a dict")
    assert client.snapshot().stacks == {}


# -- searching ------------------------------------------------------------------------------


def test_an_empty_search_keeps_everything_in_name_order():
    stacks = {"zebra": {}, "alpha": {}, "middle": {}}
    assert dockge.search_stacks(stacks, "") == ["alpha", "middle", "zebra"]
    assert dockge.search_stacks(stacks, "   ") == ["alpha", "middle", "zebra"]


def test_a_prefix_narrows_the_list():
    stacks = {"baikal": {}, "barotrauma": {}, "nginx": {}}
    assert dockge.search_stacks(stacks, "bai") == ["baikal"]
    assert dockge.search_stacks(stacks, "ba") == ["baikal", "barotrauma"]


def test_search_is_case_insensitive():
    assert dockge.search_stacks({"Baikal": {}}, "bai") == ["Baikal"]


def test_a_middle_fragment_matches():
    assert dockge.search_stacks({"my-compose-stack": {}, "other": {}}, "compose") == [
        "my-compose-stack"
    ]


def test_skipped_letters_match():
    # the point of the subsequence fallback: `bkl` must find `baikal`
    assert dockge.search_stacks({"baikal": {}, "nginx": {}}, "bkl") == ["baikal"]


def test_a_typo_still_finds_the_stack():
    assert dockge.search_stacks({"baikal": {}, "nginx": {}}, "baikel") == ["baikal"]


def test_nothing_matches_returns_nothing():
    stacks = {"baikal": {}, "nginx": {}}
    assert dockge.search_stacks(stacks, "zzzzzz") == []


def test_exact_matches_rank_above_partial_ones():
    stacks = {"ba": {}, "baikal-service": {}}
    assert dockge.search_stacks(stacks, "ba") == ["ba", "baikal-service"]


def test_equally_good_matches_stay_in_name_order():
    stacks = {"zebra-web": {}, "alpha-web": {}}
    assert dockge.search_stacks(stacks, "web") == ["alpha-web", "zebra-web"]


def test_the_agent_endpoint_is_searchable_too():
    stacks = {
        "baikal": {"endpoint": "dockge.xf85.srv.bergercookie.dev"},
        "local": {"endpoint": ""},
    }
    assert dockge.search_stacks(stacks, "xf85") == ["baikal"]


def test_a_name_match_outranks_an_endpoint_match():
    stacks = {
        "media": {"endpoint": "prod.example.com"},
        "other": {"endpoint": ""},
    }
    # "media" matches media by name; the endpoint match on media is weaker still
    assert dockge.search_stacks(stacks, "media") == ["media"]


def test_fuzzy_score_of_nothing_is_zero():
    assert dockge.fuzzy_score("x", "") == 0.0
    assert dockge.fuzzy_score("", "anything") == 1.0


def test_a_short_needle_does_not_wipe_the_list():
    # the failure mode that motivated not using get_close_matches: a one or two
    # letter prefix has to match long stack names
    stacks = {"a-very-long-stack-name": {}, "another": {}}
    assert dockge.search_stacks(stacks, "v") == ["a-very-long-stack-name"]


# -- agent endpoints in urls -----------------------------------------------------------------


def test_a_local_stack_uses_the_short_route():
    assert dockge.stack_url("http://localhost:5001", "media") == (
        "http://localhost:5001/compose/media"
    )


def test_a_remote_agent_stack_keeps_its_endpoint_in_the_path():
    # the bug this fixes: without the endpoint dockge resolves the stack against
    # the local instance and the page does not exist
    assert dockge.stack_url(
        "https://dockge.srv.bergercookie.dev",
        "baikal",
        "dockge.xf85.srv.bergercookie.dev",
    ) == "https://dockge.srv.bergercookie.dev/compose/baikal/dockge.xf85.srv.bergercookie.dev"


def test_the_endpoint_of_a_stack_is_read_from_the_push():
    assert dockge.endpoint_of({"endpoint": "agent.example.com"}) == "agent.example.com"
    assert dockge.endpoint_of({"endpoint": ""}) == ""
    assert dockge.endpoint_of({"endpoint": "  spaced.example.com  "}) == "spaced.example.com"
    # a missing or bogus endpoint must not explode
    assert dockge.endpoint_of({}) == ""
    assert dockge.endpoint_of({"endpoint": None}) == ""
    assert dockge.endpoint_of({"endpoint": 42}) == ""


def test_a_subpath_deployment_keeps_its_prefix():
    assert dockge.stack_url("https://host/dockge", "media", "agent.example.com") == (
        "https://host/dockge/compose/media/agent.example.com"
    )
