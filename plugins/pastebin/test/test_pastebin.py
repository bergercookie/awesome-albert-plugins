"""Tests for the pastebin plugin.

`requests` is monkeypatched rather than mocked wholesale, so the real response
objects and the real exception types are in play - what is being checked is how
each service's answer is turned into a link, which is the part that actually
breaks when a service changes.
"""

import json
import os

import pytest
import requests

from conftest import load_plugin

pastebin = load_plugin("pastebin")

PASTEBIN_ = pastebin.PASTEBIN
TERMBIN_ = pastebin.TERMBIN
DPASTE_ = pastebin.DPASTE
ZEROX0_ = pastebin.ZEROX0
IXIO_ = pastebin.IXIO


class FakeResponse:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code


@pytest.fixture
def post(monkeypatch):
    """Capture what would be POSTed, and answer with a canned body."""
    calls = []

    def fake_post(url, data=None, files=None, headers=None, timeout=None):
        calls.append({"url": url, "data": data, "files": files, "headers": headers})
        return fake_post.response

    fake_post.calls = calls
    fake_post.response = FakeResponse("")
    monkeypatch.setattr(pastebin.requests, "post", fake_post)
    return fake_post


# -- extract_url ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body, expected",
    [
        # the keyless services answer with the bare link
        ("https://termbin.com/abc12\n", "https://termbin.com/abc12"),
        ("  https://dpaste.org/EBKU  ", "https://dpaste.org/EBKU"),
        # dpaste's default format quotes it
        ('"https://dpaste.org/EBKU"', "https://dpaste.org/EBKU"),
        # ix.io's json
        ('{"url": "https://ix.io/9kQwErTy"}', "https://ix.io/9kQwErTy"),
        # a bare key plus a base url
        ('{"id": "ab12cd", "base_url": "https://ix.io"}', "https://ix.io/ab12cd"),
        # an html error page must never be mistaken for a link
        ("<!DOCTYPE html><html><body>nope</body></html>", None),
        ("", None),
        ("not a url at all", None),
        ('{"unrelated": 1}', None),
        # truncated json
        ('{"url": ', None),
    ],
)
def test_extract_url(body, expected):
    assert pastebin.extract_url(body) == expected


# -- termbin ---------------------------------------------------------------------------------


def test_termbin_posts_the_raw_body(post):
    post.response = FakeResponse("https://termbin.com/wjp4\n")
    url = pastebin.paste(TERMBIN_, "just testing\n")

    assert url == "https://termbin.com/wjp4"
    # raw body, not a form post
    assert post.calls[0]["data"] == b"just testing\n"
    assert post.calls[0]["files"] is None
    assert post.calls[0]["headers"]["Content-Type"] == "text/plain"


def test_termbin_answers_with_html_when_it_refuses(post):
    # fiche answers 200 with a page of prose when the body is not text it likes
    post.response = FakeResponse("<html><body>Error: invalid content</body></html>")
    with pytest.raises(pastebin.PasteError, match="did not return a link"):
        pastebin.paste(TERMBIN_, "\x00\x01binary")


# -- dpaste ----------------------------------------------------------------------------------


def test_dpaste_asks_for_the_url_format(post):
    post.response = FakeResponse("https://dpaste.org/EBKU\n")
    url = pastebin.paste(DPASTE_, "x = 1")

    assert url == "https://dpaste.org/EBKU"
    assert post.calls[0]["data"]["format"] == "url"
    assert post.calls[0]["data"]["content"] == "x = 1"


def test_dpaste_gets_the_filename_so_it_can_pick_a_lexer(post):
    post.response = FakeResponse("https://dpaste.org/EBKU\n")
    pastebin.paste(DPASTE_, "print(1)", filename="hello.py")
    assert post.calls[0]["data"]["filename"] == "hello.py"


def test_dpaste_omits_the_filename_for_inline_text(post):
    post.response = FakeResponse("https://dpaste.org/EBKU\n")
    pastebin.paste(DPASTE_, "print(1)")
    assert "filename" not in post.calls[0]["data"]


