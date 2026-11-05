"""Tests for the abbr_trilium plugin."""

import subprocess

import albert
import pytest

from conftest import load_plugin

trilium = load_plugin("abbr_trilium")


class _Response:
    status_code = 200
    text = "<p>* foo: first</p>"

    def json(self):
        return {"type": "text"}


def completed(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


def make_plugin(url="https://host", token="token", command="", note_id="note"):
    """A plugin instance with its settings set directly, no config or disk."""
    plugin = trilium.Plugin()
    plugin._url = url
    plugin._token = token
    plugin._token_command = command
    plugin._note_id = note_id
    plugin._resolved_token = None
    return plugin


@pytest.fixture(autouse=True)
def clean_albert_state():
    """The config store is class-level, so keep one test's writes out of the next."""
    config = dict(albert.PluginInstance._CONFIG)
    albert.PluginInstance._CONFIG.clear()
    yield
    albert.PluginInstance._CONFIG.clear()
    albert.PluginInstance._CONFIG.update(config)


def test_join_url_keeps_a_reverse_proxy_prefix():
    assert trilium.join_url("https://host/trilium", "etapi/notes/abc") == (
        "https://host/trilium/etapi/notes/abc"
    )


def test_normalize_note_id_accepts_an_id_a_path_or_a_url():
    note_id = "v9MDnZFkTKYF"
    assert trilium.normalize_note_id(note_id) == note_id
    assert trilium.normalize_note_id(f"#root/QIaJXuFX5LkL/{note_id}") == note_id
    assert trilium.normalize_note_id(f"https://host/#root/QIaJXuFX5LkL/{note_id}") == (
        note_id
    )
    assert trilium.normalize_note_id(f"#root/QIaJXuFX5LkL/{note_id}/") == note_id


def test_a_stored_note_url_is_reduced_to_its_id():
    plugin_id = trilium.Plugin().id()
    albert.PluginInstance._CONFIG[(plugin_id, trilium.CONFIG_NOTE_ID)] = (
        "https://host/#root/QIaJXuFX5LkL/v9MDnZFkTKYF"
    )

    assert trilium.Plugin().note_id == "v9MDnZFkTKYF"


def test_setting_a_note_url_stores_only_its_id():
    plugin = trilium.Plugin()
    plugin.note_id = "#root/QIaJXuFX5LkL/v9MDnZFkTKYF"

    assert plugin.note_id == "v9MDnZFkTKYF"
    assert albert.PluginInstance._CONFIG[(plugin.id(), trilium.CONFIG_NOTE_ID)] == (
        "v9MDnZFkTKYF"
    )


def test_html_to_text_turns_paragraphs_into_lines():
    content = "<p>* foo: first</p><p>* bar: second &amp; third</p>"
    assert trilium.html_to_text(content).splitlines() == [
        "* foo: first",
        "* bar: second & third",
    ]


def test_entries_keep_abbreviations_that_share_a_key():
    entries = trilium.make_latest_entries(
        ["* foo: first\n", "* foo: second\n", "* bar: third\n"]
    )
    assert entries == [("foo", "first"), ("foo", "second"), ("bar", "third")]


def test_append_abbreviation_writes_a_list_item_for_text_notes():
    line = trilium.abbreviation_line("foo", "A & B")
    assert trilium.append_abbreviation("<p>* old: one</p>", "text", line) == (
        "<p>* old: one</p><ul><li>foo: A &amp; B</li></ul>"
    )


def test_append_abbreviation_reuses_a_trailing_list():
    line = trilium.abbreviation_line("foo", "bar")
    assert trilium.append_abbreviation("<ul><li>old: one</li></ul>", "text", line) == (
        "<ul><li>old: one</li><li>foo: bar</li></ul>"
    )
    assert trilium.append_abbreviation(
        "<ul><li>old: one</li></ul>\n", "text", line
    ) == ("<ul><li>old: one</li><li>foo: bar</li></ul>")


def test_append_abbreviation_writes_plain_text_for_other_notes():
    line = trilium.abbreviation_line("foo", "bar")
    assert trilium.append_abbreviation("old", "code", line) == "old\n* foo: bar\n"
    assert trilium.append_abbreviation("", "code", line) == "* foo: bar\n"


def test_request_sends_the_etapi_token_and_ssl_setting(monkeypatch):
    seen = {}

    def fake_request(method, url, **kwargs):
        seen.update(method=method, url=url, **kwargs)
        return _Response()

    monkeypatch.setattr(trilium.requests, "request", fake_request)

    trilium.request(
        "GET",
        "https://host/trilium",
        "secret-token",
        "etapi/notes/abc/content",
        False,
    )

    assert seen["method"] == "GET"
    assert seen["url"] == "https://host/trilium/etapi/notes/abc/content"
    assert seen["headers"]["Authorization"] == "secret-token"
    assert seen["verify"] is False


def test_verify_ssl_defaults_to_true():
    assert trilium.Plugin().verify_ssl is True


def test_config_widget_exposes_every_setting():
    properties = {
        widget["property"]
        for widget in trilium.Plugin().configWidget()
        if "property" in widget
    }
    assert properties == {
        "trilium_url",
        "etapi_token",
        "etapi_token_command",
        "note_id",
        "verify_ssl",
    }


# -- the ETAPI token command -----------------------------------------------------------------


def test_resolve_api_key_prefers_the_plaintext_token():
    assert trilium.resolve_api_key("  plain  ", "") == "plain"
    assert trilium.resolve_api_key("  plain  ", "   ") == "plain"


def test_resolve_api_key_runs_the_command(monkeypatch):
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["shell"] = kwargs.get("shell")
        return completed(stdout="  key123\n")

    monkeypatch.setattr(trilium.subprocess, "run", fake_run)

    assert trilium.resolve_api_key("ignored", "pass show trilium") == "key123"
    assert seen["command"] == "pass show trilium"
    assert seen["shell"] is True


def test_resolve_api_key_command_wins_over_the_plaintext_token(monkeypatch):
    monkeypatch.setattr(
        trilium.subprocess,
        "run",
        lambda command, **kwargs: completed(stdout="from-command"),
    )
    assert trilium.resolve_api_key("plaintext", "echo x") == "from-command"


def test_resolve_api_key_reports_a_failed_command(monkeypatch):
    monkeypatch.setattr(
        trilium.subprocess,
        "run",
        lambda command, **kwargs: completed(returncode=1, stderr="keyring is locked\n"),
    )
    with pytest.raises(trilium.TriliumError, match=r"failed.*keyring is locked"):
        trilium.resolve_api_key("", "rbw get trilium")


def test_resolve_api_key_reports_a_command_that_hangs(monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, trilium.KEY_COMMAND_TIMEOUT)

    monkeypatch.setattr(trilium.subprocess, "run", fake_run)
    with pytest.raises(trilium.TriliumError, match="took longer"):
        trilium.resolve_api_key("", "sleep 100")


def test_resolve_api_key_refuses_empty_output(monkeypatch):
    monkeypatch.setattr(
        trilium.subprocess, "run", lambda command, **kwargs: completed(stdout="  \n")
    )
    with pytest.raises(trilium.TriliumError, match="printed nothing"):
        trilium.resolve_api_key("", "true")


def test_resolve_api_key_reports_a_command_that_will_not_start(monkeypatch):
    def fake_run(command, **kwargs):
        raise OSError("exec format error")

    monkeypatch.setattr(trilium.subprocess, "run", fake_run)
    with pytest.raises(trilium.TriliumError, match="Could not run"):
        trilium.resolve_api_key("", "some-missing-binary")


def test_the_command_token_is_used_and_cached(monkeypatch):
    calls = []

    def fake_resolve(token, command):
        calls.append((token, command))
        return "from-command"

    monkeypatch.setattr(trilium, "resolve_api_key", fake_resolve)
    plugin = make_plugin(token="plain", command="pass show trilium")

    assert plugin._api_key() == "from-command"
    assert plugin._api_key() == "from-command"
    assert calls == [("plain", "pass show trilium")]


def test_a_failed_command_is_not_cached(monkeypatch):
    calls = []

    def fake_resolve(token, command):
        calls.append(command)
        if len(calls) == 1:
            raise trilium.TriliumError("keyring is locked")
        return "now-unlocked"

    monkeypatch.setattr(trilium, "resolve_api_key", fake_resolve)
    plugin = make_plugin(token="", command="rbw get trilium")

    with pytest.raises(trilium.TriliumError, match="locked"):
        plugin._api_key()
    assert plugin._api_key() == "now-unlocked"
    assert len(calls) == 2


def test_the_command_token_is_never_written_to_the_config(monkeypatch):
    saved = dict(albert.PluginInstance._CONFIG)
    albert.PluginInstance._CONFIG.clear()
    try:
        monkeypatch.setattr(
            trilium, "resolve_api_key", lambda token, command: "super-secret"
        )
        plugin = make_plugin(token="", command="pass show trilium")

        plugin._api_key()
        assert plugin._token == ""
        assert albert.PluginInstance._CONFIG == {}
    finally:
        albert.PluginInstance._CONFIG.clear()
        albert.PluginInstance._CONFIG.update(saved)


def test_a_command_satisfies_the_setup_check():
    assert make_plugin(token="", command="pass show trilium")._setup_item() is None
    assert make_plugin(token="", command="")._setup_item() is not None


def test_load_sends_the_command_token(monkeypatch):
    plugin = make_plugin(token="", command="pass show trilium")
    seen = {}

    monkeypatch.setattr(trilium, "resolve_api_key", lambda token, command: "command-token")
    monkeypatch.setattr(
        trilium,
        "fetch_note",
        lambda base, token, note, verify: seen.update(token=token) or {"type": "text"},
    )
    monkeypatch.setattr(trilium, "fetch_note_content", lambda *args: "")

    plugin._load()
    assert seen["token"] == "command-token"


def test_setting_the_token_clears_the_resolved_command_token():
    plugin = make_plugin(token="", command="pass show trilium")
    plugin._resolved_token = "old"

    plugin.etapi_token = "  new-token  "
    assert plugin.etapi_token == "new-token"
    assert plugin._resolved_token is None


def test_setting_the_command_clears_the_resolved_token():
    plugin = make_plugin(token="", command="pass show old")
    plugin._resolved_token = "old"

    plugin.etapi_token_command = "  pass show new  "
    assert plugin.etapi_token_command == "pass show new"
    assert plugin._resolved_token is None


def test_load_parses_the_content_of_a_text_note(monkeypatch):
    plugin = trilium.Plugin()
    plugin._url = "https://host"
    plugin._token = "token"
    plugin._note_id = "note"

    monkeypatch.setattr(trilium, "fetch_note", lambda *args: {"type": "text"})
    monkeypatch.setattr(
        trilium,
        "fetch_note_content",
        lambda *args: "<p>* foo: first</p><p>* foo: second</p>",
    )

    entries, index = plugin._load()

    assert entries == [("foo", "first"), ("foo", "second")]
    assert index["foo"] == [0, 1]


def test_save_appends_to_the_designated_note(monkeypatch):
    plugin = trilium.Plugin()
    plugin._url = "https://host"
    plugin._token = "token"
    plugin._note_id = "note"

    stored = {"content": "<p>* old: one</p>"}
    monkeypatch.setattr(trilium, "fetch_note", lambda *args: {"type": "text"})
    monkeypatch.setattr(
        trilium, "fetch_note_content", lambda *args: stored["content"]
    )
    monkeypatch.setattr(
        trilium,
        "put_note_content",
        lambda *args: stored.__setitem__("content", args[-1]),
    )
    monkeypatch.setattr(trilium, "notify", lambda msg: None)

    plugin._save("foo", "bar")

    assert stored["content"] == "<p>* old: one</p><ul><li>foo: bar</li></ul>"
