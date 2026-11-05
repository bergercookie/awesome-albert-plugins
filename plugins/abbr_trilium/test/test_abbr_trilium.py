"""Tests for the abbr_trilium plugin."""

from conftest import load_plugin

trilium = load_plugin("abbr_trilium")


class _Response:
    status_code = 200
    text = "<p>* foo: first</p>"

    def json(self):
        return {"type": "text"}


def test_join_url_keeps_a_reverse_proxy_prefix():
    assert trilium.join_url("https://host/trilium", "etapi/notes/abc") == (
        "https://host/trilium/etapi/notes/abc"
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


def test_append_abbreviation_writes_html_for_text_notes():
    line = trilium.abbreviation_line("foo", "A & B")
    assert trilium.append_abbreviation("<p>* old: one</p>", "text", line) == (
        "<p>* old: one</p><p>* foo: A &amp; B</p>"
    )


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
        "note_id",
        "verify_ssl",
    }


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

    assert stored["content"] == "<p>* old: one</p><p>* foo: bar</p>"