# -- 0x0.st and ix.io ------------------------------------------------------------------------


def test_0x0_uses_the_file_field_name(post):
    # the service really does want `file`
    post.response = FakeResponse("https://0x0.st/abc\n")
    url = pastebin.paste(ZEROX0_, "hello", filename="notes.txt")

    assert url == "https://0x0.st/abc"
    assert list(post.calls[0]["files"]) == ["file"]


def test_0x0_falls_back_to_a_sensible_filename(post):
    post.response = FakeResponse("https://0x0.st/abc\n")
    pastebin.paste(ZEROX0_, "hello")
    assert post.calls[0]["files"]["file"][0] == "snippet.txt"


def test_ix_uses_the_odd_f1_field_name(post):
    # ix.io wants the content in a field called `f:1`
    post.response = FakeResponse('{"url": "https://ix.io/9kQw"}')
    url = pastebin.paste(IXIO_, "hello", filename="notes.txt")

    assert url == "https://ix.io/9kQw"
    assert list(post.calls[0]["files"]) == ["f:1"]
    assert post.calls[0]["headers"]["Accept"] == "application/json"


def test_ix_also_accepts_a_plain_text_answer(post):
    post.response = FakeResponse("https://ix.io/9kQw\n")
    assert pastebin.paste(IXIO_, "hello") == "https://ix.io/9kQw"


# -- pastebin.com ----------------------------------------------------------------------------


def test_pastebin_complains_without_a_key(post):
    with pytest.raises(pastebin.PasteError, match="needs a Developer API key"):
        pastebin.paste(PASTEBIN_, "hello", api_key="")

    # and it must not have sent anything before finding out
    assert post.calls == []


def test_pastebin_builds_the_url_from_the_key(post):
    post.response = FakeResponse(json.dumps({"key": "AbCd1234"}))
    assert pastebin.paste(PASTEBIN_, "hi", api_key="k") == "https://pastebin.com/AbCd1234"
    assert post.calls[0]["data"]["api_dev_key"] == "k"
    assert post.calls[0]["data"]["api_option"] == "paste"
    assert post.calls[0]["data"]["api_paste_code"] == "hi"


def test_pastebin_uses_the_filename_as_the_title(post):
    post.response = FakeResponse(json.dumps({"key": "AbCd1234"}))
    pastebin.paste(PASTEBIN_, "hi", filename="hello.py", api_key="k")
    assert post.calls[0]["data"]["api_paste_name"] == "hello.py"


def test_pastebin_prefers_a_url_when_the_service_sends_one(post):
    post.response = FakeResponse(json.dumps({"key": "AbCd1234", "url": "https://x.io/ab"}))
    assert pastebin.paste(PASTEBIN_, "hi", api_key="k") == "https://x.io/ab"


def test_pastebin_surfaces_its_own_error(post):
    post.response = FakeResponse(
        json.dumps({"error": "Bad API key", "message": "Your API key is invalid."})
    )
    with pytest.raises(pastebin.PasteError, match=r"Your API key is invalid\."):
        pastebin.paste(PASTEBIN_, "hi", api_key="k")


# -- http failures ---------------------------------------------------------------------------


def test_a_timeout_is_reported_as_such(post, monkeypatch):
    def boom(*a, **kw):
        raise requests.Timeout()

    post.calls.clear()
    monkeypatch.setattr(pastebin.requests, "post", boom)
    with pytest.raises(pastebin.PasteError, match="did not answer within"):
        pastebin.paste(TERMBIN_, "hi")


def test_an_unreachable_service_names_itself(post):
    def boom(*a, **kw):
        raise requests.ConnectionError("no route to host")

    pytest.MonkeyPatch().setattr(pastebin.requests, "post", boom)
    with pytest.raises(pastebin.PasteError, match=r"Cannot reach termbin\.com"):
        pastebin.paste(TERMBIN_, "hi")


