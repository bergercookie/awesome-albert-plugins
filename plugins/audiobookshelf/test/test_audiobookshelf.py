"""Tests for the audiobookshelf plugin.

`requests` is monkeypatched rather than mocked wholesale, so the real response
bodies and the real exception types are in play: what is checked is how an
Audiobookshelf answer - including the ugly ones - is turned into an item, and
that is the part that breaks when the server changes.

The plugin talks to exactly one server, so nothing here reaches out. The
high-level API helpers are monkeypatched for the item tests; `call` itself is
driven through a fake `requests.request` so its header, parameter and error
handling are exercised for real.
"""

import subprocess
import threading
import time

import albert
import pytest
import requests

from conftest import load_plugin

audiobookshelf = load_plugin("audiobookshelf")

BASE = "http://abs:13378"
TOKEN = "secret-key"


# -- harness ---------------------------------------------------------------------------------


def completed(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


class FakeResponse:
    def __init__(self, payload=None, status=200, text="", json_error=False):
        self.payload = payload
        self.status_code = status
        self.text = text
        self.json_error = json_error

    def json(self):
        if self.json_error:
            raise ValueError("not json")
        return self.payload


@pytest.fixture
def http(monkeypatch):
    """A stand-in for `requests.request` that records what it was handed."""

    class HTTP:
        def __init__(self):
            self.calls = []
            self.response = FakeResponse({})

        def __call__(self, method, url, **kwargs):
            self.calls.append({"method": method, "url": url, **kwargs})
            if isinstance(self.response, Exception):
                raise self.response
            return self.response

    handler = HTTP()
    monkeypatch.setattr(audiobookshelf.requests, "request", handler)
    return handler


class Api:
    """A stand-in for the module-level `call`, recording the API calls made."""

    def __init__(self):
        self.calls = []
        self.reply = {}

    def __call__(self, method, base_url, token, path, params=None, timeout=None):
        self.calls.append(
            {
                "method": method,
                "base_url": base_url,
                "token": token,
                "path": path,
                "params": params,
                "timeout": timeout,
            }
        )
        return self.reply


@pytest.fixture
def api(monkeypatch):
    """A stand-in for `call`, so the fetch helpers are tested on their own."""
    handler = Api()
    monkeypatch.setattr(audiobookshelf, "call", handler)
    return handler


@pytest.fixture(autouse=True)
def clean_albert_state():
    """Notification.SENT and the config store are class-level, so reset them."""
    sent = list(albert.Notification.SENT)
    config = dict(albert.PluginInstance._CONFIG)
    albert.Notification.SENT.clear()
    albert.PluginInstance._CONFIG.clear()
    yield
    albert.Notification.SENT.clear()
    albert.Notification.SENT.extend(sent)
    albert.PluginInstance._CONFIG.clear()
    albert.PluginInstance._CONFIG.update(config)


@pytest.fixture
def instant(monkeypatch):
    """Skip the search debounce so the item tests do not sleep."""

    def still(ctx, delay=0):
        return bool(ctx.isValid)

    monkeypatch.setattr(audiobookshelf.Plugin, "_wait_for_still_input", staticmethod(still))


class FakeCtx:
    def __init__(self, query, valid=True):
        self.query = query
        self.isValid = valid


def make_plugin(url=BASE, token=TOKEN, command="", player="cvlc"):
    """A plugin instance without going through __init__ (no config, no disk)."""
    plugin = audiobookshelf.Plugin.__new__(audiobookshelf.Plugin)
    plugin._url = url
    plugin._token = token
    plugin._token_command = command
    plugin._player = player
    plugin._lock = threading.Lock()
    plugin._libraries = None
    plugin._searches = {}
    plugin._resolved_token = None
    return plugin


def wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return bool(predicate())


# -- payloads --------------------------------------------------------------------------------


def library(library_id="lib1", media_type="book", name="Audiobooks"):
    return {"id": library_id, "name": name, "mediaType": media_type}


def expanded_item(
    item_id="item1",
    title="The Way of Kings",
    author="Brandon Sanderson",
    narrator="Michael Kramer",
    series="The Stormlight Archive",
    year=2010,
    duration=3600,
    track_ids=(1, 2),
):
    """A book-search hit: flat metadata and a `tracks` list."""
    return {
        "id": item_id,
        "media": {
            "metadata": {
                "title": title,
                "authorName": author,
                "narratorName": narrator,
                "seriesName": series,
                "publishedYear": year,
            },
            "duration": duration,
            "tracks": [
                {
                    "ino": ino,
                    "contentUrl": f"/api/items/{item_id}/file/{ino}",
                }
                for ino in track_ids
            ],
        },
    }


def minified_item(item_id="item2", title="Words of Radiance"):
    """A listing row: flat metadata, and neither `tracks` nor `audioFiles`."""
    return {
        "id": item_id,
        "media": {
            "metadata": {
                "title": title,
                "authorName": "Brandon Sanderson",
                "narratorName": "Michael Kramer",
                "seriesName": "The Stormlight Archive",
                "publishedYear": 2014,
            },
            "duration": 7200,
        },
    }


def old_item(item_id="item3", title="Edgedancer"):
    """An old-style item: array metadata and `audioFiles` instead of `tracks`."""
    return {
        "id": item_id,
        "media": {
            "metadata": {
                "title": title,
                "authors": [{"name": "Brandon Sanderson"}],
                "narrators": ["Kate Reading"],
                "series": [{"name": "The Stormlight Archive"}],
                "publishedYear": 2016,
            },
            "duration": 1800,
            "audioFiles": [{"ino": 7}, {"ino": 8}],
        },
    }


def search_payload(items=(), series=(), authors=()):
    return {
        "book": [{"libraryItem": item} for item in items],
        "series": list(series),
        "authors": list(authors),
    }


# -- urls ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "base, path, expected",
    [
        ("http://localhost:13378", "api/libraries", "http://localhost:13378/api/libraries"),
        ("http://localhost:13378/", "/api/libraries", "http://localhost:13378/api/libraries"),
        ("https://host/abs", "item/abc", "https://host/abs/item/abc"),
        # a leading slash on the path must not climb out of a proxy prefix
        ("https://host/abs", "/item/abc", "https://host/abs/item/abc"),
    ],
)
def test_join_url(base, path, expected):
    assert audiobookshelf.join_url(base, path) == expected


