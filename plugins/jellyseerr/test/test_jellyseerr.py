"""Tests for the jellyseerr plugin.

`requests` is monkeypatched rather than mocked wholesale, so the real response
bodies and the real exception types are in play: what is checked is how a
Jellyseerr answer - including the ugly ones - is turned into an item, and that
is the part that breaks when the server changes.

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

jellyseerr = load_plugin("jellyseerr")

BASE = "http://jellyseerr:5055"
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
    monkeypatch.setattr(jellyseerr.requests, "request", handler)
    return handler


class Api:
    """A stand-in for the module-level `call`, recording the API calls made."""

    def __init__(self):
        self.calls = []
        self.reply = {}

    def __call__(self, method, base_url, token, path, params=None, body=None, timeout=None):
        self.calls.append(
            {
                "method": method,
                "base_url": base_url,
                "token": token,
                "path": path,
                "params": params,
                "body": body,
            }
        )
        if callable(self.reply):
            return self.reply(path)
        return self.reply


@pytest.fixture
def api(monkeypatch):
    fake = Api()
    monkeypatch.setattr(jellyseerr, "call", fake)
    return fake


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


class FakeCtx:
    def __init__(self, query, valid=True):
        self.query = query
        self.isValid = valid


def make_plugin(url=BASE, token=TOKEN, command=""):
    """A plugin instance without going through __init__ (no config, no disk)."""
    plugin = jellyseerr.Plugin.__new__(jellyseerr.Plugin)
    plugin._url = url
    plugin._token = token
    plugin._token_command = command
    plugin._lock = threading.Lock()
    plugin._requests = None
    plugin._titles = {}
    plugin._searches = {}
    plugin._resolved_token = None
    return plugin


def wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


# -- sample payloads -------------------------------------------------------------------------


def movie_request(rid=1, status=jellyseerr.STATUS_PENDING, tmdb=550):
    return {
        "id": rid,
        "status": status,
        "type": "movie",
        "media": {"mediaType": "movie", "tmdbId": tmdb, "status": 1},
        "requestedBy": {"displayName": "alice"},
        "createdAt": "2024-05-01T12:00:00.000Z",
        "seasons": [],
    }


def tv_request(rid=2, status=jellyseerr.STATUS_PENDING, tmdb=1396, seasons=(1, 2)):
    return {
        "id": rid,
        "status": status,
        "type": "tv",
        "media": {"mediaType": "tv", "tmdbId": tmdb, "status": 1},
        "requestedBy": {"displayName": "bob"},
        "createdAt": "2024-05-02T12:00:00.000Z",
        "seasons": [{"seasonNumber": number, "status": 1} for number in seasons],
        "seasonCount": len(seasons),
    }


def movie_result(tmdb=550, title="Fight Club", status=1):
    return {
        "mediaType": "movie",
        "id": tmdb,
        "title": title,
        "releaseDate": "1999-10-15",
        "mediaInfo": {"status": status},
    }


def tv_result(tmdb=1396, name="Breaking Bad", status=1):
    return {
        "mediaType": "tv",
        "id": tmdb,
        "name": name,
        "firstAirDate": "2008-01-20",
        "mediaInfo": {"status": status},
    }


# -- urls ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "base, path, expected",
    [
        ("http://localhost:5055", "api/v1/request", "http://localhost:5055/api/v1/request"),
        ("http://localhost:5055/", "/api/v1/request", "http://localhost:5055/api/v1/request"),
        ("https://host/jellyseerr", "movie/42", "https://host/jellyseerr/movie/42"),
        # a leading slash on the path must not climb out of a proxy prefix
        ("https://host/jellyseerr", "/movie/42", "https://host/jellyseerr/movie/42"),
    ],
)
def test_join_url(base, path, expected):
    assert jellyseerr.join_url(base, path) == expected


def test_home_url_strips_the_trailing_slash():
    assert jellyseerr.home_url("http://localhost:5055/") == "http://localhost:5055"


def test_requests_url_points_at_the_queue():
    assert jellyseerr.requests_url(BASE) == f"{BASE}/requests"


def test_media_url_has_a_page_per_media_type():
    assert jellyseerr.media_url(BASE, "movie", 27205) == f"{BASE}/movie/27205"
    assert jellyseerr.media_url(BASE, "tv", 1396) == f"{BASE}/tv/1396"


def test_media_url_falls_back_to_the_root_for_unlinkable_hits():
    assert jellyseerr.media_url(BASE, "person", 5) == BASE
    assert jellyseerr.media_url(BASE, "movie", None) == BASE


# -- call ------------------------------------------------------------------------------------


def test_call_returns_the_decoded_body(http):
    http.response = FakeResponse({"results": []})
    assert jellyseerr.call("GET", BASE, TOKEN, "api/v1/request") == {"results": []}


def test_call_sends_the_api_key_and_user_agent(http):
    jellyseerr.call("GET", BASE, TOKEN, "api/v1/request")

    call = http.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == f"{BASE}/api/v1/request"
    assert call["headers"]["X-API-Key"] == TOKEN
    assert call["headers"]["Accept"] == "application/json"
    assert "User-Agent" in call["headers"]
    assert call["timeout"] == jellyseerr.HTTP_TIMEOUT


def test_call_forwards_params_and_body(http):
    jellyseerr.call("POST", BASE, TOKEN, "api/v1/request", params={"take": 5}, body={"a": 1})

    call = http.calls[0]
    assert call["url"] == f"{BASE}/api/v1/request?take=5"
    # params are baked into the url, not handed to requests, which would use "+"
    assert "params" not in call
    assert call["json"] == {"a": 1}


def test_call_percent_encodes_parameter_values(http):
    # the bug this fixes: requests encodes a space as "+", which Jellyseerr's
    # query parser reads literally and rejects as a reserved character
    jellyseerr.call(
        "GET", BASE, TOKEN, "api/v1/search", params={"query": "Fight Club", "page": 1}
    )
    assert http.calls[0]["url"] == f"{BASE}/api/v1/search?query=Fight%20Club&page=1"


def test_call_encodes_other_reserved_characters(http):
    jellyseerr.call("GET", BASE, TOKEN, "api/v1/search", params={"query": "C++ & more"})
    assert http.calls[0]["url"] == f"{BASE}/api/v1/search?query=C%2B%2B%20%26%20more"


def test_call_omits_params_and_body_when_not_given(http):
    jellyseerr.call("GET", BASE, TOKEN, "api/v1/request")
    assert http.calls[0]["url"] == f"{BASE}/api/v1/request"
    assert "params" not in http.calls[0]
    assert "json" not in http.calls[0]


def test_call_with_an_empty_param_dict_adds_no_query(http):
    jellyseerr.call("GET", BASE, TOKEN, "api/v1/request", params={})
    assert http.calls[0]["url"] == f"{BASE}/api/v1/request"


def test_call_refuses_an_empty_url(http):
    with pytest.raises(jellyseerr.JellyseerrError, match="No Jellyseerr URL"):
        jellyseerr.call("GET", "", TOKEN, "api/v1/request")
    assert http.calls == []


def test_call_refuses_a_url_without_a_scheme(http):
    with pytest.raises(jellyseerr.JellyseerrError, match="not a full URL"):
        jellyseerr.call("GET", "localhost:5055", TOKEN, "api/v1/request")
    assert http.calls == []


def test_call_reports_a_timeout(http):
    http.response = requests.Timeout()
    with pytest.raises(jellyseerr.JellyseerrError, match="did not answer within 10s"):
        jellyseerr.call("GET", BASE, TOKEN, "api/v1/request")


def test_call_reports_an_unreachable_server(http):
    http.response = requests.ConnectionError("no route to host")
    with pytest.raises(jellyseerr.JellyseerrError, match=f"Cannot reach {BASE}"):
        jellyseerr.call("GET", BASE, TOKEN, "api/v1/request")


def test_call_handles_a_204(http):
    http.response = FakeResponse(status=204)
    assert jellyseerr.call("POST", BASE, TOKEN, "api/v1/request/1/approve") is None


def test_call_surfaces_a_non_json_body(http):
    http.response = FakeResponse(json_error=True, status=200)
    with pytest.raises(jellyseerr.JellyseerrError, match="did not answer with JSON"):
        jellyseerr.call("GET", BASE, TOKEN, "api/v1/request")


def test_call_explains_a_403_with_the_auth_error(http):
    http.response = FakeResponse(
        {"status": 403, "error": "You do not have permission to access this endpoint"},
        status=403,
    )
    with pytest.raises(jellyseerr.JellyseerrError) as exc:
        jellyseerr.call("GET", BASE, TOKEN, "api/v1/search")

    message = str(exc.value)
    assert "HTTP 403" in message
    assert "do not have permission" in message
    assert "Check the API key" in message


def test_call_surfaces_the_service_message(http):
    http.response = FakeResponse(
        {"message": "Request for this item already exists."}, status=409
    )
    with pytest.raises(jellyseerr.JellyseerrError) as exc:
        jellyseerr.call("POST", BASE, TOKEN, "api/v1/request")

    message = str(exc.value)
    assert "HTTP 409" in message
    assert "already exists" in message
    # a 409 is not a credentials problem, so the key hint must not be there
    assert "API key" not in message


def test_call_quotes_an_html_error_page(http):
    # a reverse proxy in front of jellyseerr answers with a page, not json
    http.response = FakeResponse(
        json_error=True, status=502, text="<html>\n  <body>Bad Gateway</body>\n</html>"
    )
    with pytest.raises(jellyseerr.JellyseerrError, match=r"HTTP 502.*Bad Gateway"):
        jellyseerr.call("GET", BASE, TOKEN, "api/v1/request")


# -- fetch_requests --------------------------------------------------------------------------


def test_fetch_requests_returns_the_results(api):
    api.reply = {"results": [{"id": 1}, {"id": 2}]}
    assert jellyseerr.fetch_requests(BASE, TOKEN) == [{"id": 1}, {"id": 2}]

    call = api.calls[0]
    assert call["method"] == "GET"
    assert call["path"] == "api/v1/request"
    assert call["params"] == {"take": jellyseerr.REQUEST_TAKE, "skip": 0}


def test_fetch_requests_drops_junk_rows(api):
    api.reply = {"results": [{"id": 1}, "nope", 42, None]}
    assert jellyseerr.fetch_requests(BASE, TOKEN) == [{"id": 1}]


def test_fetch_requests_rejects_an_unexpected_body(api):
    api.reply = {"nonsense": True}
    with pytest.raises(jellyseerr.JellyseerrError, match="something unexpected"):
        jellyseerr.fetch_requests(BASE, TOKEN)


# -- fetch_search ----------------------------------------------------------------------------


def test_fetch_search_returns_movies_and_series_only(api):
    api.reply = {
        "results": [
            {"mediaType": "movie", "id": 1},
            {"mediaType": "tv", "id": 2},
            {"mediaType": "person", "id": 3},
            {"mediaType": "collection", "id": 4},
        ]
    }
    assert jellyseerr.fetch_search(BASE, TOKEN, "fight") == [
        {"mediaType": "movie", "id": 1},
        {"mediaType": "tv", "id": 2},
    ]

    assert api.calls[0]["path"] == "api/v1/search"
    assert api.calls[0]["params"] == {"query": "fight", "page": 1}


def test_fetch_search_rejects_an_unexpected_body(api):
    api.reply = None
    with pytest.raises(jellyseerr.JellyseerrError, match="something unexpected"):
        jellyseerr.fetch_search(BASE, TOKEN, "fight")


# -- fetch_title -----------------------------------------------------------------------------


def test_fetch_title_asks_for_a_movie_title(api):
    api.reply = {"title": "Fight Club", "name": "ignored"}
    assert jellyseerr.fetch_title(BASE, TOKEN, "movie", 550) == "Fight Club"
    assert api.calls[0]["path"] == "api/v1/movie/550"


def test_fetch_title_asks_for_a_series_name(api):
    api.reply = {"name": "Breaking Bad", "title": "ignored"}
    assert jellyseerr.fetch_title(BASE, TOKEN, "tv", 1396) == "Breaking Bad"
    assert api.calls[0]["path"] == "api/v1/tv/1396"


def test_fetch_title_is_empty_when_the_body_is_not_an_object(api):
    api.reply = []
    assert jellyseerr.fetch_title(BASE, TOKEN, "movie", 550) == ""


# -- resolve_titles --------------------------------------------------------------------------


def test_resolve_titles_fills_only_what_is_missing(monkeypatch):
    asked = []

    def fake_fetch(base, token, media_type, tmdb_id):
        asked.append((media_type, tmdb_id))
        return f"title-{tmdb_id}"

    monkeypatch.setattr(jellyseerr, "fetch_title", fake_fetch)

    titles = {"movie:1": "known"}
    jellyseerr.resolve_titles(BASE, TOKEN, titles, [("movie", 1), ("tv", 2), ("movie", 3)])

    assert titles == {"movie:1": "known", "tv:2": "title-2", "movie:3": "title-3"}
    assert sorted(asked) == [("movie", 3), ("tv", 2)]


def test_resolve_titles_swallows_a_failed_lookup(monkeypatch):
    def fake_fetch(base, token, media_type, tmdb_id):
        raise jellyseerr.JellyseerrError("nope")

    monkeypatch.setattr(jellyseerr, "fetch_title", fake_fetch)

    titles = {}
    jellyseerr.resolve_titles(BASE, TOKEN, titles, [("movie", 1)])
    assert titles == {"movie:1": ""}


def test_resolve_titles_with_nothing_to_do_does_not_ask(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("should not have been called")

    monkeypatch.setattr(jellyseerr, "fetch_title", fail)
    jellyseerr.resolve_titles(BASE, TOKEN, {"movie:1": "known"}, [("movie", 1)])


# -- set_request_status ----------------------------------------------------------------------


@pytest.mark.parametrize("status", ["pending", "approve", "decline"])
def test_set_request_status_uses_the_right_route(api, status):
    api.reply = {"id": 7}
    assert jellyseerr.set_request_status(BASE, TOKEN, 7, status) == {"id": 7}
    assert api.calls[0]["method"] == "POST"
    assert api.calls[0]["path"] == f"api/v1/request/7/{status}"


def test_set_request_status_refuses_an_unknown_status(api):
    with pytest.raises(jellyseerr.JellyseerrError, match="Not a request status"):
        jellyseerr.set_request_status(BASE, TOKEN, 7, "declined")
    assert api.calls == []


# -- create_request --------------------------------------------------------------------------


def test_create_request_asks_for_a_movie(api):
    api.reply = {"id": 9, "status": 2}
    assert jellyseerr.create_request(BASE, TOKEN, "movie", 550) == {"id": 9, "status": 2}

    call = api.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "api/v1/request"
    assert call["body"] == {"mediaType": "movie", "mediaId": 550}


def test_create_request_asks_a_series_for_all_its_seasons(api):
    api.reply = {"id": 9}
    jellyseerr.create_request(BASE, TOKEN, "tv", 1396)
    assert api.calls[0]["body"] == {"mediaType": "tv", "mediaId": 1396, "seasons": "all"}


def test_create_request_refuses_an_unknown_media_type(api):
    with pytest.raises(jellyseerr.JellyseerrError, match="Not a media type"):
        jellyseerr.create_request(BASE, TOKEN, "person", 5)
    assert api.calls == []


def test_create_request_refuses_a_missing_tmdb_id(api):
    with pytest.raises(jellyseerr.JellyseerrError, match="without a TMDB id"):
        jellyseerr.create_request(BASE, TOKEN, "movie", None)
    assert api.calls == []


def test_create_request_reports_the_nothing_to_request_case(api):
    # a 202 carries no request, only a message, and every season already exists
    api.reply = {"message": "Request for all seasons already exists."}
    with pytest.raises(jellyseerr.JellyseerrError, match="already exists"):
        jellyseerr.create_request(BASE, TOKEN, "tv", 1396)


def test_create_request_reports_a_payload_without_an_id(api):
    api.reply = {}
    with pytest.raises(jellyseerr.JellyseerrError, match="did not create the request"):
        jellyseerr.create_request(BASE, TOKEN, "movie", 550)


# -- resolve_api_key -------------------------------------------------------------------------


def test_resolve_api_key_prefers_the_plaintext_key():
    assert jellyseerr.resolve_api_key("  plain  ", "") == "plain"
    # and the command field being blank spaces is the same as it being empty
    assert jellyseerr.resolve_api_key("  plain  ", "   ") == "plain"


def test_resolve_api_key_runs_the_command(monkeypatch):
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["shell"] = kwargs.get("shell")
        return completed(stdout="  key123\n")

    monkeypatch.setattr(jellyseerr.subprocess, "run", fake_run)

    assert jellyseerr.resolve_api_key("ignored", "pass show jellyseerr") == "key123"
    assert seen["command"] == "pass show jellyseerr"
    assert seen["shell"] is True


def test_resolve_api_key_command_wins_over_the_plaintext_key(monkeypatch):
    monkeypatch.setattr(
        jellyseerr.subprocess,
        "run",
        lambda command, **kwargs: completed(stdout="from-command"),
    )
    assert jellyseerr.resolve_api_key("plaintext", "echo x") == "from-command"


def test_resolve_api_key_reports_a_failed_command(monkeypatch):
    monkeypatch.setattr(
        jellyseerr.subprocess,
        "run",
        lambda command, **kwargs: completed(returncode=1, stderr="keyring is locked\n"),
    )
    with pytest.raises(jellyseerr.JellyseerrError, match=r"failed.*keyring is locked"):
        jellyseerr.resolve_api_key("", "rbw get jellyseerr")


def test_resolve_api_key_reports_a_command_that_hangs(monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, jellyseerr.KEY_COMMAND_TIMEOUT)

    monkeypatch.setattr(jellyseerr.subprocess, "run", fake_run)
    with pytest.raises(jellyseerr.JellyseerrError, match="took longer"):
        jellyseerr.resolve_api_key("", "sleep 100")


def test_resolve_api_key_refuses_empty_output(monkeypatch):
    monkeypatch.setattr(
        jellyseerr.subprocess, "run", lambda command, **kwargs: completed(stdout="  \n")
    )
    with pytest.raises(jellyseerr.JellyseerrError, match="printed nothing"):
        jellyseerr.resolve_api_key("", "true")


def test_resolve_api_key_reports_a_command_that_will_not_start(monkeypatch):
    def fake_run(command, **kwargs):
        raise OSError("Exec format error")

    monkeypatch.setattr(jellyseerr.subprocess, "run", fake_run)
    with pytest.raises(jellyseerr.JellyseerrError, match="Could not run"):
        jellyseerr.resolve_api_key("", "./bogus")


# -- reading the payloads --------------------------------------------------------------------


def test_int_falls_back_for_junk():
    assert jellyseerr._int("5") == 5
    assert jellyseerr._int(None, 7) == 7
    assert jellyseerr._int("x", 7) == 7


def test_parse_timestamp_reads_a_z_suffixed_utc_moment():
    stamp = jellyseerr._parse_timestamp("2024-05-01T12:00:00.000Z")
    assert stamp is not None
    assert stamp.isoformat() == "2024-05-01T12:00:00+00:00"


def test_parse_timestamp_assumes_utc_for_a_naive_value():
    stamp = jellyseerr._parse_timestamp("2024-05-01T12:00:00")
    assert stamp is not None
    assert stamp.tzinfo is not None


def test_parse_timestamp_rejects_junk():
    assert jellyseerr._parse_timestamp(None) is None
    assert jellyseerr._parse_timestamp("") is None
    assert jellyseerr._parse_timestamp("last tuesday") is None
    assert jellyseerr._parse_timestamp(12345) is None


def test_relative_time_never_counts_down():
    stamp = jellyseerr._parse_timestamp("2024-05-01T12:00:00.000Z")
    now = stamp.replace(hour=11)
    assert jellyseerr.relative_time("2024-05-01T12:00:00.000Z", now) == "just now"


def test_relative_time_speaks_in_years():
    assert jellyseerr.relative_time("2020-05-01T12:00:00.000Z", None) != ""


def test_sort_requests_puts_pending_first_then_newest():
    old_pending = movie_request(rid=1, status=jellyseerr.STATUS_PENDING)
    new_pending = dict(movie_request(rid=2, status=jellyseerr.STATUS_PENDING))
    new_pending["createdAt"] = "2024-05-03T12:00:00.000Z"
    approved = dict(movie_request(rid=3, status=jellyseerr.STATUS_APPROVED))
    approved["createdAt"] = "2024-05-04T12:00:00.000Z"

    ordered = jellyseerr.sort_requests([approved, old_pending, new_pending])
    assert [request["id"] for request in ordered] == [2, 1, 3]


def test_request_media_type_prefers_the_media_object():
    assert jellyseerr.request_media_type(movie_request()) == "movie"
    assert jellyseerr.request_media_type({"type": "tv"}) == "tv"
    assert jellyseerr.request_media_type({"type": "person"}) == ""
    assert jellyseerr.request_media_type({}) == ""


def test_request_tmdb_id_reads_the_media_object():
    assert jellyseerr.request_tmdb_id(movie_request(tmdb=42)) == 42
    assert jellyseerr.request_tmdb_id({}) is None


def test_request_status_is_an_int():
    assert jellyseerr.request_status(movie_request(status=2)) == 2
    assert jellyseerr.request_status({}) == 0


def test_request_refs_pairs_type_and_id():
    assert jellyseerr.request_refs([movie_request(tmdb=1), tv_request(tmdb=2)]) == [
        ("movie", 1),
        ("tv", 2),
    ]


def test_request_title_uses_the_cache():
    assert jellyseerr.request_title(movie_request(tmdb=550), {"movie:550": "Fight Club"}) == (
        "Fight Club"
    )


def test_request_title_falls_back_to_type_and_id():
    assert jellyseerr.request_title(movie_request(tmdb=550), {}) == "Movie 550"
    assert jellyseerr.request_title(tv_request(tmdb=1396), {}) == "Series 1396"


def test_request_title_falls_back_to_the_type_alone():
    assert jellyseerr.request_title({"type": "movie", "media": {}}, {}) == "Movie"


@pytest.mark.parametrize(
    "payload, expected",
    [
        (movie_request(), ""),
        (tv_request(seasons=(1, 3)), "S1, S3"),
        (tv_request(seasons=(1, 2, 3, 4, 5)), "5 seasons"),
        (tv_request(seasons=(1,)), "S1"),
    ],
)
def test_season_label(payload, expected):
    assert jellyseerr.season_label(payload) == expected


def test_season_label_falls_back_to_the_count():
    request = tv_request()
    request["seasons"] = []
    request["seasonCount"] = 2
    assert jellyseerr.season_label(request) == "2 seasons"


def test_season_label_of_one_is_singular():
    request = tv_request()
    request["seasons"] = []
    request["seasonCount"] = 1
    assert jellyseerr.season_label(request) == "1 season"


def test_season_label_is_empty_without_seasons():
    request = tv_request()
    request["seasons"] = []
    request["seasonCount"] = 0
    assert jellyseerr.season_label(request) == ""


def test_request_subtext_describes_the_row(monkeypatch):
    monkeypatch.setattr(jellyseerr, "relative_time", lambda value: "2 days ago")
    subtext = jellyseerr.request_subtext(movie_request(status=jellyseerr.STATUS_PENDING))

    assert subtext == "Movie | Pending | requested by alice | 2 days ago"


def test_request_subtext_names_the_seasons(monkeypatch):
    monkeypatch.setattr(jellyseerr, "relative_time", lambda value: "")
    subtext = jellyseerr.request_subtext(tv_request(seasons=(1, 3)))
    assert subtext.startswith("Series | S1, S3 | Pending")


def test_result_media_type_only_accepts_requestable_kinds():
    assert jellyseerr.result_media_type(movie_result()) == "movie"
    assert jellyseerr.result_media_type(tv_result()) == "tv"
    assert jellyseerr.result_media_type({"mediaType": "person"}) == ""


def test_result_title_reads_title_or_name():
    assert jellyseerr.result_title(movie_result()) == "Fight Club"
    assert jellyseerr.result_title(tv_result()) == "Breaking Bad"
    assert jellyseerr.result_title({}) == ""


def test_result_year_reads_either_date_field():
    assert jellyseerr.result_year(movie_result()) == "1999"
    assert jellyseerr.result_year(tv_result()) == "2008"
    assert jellyseerr.result_year({"releaseDate": ""}) == ""
    assert jellyseerr.result_year({"releaseDate": "99"}) == ""


def test_result_media_status_defaults_to_unknown():
    assert jellyseerr.result_media_status(movie_result(status=5)) == 5
    assert jellyseerr.result_media_status({}) == jellyseerr.MEDIA_UNKNOWN
    assert jellyseerr.result_media_status({"mediaInfo": "nope"}) == jellyseerr.MEDIA_UNKNOWN


@pytest.mark.parametrize(
    "status, requestable",
    [
        (jellyseerr.MEDIA_UNKNOWN, True),
        (jellyseerr.MEDIA_PENDING, False),
        (jellyseerr.MEDIA_PROCESSING, False),
        (jellyseerr.MEDIA_PARTIAL, False),
        (jellyseerr.MEDIA_AVAILABLE, False),
    ],
)
def test_can_request_a_movie_only_when_untouched(status, requestable):
    assert jellyseerr.can_request(movie_result(status=status)) is requestable


@pytest.mark.parametrize(
    "status, requestable",
    [
        (jellyseerr.MEDIA_UNKNOWN, True),
        (jellyseerr.MEDIA_PENDING, True),
        (jellyseerr.MEDIA_AVAILABLE, False),
    ],
)
def test_can_request_a_series_whenever_seasons_could_be_missing(status, requestable):
    assert jellyseerr.can_request(tv_result(status=status)) is requestable


def test_can_request_without_library_information():
    assert jellyseerr.can_request({"mediaType": "movie", "id": 1}) is True


def test_result_subtext_describes_the_hit():
    assert jellyseerr.result_subtext(movie_result(status=1)) == "Movie | 1999 | Not requested"
    assert (
        jellyseerr.result_subtext(tv_result(status=5)) == "Series | 2008 | Already available"
    )


# -- items: setup ----------------------------------------------------------------------------


def test_a_missing_url_is_asked_for_first():
    plugin = make_plugin(url="", token="")
    (item,) = next(plugin.items(FakeCtx("")))

    assert "Jellyseerr URL missing" in item.text
    assert item.actions[0].id == "open"


def test_a_missing_key_is_asked_for():
    plugin = make_plugin(url=BASE, token="")
    (item,) = next(plugin.items(FakeCtx("")))

    assert "API key missing" in item.text
    assert BASE in item.subtext


def test_setup_takes_precedence_over_the_query():
    plugin = make_plugin(url="", token="")
    (item,) = next(plugin.items(FakeCtx("fight club")))
    assert "settings" in item.text


# -- items: the request list -----------------------------------------------------------------


@pytest.fixture
def offline(monkeypatch):
    """Keep the request list off the network: no requests, no title lookups."""
    monkeypatch.setattr(jellyseerr, "fetch_requests", lambda *a, **k: [])
    monkeypatch.setattr(jellyseerr, "resolve_titles", lambda *a, **k: None)


def test_an_empty_query_lists_the_requests(monkeypatch, offline):
    monkeypatch.setattr(jellyseerr, "fetch_requests", lambda *a, **k: [movie_request()])
    plugin = make_plugin()
    plugin._titles = {"movie:550": "Fight Club"}

    items = next(plugin.items(FakeCtx("")))
    assert [item.text for item in items] == ["Fight Club"]


def test_an_empty_list_says_so(offline):
    plugin = make_plugin()
    items = next(plugin.items(FakeCtx("")))

    assert "No requests on this Jellyseerr" in items[0].text


def test_pending_requests_are_approved_with_enter(monkeypatch, offline):
    monkeypatch.setattr(jellyseerr, "fetch_requests", lambda *a, **k: [movie_request()])
    plugin = make_plugin()
    plugin._titles = {"movie:550": "Fight Club"}

    items = next(plugin.items(FakeCtx("")))
    assert items[0].actions[0].id == "approve"
    assert [action.id for action in items[0].actions] == [
        "approve",
        "decline",
        "open",
        "site",
        "reload",
    ]


def test_a_decided_request_is_only_opened(monkeypatch, offline):
    request = movie_request(status=jellyseerr.STATUS_APPROVED)
    monkeypatch.setattr(jellyseerr, "fetch_requests", lambda *a, **k: [request])
    plugin = make_plugin()
    plugin._titles = {"movie:550": "Fight Club"}

    items = next(plugin.items(FakeCtx("")))
    assert items[0].actions[0].id == "open"
    assert all(action.id != "approve" for action in items[0].actions)


def test_the_request_list_resolves_missing_titles(monkeypatch):
    monkeypatch.setattr(jellyseerr, "fetch_requests", lambda *a, **k: [movie_request()])
    monkeypatch.setattr(jellyseerr, "fetch_title", lambda *a, **k: "Fight Club")
    plugin = make_plugin()

    items = next(plugin.items(FakeCtx("")))
    assert items[0].text == "Fight Club"


def test_a_request_the_lookup_missed_still_names_its_media(monkeypatch):
    monkeypatch.setattr(jellyseerr, "fetch_requests", lambda *a, **k: [movie_request()])
    plugin = make_plugin()
    plugin._titles = {"movie:550": ""}

    items = next(plugin.items(FakeCtx("")))
    assert items[0].text == "Movie 550"


# -- items: searching ------------------------------------------------------------------------


def test_a_one_character_query_asks_for_more(monkeypatch, offline):
    plugin = make_plugin()
    items = next(plugin.items(FakeCtx("f")))

    assert "Search Jellyseerr for f" in items[0].text
    assert items[0].input_action_text == ""


def test_a_search_lists_the_hits(monkeypatch):
    monkeypatch.setattr(jellyseerr, "fetch_search", lambda *a, **k: [movie_result()])
    plugin = make_plugin()

    items = next(plugin.items(FakeCtx("fight")))
    assert [item.text for item in items] == ["Fight Club"]
    assert items[0].actions[0].id == "request"


def test_a_requestable_hit_is_requested_first():
    plugin = make_plugin()
    item = plugin._result_item(movie_result(status=jellyseerr.MEDIA_UNKNOWN))
    assert item.actions[0].id == "request"


def test_an_available_hit_is_only_opened():
    plugin = make_plugin()
    item = plugin._result_item(tv_result(status=jellyseerr.MEDIA_AVAILABLE))
    assert item.actions[0].id == "open"


def test_a_search_without_hits_says_so(monkeypatch):
    monkeypatch.setattr(jellyseerr, "fetch_search", lambda *a, **k: [])
    plugin = make_plugin()

    items = next(plugin.items(FakeCtx("zzzz")))
    assert "Nothing on Jellyseerr matches" in items[0].text


def test_the_search_is_capped(monkeypatch):
    monkeypatch.setattr(jellyseerr, "SEARCH_LIMIT", 2)
    plugin = make_plugin()
    results = [movie_result(tmdb=index, title=f"Title {index}") for index in range(5)]

    items = plugin._search_items("title", results)
    assert [item.text for item in items] == ["Title 0", "Title 1"]


def test_a_cancelled_query_is_not_searched(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("a cancelled query must not reach the network")

    monkeypatch.setattr(jellyseerr, "fetch_search", fail)
    plugin = make_plugin()

    assert list(plugin.items(FakeCtx("fight", valid=False))) == []


# -- caches ----------------------------------------------------------------------------------


def test_the_request_list_is_fetched_once_within_the_ttl(monkeypatch):
    calls = []

    def fake_fetch(*args, **kwargs):
        calls.append(args)
        return []

    monkeypatch.setattr(jellyseerr, "fetch_requests", fake_fetch)
    monkeypatch.setattr(jellyseerr, "resolve_titles", lambda *a, **k: None)

    plugin = make_plugin()
    plugin._request_list()
    plugin._request_list()
    assert len(calls) == 1


def test_a_search_is_fetched_once_within_the_ttl(monkeypatch):
    calls = []

    def fake_fetch(*args, **kwargs):
        calls.append(args)
        return []

    monkeypatch.setattr(jellyseerr, "fetch_search", fake_fetch)
    plugin = make_plugin()

    plugin._search("fight")
    plugin._search("fight")
    assert len(calls) == 1


def test_forget_drops_every_cache(monkeypatch):
    monkeypatch.setattr(jellyseerr, "fetch_requests", lambda *a, **k: [])
    monkeypatch.setattr(jellyseerr, "resolve_titles", lambda *a, **k: None)

    plugin = make_plugin()
    plugin._request_list()
    plugin._search = lambda term: []
    plugin._searches["fight"] = (time.monotonic(), [])
    plugin._titles = {"movie:1": "x"}

    plugin._forget()

    assert plugin._requests is None
    assert plugin._titles == {}
    assert plugin._searches == {}


def test_the_search_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(jellyseerr, "SEARCH_CACHE_SIZE", 3)
    monkeypatch.setattr(jellyseerr, "fetch_search", lambda *a, **k: [])
    plugin = make_plugin()

    for term in ("a", "b", "c", "d"):
        plugin._search(term)
    assert len(plugin._searches) == 3
    assert "a" not in plugin._searches


# -- the api key command ---------------------------------------------------------------------


def test_the_plaintext_key_is_used_when_no_command_is_set():
    assert make_plugin(token="plain")._api_key() == "plain"


def test_the_command_key_wins_over_the_plaintext_key(monkeypatch):
    monkeypatch.setattr(
        jellyseerr.subprocess,
        "run",
        lambda command, **kwargs: completed(stdout="from-command"),
    )
    assert make_plugin(token="plain", command="pass show x")._api_key() == "from-command"


def test_the_command_runs_once_and_the_key_is_cached(monkeypatch):
    calls = []

    def fake_resolve(token, command):
        calls.append((token, command))
        return "from-command"

    monkeypatch.setattr(jellyseerr, "resolve_api_key", fake_resolve)
    plugin = make_plugin(token="", command="pass show jellyseerr")

    assert plugin._api_key() == "from-command"
    assert plugin._api_key() == "from-command"
    assert calls == [("", "pass show jellyseerr")]


def test_a_failed_command_is_not_cached(monkeypatch):
    calls = []

    def fake_resolve(token, command):
        calls.append(command)
        if len(calls) == 1:
            raise jellyseerr.JellyseerrError("keyring is locked")
        return "now-unlocked"

    monkeypatch.setattr(jellyseerr, "resolve_api_key", fake_resolve)
    plugin = make_plugin(token="", command="rbw get x")

    with pytest.raises(jellyseerr.JellyseerrError, match="locked"):
        plugin._api_key()
    # the second try runs the command again and succeeds
    assert plugin._api_key() == "now-unlocked"
    assert len(calls) == 2


def test_the_command_key_is_never_written_to_the_config(monkeypatch):
    monkeypatch.setattr(jellyseerr, "resolve_api_key", lambda token, command: "super-secret")
    plugin = make_plugin(token="", command="pass show x")

    plugin._api_key()
    assert plugin._token == ""
    # nothing was written to Albert's config store, so the key stays in memory
    assert albert.PluginInstance._CONFIG == {}


def test_a_command_satisfies_the_setup_check():
    assert make_plugin(token="", command="pass show x")._setup_item() is None
    assert make_plugin(token="", command="")._setup_item() is not None


def test_the_request_list_sends_the_command_key(monkeypatch):
    monkeypatch.setattr(jellyseerr, "resolve_api_key", lambda token, command: "command-key")
    seen = {}

    def fake_fetch(base, token):
        seen["base"], seen["token"] = base, token
        return []

    monkeypatch.setattr(jellyseerr, "fetch_requests", fake_fetch)
    monkeypatch.setattr(jellyseerr, "resolve_titles", lambda *a, **k: None)

    make_plugin(token="", command="pass show x")._request_list()
    assert seen == {"base": BASE, "token": "command-key"}


def test_the_search_sends_the_command_key(monkeypatch):
    monkeypatch.setattr(jellyseerr, "resolve_api_key", lambda token, command: "command-key")
    seen = {}

    def fake_search(base, token, term):
        seen["token"] = token
        return []

    monkeypatch.setattr(jellyseerr, "fetch_search", fake_search)
    make_plugin(token="", command="pass show x")._search("fight")
    assert seen["token"] == "command-key"


def test_a_command_that_fails_is_reported_when_acting(monkeypatch):
    def fake_resolve(token, command):
        raise jellyseerr.JellyseerrError("keyring is locked")

    monkeypatch.setattr(jellyseerr, "resolve_api_key", fake_resolve)
    plugin = make_plugin(token="", command="rbw get x")

    item = plugin._request_item(movie_request(), {"movie:550": "Fight Club"})
    item.actions[0].callable()

    assert wait_for(lambda: ("Jellyseerr", "keyring is locked") in albert.Notification.SENT)


def test_changing_the_command_forgets_the_resolved_key():
    plugin = make_plugin(token="", command="a")
    plugin._resolved_token = "old"

    plugin.api_key_command = "  pass show b  "
    assert plugin._resolved_token is None
    config = albert.PluginInstance._CONFIG
    assert config[("python.mock", jellyseerr.CONFIG_API_TOKEN_COMMAND)] == "pass show b"


def test_changing_the_key_forgets_the_resolved_key():
    plugin = make_plugin()
    plugin._resolved_token = "old"

    plugin.api_key = "new"
    assert plugin._resolved_token is None


# -- error and crash items -------------------------------------------------------------------


def test_a_jellyseerr_error_becomes_a_retry_item(monkeypatch, offline):
    def boom(*args, **kwargs):
        raise jellyseerr.JellyseerrError("the server said no")

    monkeypatch.setattr(jellyseerr, "fetch_requests", boom)
    plugin = make_plugin()

    items = next(plugin.items(FakeCtx("")))
    assert items[0].text == "the server said no"
    assert items[0].actions[0].id == "retry"


def test_an_unexpected_error_becomes_a_crash_item(monkeypatch, offline):
    def boom(*args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(jellyseerr, "fetch_requests", boom)
    plugin = make_plugin()

    items = next(plugin.items(FakeCtx("")))
    assert "Something went wrong" in items[0].text
    assert items[0].actions[0].id == "copy"


# -- actions ---------------------------------------------------------------------------------


def test_approving_a_request_notifies_and_invalidates(monkeypatch):
    recorded = []
    monkeypatch.setattr(jellyseerr, "set_request_status", lambda *args: recorded.append(args))

    plugin = make_plugin()
    plugin._requests = (time.monotonic(), [])
    item = plugin._request_item(movie_request(), {"movie:550": "Fight Club"})

    item.actions[0].callable()

    assert plugin._requests is None
    assert wait_for(lambda: ("Jellyseerr", "Approved Fight Club") in albert.Notification.SENT)
    assert recorded == [(BASE, TOKEN, 1, "approve")]


def test_declining_a_request_notifies(monkeypatch):
    recorded = []
    monkeypatch.setattr(jellyseerr, "set_request_status", lambda *args: recorded.append(args))

    plugin = make_plugin()
    item = plugin._request_item(movie_request(), {"movie:550": "Fight Club"})
    item.actions[1].callable()

    assert wait_for(lambda: ("Jellyseerr", "Declined Fight Club") in albert.Notification.SENT)
    assert recorded == [(BASE, TOKEN, 1, "decline")]


def test_requesting_a_hit_notifies(monkeypatch):
    recorded = []
    monkeypatch.setattr(jellyseerr, "create_request", lambda *args: recorded.append(args))

    plugin = make_plugin()
    item = plugin._result_item(movie_result(status=jellyseerr.MEDIA_UNKNOWN))
    item.actions[0].callable()

    assert wait_for(lambda: ("Jellyseerr", "Requested Fight Club") in albert.Notification.SENT)
    assert recorded == [(BASE, TOKEN, "movie", 550)]


def test_a_failed_action_is_reported(monkeypatch):
    def boom(*args, **kwargs):
        raise jellyseerr.JellyseerrError("could not approve")

    monkeypatch.setattr(jellyseerr, "set_request_status", boom)

    plugin = make_plugin()
    item = plugin._request_item(movie_request(), {"movie:550": "Fight Club"})
    item.actions[0].callable()

    assert wait_for(lambda: ("Jellyseerr", "could not approve") in albert.Notification.SENT)


def test_mutate_reports_a_jellyseerr_error():
    def work():
        raise jellyseerr.JellyseerrError("nope")

    jellyseerr.Plugin._mutate(work, "should not appear")
    assert ("Jellyseerr", "nope") in albert.Notification.SENT
    assert ("Jellyseerr", "should not appear") not in albert.Notification.SENT


def test_mutate_reports_an_unexpected_error():
    def work():
        raise ValueError("bad thing")

    jellyseerr.Plugin._mutate(work, "should not appear")
    assert ("Jellyseerr", "ValueError: bad thing") in albert.Notification.SENT


# -- configuration and metadata --------------------------------------------------------------


def test_init_reads_and_strips_the_config():
    config = albert.PluginInstance._CONFIG
    config[("python.mock", jellyseerr.CONFIG_URL)] = "  http://x  "
    config[("python.mock", jellyseerr.CONFIG_API_TOKEN)] = "  tok  "
    config[("python.mock", jellyseerr.CONFIG_API_TOKEN_COMMAND)] = "  cmd  "

    plugin = jellyseerr.Plugin()
    assert plugin.jellyseerr_url == "http://x"
    assert plugin.api_key == "tok"
    assert plugin.api_key_command == "cmd"
    assert plugin._resolved_token is None


def test_setting_the_url_writes_it_and_forgets_the_cache():
    plugin = make_plugin()
    plugin._requests = (time.monotonic(), [])

    plugin.jellyseerr_url = "  http://new  "
    assert plugin.jellyseerr_url == "http://new"
    assert albert.PluginInstance._CONFIG[("python.mock", jellyseerr.CONFIG_URL)] == "http://new"
    assert plugin._requests is None


def test_setting_the_key_writes_it_and_forgets_the_cache():
    plugin = make_plugin()
    plugin._requests = (time.monotonic(), [])

    plugin.api_key = "  newkey  "
    assert plugin.api_key == "newkey"
    stored = albert.PluginInstance._CONFIG[("python.mock", jellyseerr.CONFIG_API_TOKEN)]
    assert stored == "newkey"
    assert plugin._requests is None


def test_the_config_widget_has_a_url_and_a_masked_key():
    widget = jellyseerr.Plugin.configWidget(make_plugin())
    fields = [entry for entry in widget if entry.get("property")]

    assert [field["property"] for field in fields] == [
        "jellyseerr_url",
        "api_key",
        "api_key_command",
    ]
    key = next(field for field in fields if field["property"] == "api_key")
    assert key["widget_properties"]["echoMode"] == 2
    assert widget[0]["type"] == "label"


def test_the_trigger_and_synopsis():
    plugin = make_plugin()
    assert plugin.defaultTrigger() == "seerr "
    assert plugin.synopsis("") == "a title, or nothing for the recent requests"


def test_the_icon_file_exists():
    assert (jellyseerr.ICON_DIR / "jellyseerr.svg").is_file()


def test_the_icon_is_loaded_from_that_file():
    icon = jellyseerr.Plugin.makeIcon()
    assert str(jellyseerr.ICON_PATH) in str(icon)