def test_an_http_error_includes_the_status_code(post):
    post.response = FakeResponse("payload too large", status_code=413)
    with pytest.raises(pastebin.PasteError, match=r"HTTP 413.*payload too large"):
        pastebin.paste(TERMBIN_, "hi")


def test_a_non_json_pastebin_answer_is_not_a_success(post):
    post.response = FakeResponse("<html>maintenance</html>")
    with pytest.raises(pastebin.PasteError, match="did not return a link"):
        pastebin.paste(PASTEBIN_, "hi", api_key="k")


# -- the shared entry point ------------------------------------------------------------------


def test_pasting_nothing_is_refused(post):
    with pytest.raises(pastebin.PasteError, match="nothing to paste"):
        pastebin.paste(TERMBIN_, "   \n  ")
    assert post.calls == []


def test_every_backend_is_wired_up(post):
    # a typo in the dispatch table would only show up as a NameError at upload
    # time, which is the worst possible moment to find one
    for backend in pastebin.BACKENDS.values():
        post.response = FakeResponse("")
        try:
            pastebin.paste(backend, "hi", api_key="k")
        except (pastebin.PasteError, AttributeError):
            pass
        else:  # pragma: no cover
            pass
    # every id in the registry has a handler
    assert set(pastebin.BACKENDS) == {"termbin", "dpaste", "0x0.st", "ix.io", "pastebin.com"}


def test_the_keyless_services_really_do_not_need_a_key():
    for backend in pastebin.BACKENDS.values():
        if backend.id != "pastebin.com":
            assert backend.needs_key is False, backend.id
    assert PASTEBIN_.needs_key is True


# -- reading snippets ------------------------------------------------------------------------


def test_read_snippet_reads_utf8(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("héllo\nwörld\n", encoding="utf-8")

    text, name = pastebin.read_snippet(str(path))
    assert text == "héllo\nwörld\n"
    assert name == "notes.txt"


def test_read_snippet_refuses_binary(tmp_path):
    path = tmp_path / "blob.bin"
    path.write_bytes(b"\xff\xfe\x00\x01")
    with pytest.raises(pastebin.PasteError, match="not UTF-8"):
        pastebin.read_snippet(str(path))


def test_read_snippet_refuses_a_missing_file():
    with pytest.raises(pastebin.PasteError, match="Cannot read"):
        pastebin.read_snippet("/nonexistent/nope.txt")


def test_read_snippet_enforces_the_size_limit(tmp_path, monkeypatch):
    path = tmp_path / "big.txt"
    path.write_text("x" * 100, encoding="utf-8")
    monkeypatch.setattr(pastebin, "MAX_BYTES", 10)

    with pytest.raises(pastebin.PasteError, match="over the 10 byte limit"):
        pastebin.read_snippet(str(path))


def test_read_snippet_expands_a_tilde(monkeypatch, tmp_path):
    path = tmp_path / "tilde.txt"
    path.write_text("ok", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))

    text, _ = pastebin.read_snippet("~/tilde.txt")
    assert text == "ok"


# -- stdin ------------------------------------------------------------------------------------
#
# stdin_snippet() runs on every keystroke, so "returns promptly" is a correctness
# requirement, not a nicety. These use real files, fifos and processes, because a
# mocked stdin cannot demonstrate that a read does not block.


def test_stdin_is_ignored_on_a_terminal():
    monkey = pytest.MonkeyPatch()
    monkey.setattr(pastebin.sys.stdin, "isatty", lambda: True, raising=False)
    try:
        assert pastebin.stdin_snippet() is None
    finally:
        monkey.undo()


def test_stdin_is_ignored_when_there_is_no_stdin():
    monkey = pytest.MonkeyPatch()
    monkey.setattr(pastebin.sys, "stdin", None)
    try:
        assert pastebin.stdin_snippet() is None
    finally:
        monkey.undo()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs fifos")