def test_home_url_strips_the_trailing_slash():
    assert audiobookshelf.home_url("http://localhost:13378/") == "http://localhost:13378"


def test_item_url_points_at_the_item_page():
    assert audiobookshelf.item_url(BASE, "abc") == f"{BASE}/item/abc"


def test_stream_url_appends_the_token():
    url = audiobookshelf.stream_url(BASE, "/api/items/abc/file/1", TOKEN)
    assert url == f"{BASE}/api/items/abc/file/1?token={TOKEN}"


def test_stream_url_without_a_token_has_no_query():
    url = audiobookshelf.stream_url(BASE, "/api/items/abc/file/1", "")
    assert url == f"{BASE}/api/items/abc/file/1"


# -- call ------------------------------------------------------------------------------------


def test_call_returns_the_decoded_body(http):
    http.response = FakeResponse({"libraries": []})
    assert audiobookshelf.call("GET", BASE, TOKEN, "api/libraries") == {"libraries": []}


def test_call_sends_a_bearer_token_and_user_agent(http):
    audiobookshelf.call("GET", BASE, TOKEN, "api/libraries")

    call = http.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == f"{BASE}/api/libraries"
    assert call["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert call["headers"]["Accept"] == "application/json"
    assert "User-Agent" in call["headers"]
    assert call["timeout"] == audiobookshelf.HTTP_TIMEOUT


def test_call_encodes_params_with_quote(http):
    params = {"q": "C++ & x"}
    audiobookshelf.call("GET", BASE, TOKEN, "api/libraries/lib1/search", params=params)
    assert http.calls[0]["url"] == f"{BASE}/api/libraries/lib1/search?q=C%2B%2B%20%26%20x"


def test_call_omits_the_query_when_there_are_no_params(http):
    audiobookshelf.call("GET", BASE, TOKEN, "api/libraries")
    assert http.calls[0]["url"] == f"{BASE}/api/libraries"


def test_call_with_an_empty_param_dict_adds_no_query(http):
    audiobookshelf.call("GET", BASE, TOKEN, "api/libraries", params={})
    assert http.calls[0]["url"] == f"{BASE}/api/libraries"


def test_call_refuses_an_empty_url(http):
    with pytest.raises(audiobookshelf.AudiobookshelfError, match="No Audiobookshelf URL"):
        audiobookshelf.call("GET", "", TOKEN, "api/libraries")
    assert http.calls == []


def test_call_refuses_a_url_without_a_scheme(http):
    with pytest.raises(audiobookshelf.AudiobookshelfError, match="not a full URL"):
        audiobookshelf.call("GET", "localhost:13378", TOKEN, "api/libraries")
    assert http.calls == []


def test_call_reports_a_timeout(http):
    http.response = requests.Timeout()
    with pytest.raises(audiobookshelf.AudiobookshelfError, match="did not answer within 10s"):
        audiobookshelf.call("GET", BASE, TOKEN, "api/libraries")


def test_call_reports_an_unreachable_server(http):
    http.response = requests.ConnectionError("no route to host")
    with pytest.raises(audiobookshelf.AudiobookshelfError, match=f"Cannot reach {BASE}"):
        audiobookshelf.call("GET", BASE, TOKEN, "api/libraries")


def test_call_handles_a_204(http):
    http.response = FakeResponse(status=204)
    assert audiobookshelf.call("DELETE", BASE, TOKEN, "api/items/1") is None


def test_call_surfaces_a_non_json_body(http):
    http.response = FakeResponse(json_error=True, status=200)
    with pytest.raises(audiobookshelf.AudiobookshelfError, match="did not answer with JSON"):
        audiobookshelf.call("GET", BASE, TOKEN, "api/libraries")


def test_call_explains_a_401_with_the_auth_error(http):
    http.response = FakeResponse({"error": "Unauthorized"}, status=401)
    with pytest.raises(audiobookshelf.AudiobookshelfError) as exc:
        audiobookshelf.call("GET", BASE, TOKEN, "api/libraries")

    message = str(exc.value)
    assert "HTTP 401" in message
    assert "Unauthorized" in message
    assert "Check the API key" in message


def test_call_surfaces_a_service_message(http):
    http.response = FakeResponse({"message": "Library not found"}, status=404)
    with pytest.raises(audiobookshelf.AudiobookshelfError) as exc:
        audiobookshelf.call("GET", BASE, TOKEN, "api/libraries/nope")

    message = str(exc.value)
    assert "HTTP 404" in message
    assert "Library not found" in message
    # a 404 is not a credentials problem, so the key hint must not be there
    assert "API key" not in message


def test_call_quotes_an_html_error_page(http):
    http.response = FakeResponse(
        json_error=True, status=502, text="<html>\n  <body>Bad Gateway</body>\n</html>"
    )
    with pytest.raises(audiobookshelf.AudiobookshelfError, match=r"HTTP 502.*Bad Gateway"):
        audiobookshelf.call("GET", BASE, TOKEN, "api/libraries")


# -- resolve_api_key -------------------------------------------------------------------------


def test_resolve_api_key_prefers_the_plaintext_key():
    assert audiobookshelf.resolve_api_key("  plain  ", "") == "plain"
    assert audiobookshelf.resolve_api_key("  plain  ", "   ") == "plain"


def test_resolve_api_key_runs_the_command(monkeypatch):
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["shell"] = kwargs.get("shell")
        return completed(stdout="  key123\n")

    monkeypatch.setattr(audiobookshelf.subprocess, "run", fake_run)

    assert audiobookshelf.resolve_api_key("ignored", "pass show abs") == "key123"
    assert seen["command"] == "pass show abs"
    assert seen["shell"] is True


def test_resolve_api_key_command_wins_over_the_plaintext_key(monkeypatch):
    monkeypatch.setattr(
        audiobookshelf.subprocess,
        "run",
        lambda command, **kwargs: completed(stdout="from-command"),
    )
    assert audiobookshelf.resolve_api_key("plaintext", "echo x") == "from-command"


def test_resolve_api_key_reports_a_failed_command(monkeypatch):
    monkeypatch.setattr(
        audiobookshelf.subprocess,
        "run",
        lambda command, **kwargs: completed(returncode=1, stderr="keyring is locked\n"),
    )
    with pytest.raises(audiobookshelf.AudiobookshelfError, match=r"failed.*keyring is locked"):
        audiobookshelf.resolve_api_key("", "rbw get abs")


def test_resolve_api_key_reports_a_command_that_hangs(monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, audiobookshelf.KEY_COMMAND_TIMEOUT)

    monkeypatch.setattr(audiobookshelf.subprocess, "run", fake_run)
    with pytest.raises(audiobookshelf.AudiobookshelfError, match="took longer"):
        audiobookshelf.resolve_api_key("", "sleep 100")


def test_resolve_api_key_refuses_empty_output(monkeypatch):
    monkeypatch.setattr(
        audiobookshelf.subprocess, "run", lambda command, **kwargs: completed(stdout="  \n")
    )
    with pytest.raises(audiobookshelf.AudiobookshelfError, match="printed nothing"):
        audiobookshelf.resolve_api_key("", "true")


def test_resolve_api_key_reports_a_command_that_will_not_start(monkeypatch):
    def fake_run(command, **kwargs):
        raise OSError("exec format error")

    monkeypatch.setattr(audiobookshelf.subprocess, "run", fake_run)
    with pytest.raises(audiobookshelf.AudiobookshelfError, match="Could not run"):
        audiobookshelf.resolve_api_key("", "some-missing-binary")


# -- fetch_libraries -------------------------------------------------------------------------


def test_fetch_libraries_returns_the_libraries(api):
    api.reply = {"libraries": [library("a"), library("b")]}
    assert audiobookshelf.fetch_libraries(BASE, TOKEN) == [library("a"), library("b")]
    assert api.calls[0]["path"] == "api/libraries"


def test_fetch_libraries_drops_junk_rows(api):
    api.reply = {"libraries": [library("a"), "nope", 42, None]}
    assert audiobookshelf.fetch_libraries(BASE, TOKEN) == [library("a")]


def test_fetch_libraries_rejects_an_unexpected_body(api):
    api.reply = {"nonsense": True}
    with pytest.raises(audiobookshelf.AudiobookshelfError, match="something unexpected"):
        audiobookshelf.fetch_libraries(BASE, TOKEN)


def test_fetch_audiobook_libraries_keeps_only_books(api):
    api.reply = {"libraries": [library("a"), library("p", media_type="podcast")]}
    assert audiobookshelf.fetch_audiobook_libraries(BASE, TOKEN) == [library("a")]


# -- fetch_library_search --------------------------------------------------------------------


def test_fetch_library_search_returns_the_payload(api):
    api.reply = search_payload(items=[expanded_item("i1")])
    assert audiobookshelf.fetch_library_search(BASE, TOKEN, "lib1", "storm") == api.reply
    assert api.calls[0]["path"] == "api/libraries/lib1/search"
    assert api.calls[0]["params"] == {"q": "storm", "limit": audiobookshelf.SEARCH_LIMIT}


def test_fetch_library_search_rejects_an_unexpected_body(api):
    api.reply = None
    with pytest.raises(audiobookshelf.AudiobookshelfError, match="something unexpected"):
        audiobookshelf.fetch_library_search(BASE, TOKEN, "lib1", "storm")


# -- fetch_author_items ----------------------------------------------------------------------


def test_fetch_author_items_returns_the_results(api):
    api.reply = {"results": [minified_item("i1"), "nope", None]}
    assert audiobookshelf.fetch_author_items(BASE, TOKEN, "lib1", "a1") == [
        minified_item("i1")
    ]
    assert api.calls[0]["path"] == "api/libraries/lib1/items"
    assert api.calls[0]["params"] == {
        "filter": "authors.a1",
        "limit": audiobookshelf.SEARCH_LIMIT,
    }


def test_fetch_author_items_rejects_an_unexpected_body(api):
    api.reply = {"nonsense": True}
    with pytest.raises(audiobookshelf.AudiobookshelfError, match="something unexpected"):
        audiobookshelf.fetch_author_items(BASE, TOKEN, "lib1", "a1")


# -- fetch_item ------------------------------------------------------------------------------


def test_fetch_item_asks_for_the_expanded_item(api):
    api.reply = expanded_item("i1")
    assert audiobookshelf.fetch_item(BASE, TOKEN, "i1") == expanded_item("i1")
    assert api.calls[0]["path"] == "api/items/i1"
    assert api.calls[0]["params"] == {"expanded": "1"}


def test_fetch_item_rejects_an_unexpected_body(api):
    api.reply = []
    with pytest.raises(audiobookshelf.AudiobookshelfError, match="something unexpected"):
        audiobookshelf.fetch_item(BASE, TOKEN, "i1")


def test_fetch_item_detail_refetches_by_id(api):
    api.reply = expanded_item("i9")
    detail = audiobookshelf.fetch_item_detail(BASE, TOKEN, minified_item("i9"))
    assert detail == expanded_item("i9")
    assert api.calls[0]["path"] == "api/items/i9"


def test_fetch_item_detail_refuses_an_item_without_an_id():
    with pytest.raises(audiobookshelf.AudiobookshelfError, match="no id"):
        audiobookshelf.fetch_item_detail(BASE, TOKEN, {"media": {}})


# -- reading the payloads --------------------------------------------------------------------


def test_int_reads_numbers_and_falls_back():
    assert audiobookshelf._int("5") == 5
    assert audiobookshelf._int(None, 7) == 7
    assert audiobookshelf._int("x") == 0


def test_list_wraps_only_lists():
    assert audiobookshelf._list([1]) == [1]
    assert audiobookshelf._list(None) == []
    assert audiobookshelf._list("x") == []


def test_item_id_is_a_string_or_none():
    assert audiobookshelf.item_id({"id": "a"}) == "a"
    assert audiobookshelf.item_id({}) is None


def test_item_title_reads_the_metadata_then_a_stand_in():
    assert audiobookshelf.item_title(expanded_item(title="Dune")) == "Dune"
    assert audiobookshelf.item_title({"media": {}}) == "Untitled audiobook"


def test_item_author_reads_the_flat_field():
    assert audiobookshelf.item_author(expanded_item(author="Le Guin")) == "Le Guin"


def test_item_author_falls_back_to_the_authors_array():
    assert audiobookshelf.item_author(old_item()) == "Brandon Sanderson"


def test_item_narrator_reads_the_flat_field():
    assert audiobookshelf.item_narrator(expanded_item(narrator="Tim Curry")) == "Tim Curry"


def test_item_narrator_falls_back_to_the_array():
    assert audiobookshelf.item_narrator(old_item()) == "Kate Reading"


def test_item_series_reads_the_flat_field():
    assert audiobookshelf.item_series(expanded_item(series="Mistborn")) == "Mistborn"


def test_item_series_falls_back_to_the_array():
    assert audiobookshelf.item_series(old_item()) == "The Stormlight Archive"


def test_item_year_is_a_string():
    assert audiobookshelf.item_year(expanded_item(year=1984)) == "1984"
    assert audiobookshelf.item_year({"media": {}}) == ""


def test_item_duration_is_seconds():
    assert audiobookshelf.item_duration(expanded_item(duration=100)) == 100
    assert audiobookshelf.item_duration({"media": {}}) == 0


@pytest.mark.parametrize(
    "seconds, expected",
    [
        (0, ""),
        (-1, ""),
        (59, "<1m"),
        (60, "1m"),
        (125, "2m"),
        (3600, "1h"),
        (3720, "1h 2m"),
        (86400, "24h"),
    ],
)
def test_format_duration(seconds, expected):
    assert audiobookshelf.format_duration(seconds) == expected


def test_item_subtext_describes_the_audiobook():
    assert audiobookshelf.item_subtext(expanded_item()) == (
        "Brandon Sanderson | narrated by Michael Kramer | The Stormlight Archive | 2010 | 1h"
    )


def test_item_subtext_leaves_a_repeated_narrator_out():
    item = expanded_item(author="Neil Gaiman", narrator="Neil Gaiman")
    subtext = audiobookshelf.item_subtext(item)
    assert subtext.startswith("Neil Gaiman | The Stormlight Archive")
    assert "narrated by" not in subtext


def test_item_subtext_of_a_bare_item_is_empty():
    assert audiobookshelf.item_subtext({"media": {}}) == ""


def test_item_tracks_reads_the_tracks_list():
    assert audiobookshelf.item_tracks(expanded_item(track_ids=(1, 2))) == [
        "/api/items/item1/file/1",
        "/api/items/item1/file/2",
    ]


def test_item_tracks_builds_urls_from_audio_files():
    assert audiobookshelf.item_tracks(old_item("item3")) == [
        "/api/items/item3/file/7",
        "/api/items/item3/file/8",
    ]


def test_item_tracks_is_empty_for_a_minified_item():
    assert audiobookshelf.item_tracks(minified_item()) == []


def test_playable_urls_appends_the_token_to_every_track():
    urls = audiobookshelf.playable_urls(BASE, TOKEN, expanded_item(track_ids=(1,)))
    assert urls == [f"{BASE}/api/items/item1/file/1?token={TOKEN}"]


# -- the search payload ----------------------------------------------------------------------


def test_search_payload_items_reads_book_hits():
    payload = search_payload(items=[expanded_item("i1")])
    assert audiobookshelf.search_payload_items(payload) == [expanded_item("i1")]


def test_search_payload_items_unwraps_series_books():
    series = [{"series": {"id": "s1"}, "books": [old_item("i2")]}]
    assert audiobookshelf.search_payload_items(search_payload(series=series)) == [
        old_item("i2")
    ]


def test_search_payload_items_ignores_junk():
    payload = {"book": ["nope", {"libraryItem": "no"}], "series": [None, {"books": [3]}]}
    assert audiobookshelf.search_payload_items(payload) == []


def test_search_payload_authors_returns_id_and_name():
    payload = search_payload(authors=[{"id": "a1", "name": "Sanderson"}])
    assert audiobookshelf.search_payload_authors(payload) == [("a1", "Sanderson")]


def test_search_payload_authors_is_capped():
    authors = [{"id": str(i), "name": "x"} for i in range(10)]
    payload = search_payload(authors=authors)
    assert len(audiobookshelf.search_payload_authors(payload, limit=2)) == 2


def test_search_payload_authors_skips_rows_without_an_id():
    payload = search_payload(authors=[{"name": "x"}])
    assert audiobookshelf.search_payload_authors(payload) == []


def test_dedupe_items_keeps_the_first_of_each_id():
    items = [expanded_item("i1"), expanded_item("i1"), expanded_item("i2")]
    assert [item["id"] for item in audiobookshelf.dedupe_items(items)] == ["i1", "i2"]


def test_dedupe_items_drops_items_without_an_id():
    assert audiobookshelf.dedupe_items([{"media": {}}, expanded_item("i1")]) == [
        expanded_item("i1")
    ]


# -- search_books ----------------------------------------------------------------------------


def test_search_books_merges_libraries_and_follows_authors(monkeypatch):
    payloads = {
        "lib1": search_payload(items=[expanded_item("i1")], authors=[{"id": "a1"}]),
        "lib2": search_payload(items=[expanded_item("i2")]),
    }
    search_calls = []
    author_calls = []

    def fake_search(base, token, library_id, query, limit):
        search_calls.append((library_id, query, limit))
        return payloads[library_id]

    def fake_author(base, token, library_id, author_id, limit):
        author_calls.append((library_id, author_id))
        return [expanded_item("i4")]

    monkeypatch.setattr(audiobookshelf, "fetch_library_search", fake_search)
    monkeypatch.setattr(audiobookshelf, "fetch_author_items", fake_author)

    libs = [library("lib1"), library("lib2")]
    items = audiobookshelf.search_books(BASE, TOKEN, "storm", libs)

    assert [item["id"] for item in items] == ["i1", "i4", "i2"]
    assert search_calls == [
        ("lib1", "storm", audiobookshelf.SEARCH_LIMIT),
        ("lib2", "storm", audiobookshelf.SEARCH_LIMIT),
    ]
    assert author_calls == [("lib1", "a1")]


def test_search_books_caps_the_list(monkeypatch):
    payload = search_payload(items=[expanded_item(f"i{n}") for n in range(5)])
    monkeypatch.setattr(audiobookshelf, "fetch_library_search", lambda *a, **k: payload)

    items = audiobookshelf.search_books(BASE, TOKEN, "storm", [library()], limit=3)
    assert [item["id"] for item in items] == ["i0", "i1", "i2"]


def test_search_books_skips_a_library_without_an_id(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("a library without an id needs no search")

    monkeypatch.setattr(audiobookshelf, "fetch_library_search", boom)

    assert audiobookshelf.search_books(BASE, TOKEN, "storm", [{"mediaType": "book"}]) == []


# -- the player ------------------------------------------------------------------------------


def test_player_argv_splits_the_command():
    assert audiobookshelf.player_argv("cvlc") == ["cvlc"]
    assert audiobookshelf.player_argv("cvlc --play-and-exit") == ["cvlc", "--play-and-exit"]


def test_player_argv_refuses_an_empty_player():
    with pytest.raises(audiobookshelf.AudiobookshelfError, match="No player"):
        audiobookshelf.player_argv("")


def test_launch_player_runs_the_player_on_every_url(monkeypatch):
    seen = {}

    def fake_popen(argv, **kwargs):
        seen["argv"] = argv
        return object()

    monkeypatch.setattr(audiobookshelf.subprocess, "Popen", fake_popen)

    audiobookshelf.launch_player("cvlc", ["u1", "u2"])
    assert seen["argv"] == ["cvlc", "u1", "u2"]


def test_launch_player_refuses_an_empty_playlist():
    with pytest.raises(audiobookshelf.AudiobookshelfError, match="nothing to play"):
        audiobookshelf.launch_player("cvlc", [])


def test_launch_player_reports_a_missing_binary(monkeypatch):
    def fake_popen(argv, **kwargs):
        raise FileNotFoundError("no cvlc")

    monkeypatch.setattr(audiobookshelf.subprocess, "Popen", fake_popen)

    with pytest.raises(audiobookshelf.AudiobookshelfError, match="Could not run"):
        audiobookshelf.launch_player("cvlc", ["u1"])


# -- items: setup ----------------------------------------------------------------------------


def test_a_missing_url_is_asked_for_first():
    plugin = make_plugin(url="", token="")
    (item,) = next(plugin.items(FakeCtx("")))

    assert "Audiobookshelf URL missing" in item.text
    assert item.actions[0].id == "open"


def test_a_missing_key_is_asked_for():
    plugin = make_plugin(url=BASE, token="")
    (item,) = next(plugin.items(FakeCtx("")))

    assert "API key missing" in item.text
    assert BASE in item.subtext


def test_setup_takes_precedence_over_the_query():
    plugin = make_plugin(url="", token="")
    (item,) = next(plugin.items(FakeCtx("storm")))
    assert "settings" in item.text


# -- items: the search -----------------------------------------------------------------------


def test_an_empty_query_only_hints():
    plugin = make_plugin()
    items = next(plugin.items(FakeCtx("")))

    assert "Search your Audiobookshelf library" in items[0].text


def test_a_single_character_only_hints(instant):
    plugin = make_plugin()
    items = next(plugin.items(FakeCtx("d")))

    assert "Search Audiobookshelf for d" in items[0].text


def test_no_audiobook_library_says_so(monkeypatch, instant):
    monkeypatch.setattr(audiobookshelf, "fetch_audiobook_libraries", lambda *a, **k: [])
    plugin = make_plugin()

    items = next(plugin.items(FakeCtx("storm")))
    assert "No audiobook libraries" in items[0].text


def test_a_search_lists_audiobooks(monkeypatch, instant):
    monkeypatch.setattr(
        audiobookshelf, "fetch_audiobook_libraries", lambda *a, **k: [library()]
    )
    monkeypatch.setattr(
        audiobookshelf, "search_books", lambda base, token, term, libraries: [expanded_item()]
    )
    plugin = make_plugin()

    items = next(plugin.items(FakeCtx("storm")))
    assert [item.text for item in items] == ["The Way of Kings"]
    assert items[0].actions[0].id == "play"


def test_a_search_without_hits_says_so(monkeypatch, instant):
    monkeypatch.setattr(
        audiobookshelf, "fetch_audiobook_libraries", lambda *a, **k: [library()]
    )
    monkeypatch.setattr(audiobookshelf, "search_books", lambda *a, **k: [])
    plugin = make_plugin()

    items = next(plugin.items(FakeCtx("zzzz")))
    assert "Nothing in your Audiobookshelf library matches" in items[0].text


def test_a_replaced_query_is_abandoned(monkeypatch):
    monkeypatch.setattr(
        audiobookshelf, "fetch_audiobook_libraries", lambda *a, **k: [library()]
    )
    monkeypatch.setattr(
        audiobookshelf,
        "search_books",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be searched")),
    )
    plugin = make_plugin()

    assert list(plugin.items(FakeCtx("storm", valid=False))) == []


# -- items: errors ---------------------------------------------------------------------------


def test_an_audiobookshelf_error_becomes_a_retry_item(monkeypatch, instant):
    def boom(*args, **kwargs):
        raise audiobookshelf.AudiobookshelfError("the server said no")

    monkeypatch.setattr(audiobookshelf, "fetch_audiobook_libraries", boom)
    plugin = make_plugin()

    items = next(plugin.items(FakeCtx("storm")))
    assert items[0].text == "the server said no"
    assert items[0].actions[0].id == "retry"


def test_an_unexpected_error_becomes_a_crash_item(monkeypatch, instant):
    def boom(*args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(audiobookshelf, "fetch_audiobook_libraries", boom)
    plugin = make_plugin()

    items = next(plugin.items(FakeCtx("storm")))
    assert "Something went wrong" in items[0].text
    assert items[0].actions[0].id == "copy"


# -- caches ----------------------------------------------------------------------------------


def test_the_libraries_are_fetched_once_within_the_ttl(monkeypatch):
    calls = []

    def fake_fetch(*args, **kwargs):
        calls.append(1)
        return [library()]

    monkeypatch.setattr(audiobookshelf, "fetch_audiobook_libraries", fake_fetch)

    plugin = make_plugin()
    plugin._audiobook_libraries()
    plugin._audiobook_libraries()
    assert len(calls) == 1


def test_a_search_is_fetched_once_within_the_ttl(monkeypatch):
    calls = []

    def fake_search(*args, **kwargs):
        calls.append(1)
        return []

    monkeypatch.setattr(audiobookshelf, "search_books", fake_search)

    plugin = make_plugin()
    plugin._search("storm", [library()])
    plugin._search("storm", [library()])
    assert len(calls) == 1


def test_forget_drops_every_cache(monkeypatch):
    monkeypatch.setattr(audiobookshelf, "fetch_audiobook_libraries", lambda *a, **k: [])

    plugin = make_plugin()
    plugin._audiobook_libraries()
    plugin._searches["storm"] = (time.monotonic(), [])

    plugin._forget()

    assert plugin._libraries is None
    assert plugin._searches == {}


def test_the_search_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(audiobookshelf, "SEARCH_CACHE_SIZE", 3)
    monkeypatch.setattr(audiobookshelf, "search_books", lambda *a, **k: [])

    plugin = make_plugin()
    for term in ("a", "b", "c", "d"):
        plugin._search(term, [library()])

    assert len(plugin._searches) == 3
    assert "a" not in plugin._searches


# -- the api key command ---------------------------------------------------------------------


def test_the_plaintext_key_is_used_when_no_command_is_set():
    assert make_plugin(token="plain")._api_key() == "plain"


def test_the_command_key_wins_over_the_plaintext_key(monkeypatch):
    monkeypatch.setattr(
        audiobookshelf.subprocess,
        "run",
        lambda command, **kwargs: completed(stdout="from-command"),
    )
    assert make_plugin(token="plain", command="pass show x")._api_key() == "from-command"


def test_the_command_runs_once_and_the_key_is_cached(monkeypatch):
    calls = []

    def fake_resolve(token, command):
        calls.append((token, command))
        return "from-command"

    monkeypatch.setattr(audiobookshelf, "resolve_api_key", fake_resolve)
    plugin = make_plugin(token="", command="pass show abs")

    assert plugin._api_key() == "from-command"
    assert plugin._api_key() == "from-command"
    assert calls == [("", "pass show abs")]


def test_a_failed_command_is_not_cached(monkeypatch):
    calls = []

    def fake_resolve(token, command):
        calls.append(command)
        if len(calls) == 1:
            raise audiobookshelf.AudiobookshelfError("keyring is locked")
        return "now-unlocked"

    monkeypatch.setattr(audiobookshelf, "resolve_api_key", fake_resolve)
    plugin = make_plugin(token="", command="rbw get x")

    with pytest.raises(audiobookshelf.AudiobookshelfError, match="locked"):
        plugin._api_key()
    # the second try runs the command again and succeeds
    assert plugin._api_key() == "now-unlocked"
    assert len(calls) == 2


def test_the_command_key_is_never_written_to_the_config(monkeypatch):
    monkeypatch.setattr(
        audiobookshelf, "resolve_api_key", lambda token, command: "super-secret"
    )
    plugin = make_plugin(token="", command="pass show x")

    plugin._api_key()
    assert plugin._token == ""
    # nothing was written to Albert's config store, so the key stays in memory
    assert albert.PluginInstance._CONFIG == {}


def test_a_command_satisfies_the_setup_check():
    assert make_plugin(token="", command="pass show x")._setup_item() is None
    assert make_plugin(token="", command="")._setup_item() is not None


def test_the_search_sends_the_command_key(monkeypatch):
    monkeypatch.setattr(
        audiobookshelf, "resolve_api_key", lambda token, command: "command-key"
    )
    seen = {}

    def fake_search(base, token, term, libraries):
        seen["token"] = token
        return []

    monkeypatch.setattr(audiobookshelf, "search_books", fake_search)
    make_plugin(token="", command="pass show x")._search("storm", [library()])
    assert seen["token"] == "command-key"


# -- the play action -------------------------------------------------------------------------


def test_play_refetches_the_item_and_launches_the_player(monkeypatch):
    launched = {}
    monkeypatch.setattr(audiobookshelf, "fetch_item_detail", lambda *a, **k: expanded_item())
    monkeypatch.setattr(
        audiobookshelf,
        "launch_player",
        lambda player, urls: launched.update(player=player, urls=list(urls)),
    )

    make_plugin()._play_worker(minified_item(), "Words of Radiance")

    assert launched["player"] == "cvlc"
    assert launched["urls"] == [
        f"{BASE}/api/items/item1/file/1?token={TOKEN}",
        f"{BASE}/api/items/item1/file/2?token={TOKEN}",
    ]
    assert ("Audiobookshelf", "Playing Words of Radiance") in albert.Notification.SENT


def test_play_uses_the_configured_player(monkeypatch):
    launched = {}
    monkeypatch.setattr(audiobookshelf, "fetch_item_detail", lambda *a, **k: expanded_item())
    monkeypatch.setattr(
        audiobookshelf, "launch_player", lambda player, urls: launched.update(player=player)
    )

    make_plugin(player="mpv")._play_worker(expanded_item(), "X")
    assert launched["player"] == "mpv"


def test_play_reports_an_item_without_audio(monkeypatch):
    monkeypatch.setattr(
        audiobookshelf,
        "fetch_item_detail",
        lambda *a, **k: {"id": "i1", "media": {"metadata": {}, "tracks": []}},
    )

    make_plugin()._play_worker(minified_item(), "Empty")
    assert ("Audiobookshelf", "There is nothing to play.") in albert.Notification.SENT


def test_play_reports_a_missing_player(monkeypatch):
    monkeypatch.setattr(audiobookshelf, "fetch_item_detail", lambda *a, **k: expanded_item())

    make_plugin(player="")._play_worker(minified_item(), "X")

    messages = [text for _title, text in albert.Notification.SENT]
    assert "No player is configured. Add one in the plugin settings." in messages


def test_play_reports_an_item_without_an_id():
    make_plugin()._play_worker({"media": {}}, "X")

    assert wait_for(lambda: any("no id" in text for _title, text in albert.Notification.SENT))


# -- configuration and metadata --------------------------------------------------------------


def test_init_reads_and_strips_the_config():
    config = albert.PluginInstance._CONFIG
    config[("python.mock", audiobookshelf.CONFIG_URL)] = "  http://x  "
    config[("python.mock", audiobookshelf.CONFIG_API_TOKEN)] = "  tok  "
    config[("python.mock", audiobookshelf.CONFIG_API_TOKEN_COMMAND)] = "  cmd  "
    config[("python.mock", audiobookshelf.CONFIG_PLAYER)] = "  mpv  "

    plugin = audiobookshelf.Plugin()
    assert plugin.audiobookshelf_url == "http://x"
    assert plugin.api_key == "tok"
    assert plugin.api_key_command == "cmd"
    assert plugin.player_command == "mpv"
    assert plugin._resolved_token is None


def test_a_blank_player_falls_back_to_cvlc():
    assert audiobookshelf.Plugin().player_command == "cvlc"


def test_setting_the_url_writes_it_and_forgets_the_cache():
    plugin = make_plugin()
    plugin._libraries = (time.monotonic(), [])

    plugin.audiobookshelf_url = "  http://new  "
    assert plugin.audiobookshelf_url == "http://new"
    stored = albert.PluginInstance._CONFIG[("python.mock", audiobookshelf.CONFIG_URL)]
    assert stored == "http://new"
    assert plugin._libraries is None


def test_setting_the_key_writes_it_and_resets_the_caches():
    plugin = make_plugin()
    plugin._resolved_token = "old"

    plugin.api_key = "  newkey  "
    assert plugin.api_key == "newkey"
    stored = albert.PluginInstance._CONFIG[("python.mock", audiobookshelf.CONFIG_API_TOKEN)]
    assert stored == "newkey"
    assert plugin._resolved_token is None


def test_setting_the_command_forgets_the_resolved_key():
    plugin = make_plugin(token="", command="a")
    plugin._resolved_token = "old"

    plugin.api_key_command = "  pass show b  "
    assert plugin.api_key_command == "pass show b"
    assert plugin._resolved_token is None


def test_setting_the_player_writes_it():
    plugin = make_plugin()
    plugin.player_command = "  cvlc --play-and-exit  "

    assert plugin.player_command == "cvlc --play-and-exit"
    stored = albert.PluginInstance._CONFIG[("python.mock", audiobookshelf.CONFIG_PLAYER)]
    assert stored == "cvlc --play-and-exit"


def test_setting_a_blank_player_falls_back():
    plugin = make_plugin()
    plugin.player_command = "   "
    assert plugin.player_command == "cvlc"


def test_the_config_widget_has_url_key_and_player():
    widget = audiobookshelf.Plugin.configWidget(make_plugin())
    fields = [entry for entry in widget if entry.get("property")]

    assert [field["property"] for field in fields] == [
        "audiobookshelf_url",
        "api_key",
        "api_key_command",
        "player_command",
    ]
    key = next(field for field in fields if field["property"] == "api_key")
    assert key["widget_properties"]["echoMode"] == 2
    assert widget[0]["type"] == "label"


def test_the_trigger_and_synopsis():
    plugin = make_plugin()
    assert plugin.defaultTrigger() == "abs "
    assert plugin.synopsis("") == "an audiobook title, series or author"


def test_the_icon_file_exists():
    assert (audiobookshelf.ICON_DIR / "audiobookshelf.svg").is_file()


def test_the_icon_is_loaded_from_that_file():
    icon = audiobookshelf.Plugin.makeIcon()
    assert str(audiobookshelf.ICON_PATH) in str(icon)