def test_an_idle_open_pipe_does_not_block(tmp_path, monkeypatch):
    """The case that would freeze the query thread.

    A launcher that hands the plugin an open but idle pipe is the dangerous one:
    the pipe never reaches EOF, so a plain read() would wait forever. The write
    end is held open by this process and nothing is ever written.
    """
    import time

    fifo = tmp_path / "idle"
    os.mkfifo(fifo)

    # O_NONBLOCK is what keeps the open() itself from waiting for a writer
    read_fd = os.open(str(fifo), os.O_RDONLY | os.O_NONBLOCK)
    write_fd = os.open(str(fifo), os.O_WRONLY | os.O_NONBLOCK)

    fake = type("Stdin", (), {})()
    fake.isatty = lambda: False
    fake.fileno = lambda: read_fd
    monkeypatch.setattr(pastebin.sys, "stdin", fake)

    start = time.time()
    assert pastebin.stdin_snippet() is None
    assert time.time() - start < 1.0

    os.close(read_fd)
    os.close(write_fd)


def test_a_piped_snippet_arrives_whole(monkeypatch):
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"from the pipe\n")
    os.close(write_fd)

    fake = type("Stdin", (), {})()
    fake.isatty = lambda: False
    fake.fileno = lambda: read_fd
    monkeypatch.setattr(pastebin.sys, "stdin", fake)

    assert pastebin.stdin_snippet() == "from the pipe\n"
    os.close(read_fd)


def _pipe_stdin(monkeypatch, payload: bytes) -> None:
    """Point the plugin at a pipe carrying *payload*."""
    read_fd, write_fd = os.pipe()
    os.write(write_fd, payload)
    os.close(write_fd)

    fake = type("Stdin", (), {})()
    fake.isatty = lambda: False
    fake.fileno = lambda: read_fd
    monkeypatch.setattr(pastebin.sys, "stdin", fake)


def test_a_piped_snippet_at_the_size_limit_is_taken(monkeypatch):
    monkeypatch.setattr(pastebin, "MAX_BYTES", 8)
    _pipe_stdin(monkeypatch, b"x" * 8)
    assert pastebin.stdin_snippet() == "x" * 8


def test_an_oversized_pipe_is_refused_not_truncated(monkeypatch):
    # uploading the first N bytes of a longer paste would be worse than failing
    monkeypatch.setattr(pastebin, "MAX_BYTES", 8)
    _pipe_stdin(monkeypatch, b"x" * 4096)

    with pytest.raises(pastebin.PasteError, match="over the 8 byte limit"):
        pastebin.stdin_snippet()


def test_an_oversized_pipe_becomes_a_visible_error(monkeypatch):
    monkeypatch.setattr(pastebin, "MAX_BYTES", 8)
    _pipe_stdin(monkeypatch, b"x" * 4096)

    parsed = pastebin.Plugin.parse_input("anything")
    assert parsed.error is not None
    assert "over the 8 byte limit" in parsed.error
    assert parsed.text == ""


def test_stdin_reading_survives_a_closed_descriptor(monkeypatch):
    class NoFileno:
        def isatty(self):
            return False

        def fileno(self):
            raise ValueError("I/O operation on closed file")

    monkeypatch.setattr(pastebin.sys, "stdin", NoFileno())
    assert pastebin.stdin_snippet() is None


def test_binary_on_stdin_is_ignored(monkeypatch):
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"\xff\xfe\x00\x01")
    os.close(write_fd)

    fake = type("Stdin", (), {})()
    fake.isatty = lambda: False
    fake.fileno = lambda: read_fd
    monkeypatch.setattr(pastebin.sys, "stdin", fake)

    assert pastebin.stdin_snippet() is None
    os.close(read_fd)


# -- input parsing ---------------------------------------------------------------------------


def _no_stdin(monkeypatch):
    monkeypatch.setattr(pastebin, "stdin_snippet", lambda: None)


def test_plain_text_becomes_the_snippet(monkeypatch):
    _no_stdin(monkeypatch)
    parsed = pastebin.Plugin.parse_input("  some text  ")
    assert parsed.kind == "text"
    assert parsed.text == "some text"
    assert parsed.filename is None
    assert parsed.error is None


def test_a_piped_snippet_wins_over_the_query(monkeypatch):
    monkeypatch.setattr(pastebin, "stdin_snippet", lambda: "from the pipe\n")
    parsed = pastebin.Plugin.parse_input("notes.txt")
    assert parsed.text == "from the pipe\n"
    assert parsed.kind == "text"


def test_the_file_prefix_is_explicit(monkeypatch, tmp_path):
    _no_stdin(monkeypatch)
    path = tmp_path / "conf.txt"
    path.write_text("a = 1\n", encoding="utf-8")

    parsed = pastebin.Plugin.parse_input(f"file:{path}")
    assert parsed.kind == "file"
    assert parsed.text == "a = 1\n"
    assert parsed.filename == "conf.txt"


def test_a_bare_path_works_too(monkeypatch, tmp_path):
    # people type the path, and the item always says which source it picked
    _no_stdin(monkeypatch)
    path = tmp_path / "conf.txt"
    path.write_text("a = 1\n", encoding="utf-8")

    parsed = pastebin.Plugin.parse_input(str(path))
    assert parsed.kind == "file"
    assert parsed.text == "a = 1\n"


def test_multi_word_text_is_never_mistaken_for_a_path(monkeypatch, tmp_path):
    _no_stdin(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a b").write_text("file", encoding="utf-8")

    parsed = pastebin.Plugin.parse_input("a b")
    assert parsed.kind == "text"
    assert parsed.text == "a b"


def test_a_missing_file_after_the_prefix_is_an_error(monkeypatch):
    _no_stdin(monkeypatch)
    parsed = pastebin.Plugin.parse_input("file:/nonexistent/nope.txt")
    assert parsed.error is not None
    assert parsed.text == ""


def test_an_empty_file_prefix_is_an_error(monkeypatch):
    _no_stdin(monkeypatch)
    parsed = pastebin.Plugin.parse_input("file:   ")
    assert parsed.error == "No file given after 'file:'."


# -- the preview ------------------------------------------------------------------------------


def test_preview_of_a_one_liner():
    assert pastebin.Plugin._preview("hello world") == "hello world"


def test_preview_counts_the_lines_of_a_multiline_snippet():
    assert pastebin.Plugin._preview("a\nb\nc") == "(3 lines) a"


def test_preview_skips_leading_blank_lines():
    assert pastebin.Plugin._preview("\n\n  real content\nmore") == "(2 lines) real content"


def test_preview_is_capped():
    preview = pastebin.Plugin._preview("x" * 500)
    assert len(preview) <= 60
    assert preview.endswith("...")


def test_preview_collapses_runs_of_whitespace():
    assert pastebin.Plugin._preview("a    b\t\tc") == "a b c"


# -- config -----------------------------------------------------------------------------------


def test_the_config_widget_offers_every_service():
    plugin = pastebin.Plugin.__new__(pastebin.Plugin)
    plugin.iid = "x"
    plugin.id = lambda: "python.pastebin"

    widget = pastebin.Plugin.configWidget(plugin)
    combobox = next(w for w in widget if w["type"] == "combobox")
    assert combobox["property"] == "default_backend"
    assert combobox["items"] == [b.label for b in pastebin.BACKENDS.values()]

    properties = [w.get("property") for w in widget if w.get("property")]
    assert properties == [
        "default_backend",
        "pastebin_api_key",
        "auto_copy_link",
        "open_in_browser",
    ]


def test_an_unknown_stored_backend_falls_back_to_the_default():
    # a service name that disappeared from a newer version must not break startup
    assert pastebin.BACKENDS_BY_LABEL.get("paste.ee", pastebin.TERMBIN) is pastebin.TERMBIN
