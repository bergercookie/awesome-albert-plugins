"""Tests for the trakt plugin.

`requests` is monkeypatched rather than mocked wholesale, so the real exception
types are in play: what is checked is how a Trakt answer - including the ugly
ones - is turned into an item, and that is the part that breaks when the API
changes.

The plugin talks to exactly two hosts, both Trakt's own, so nothing here
reaches out. The high-level helpers are monkeypatched for the item tests;
`call` itself is driven through a fake `requests.request` so its headers,
parameters and error handling are exercised for real.
"""

import threading
import time

import albert
import pytest
import requests

from conftest import load_plugin

trakt = load_plugin("trakt")

KEY = "client-id"
SECRET = "client-secret"
ACCESS = "access-token"
REFRESH = "refresh-token"


# -- harness ---------------------------------------------------------------------------------


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
    monkeypatch.setattr(trakt.requests, "request", handler)
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


class FakeCtx:
    def __init__(self, query, valid=True):
        self.query = query
        self.isValid = valid


def make_plugin(api_key=KEY, api_secret=SECRET, access="", refresh="", username=""):
    """A plugin instance without going through __init__ (no config, no disk)."""
    plugin = trakt.Plugin.__new__(trakt.Plugin)
    plugin._api_key = api_key
    plugin._api_secret = api_secret
    plugin._access_token = access
    plugin._refresh_token = refresh
    plugin._username = username
    plugin._lock = threading.Lock()
    plugin._searches = {}
    plugin._generation = 0
    plugin._signing_in = False
    plugin._pending = None
    plugin._pending_deadline = 0.0
    return plugin


class Clock:
    """A monotonic clock that only moves when slept."""

    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += seconds


def wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


# -- sample payloads -------------------------------------------------------------------------


def movie_hit(trakt_id=550, title="Fight Club", year=1999, slug="fight-club"):
    ids = {"trakt": trakt_id, "slug": slug, "imdb": "tt0137523"}
    return {"type": "movie", "movie": {"title": title, "year": year, "ids": ids}}


def show_hit(trakt_id=1396, title="Breaking Bad", year=2008, slug="breaking-bad"):
    ids = {"trakt": trakt_id, "slug": slug, "tvdb": 81189}
    return {"type": "show", "show": {"title": title, "year": year, "ids": ids}}


def person_hit():
    return {
        "type": "person",
        "person": {"name": "David Fincher", "ids": {"trakt": 1, "slug": "david-fincher"}},
    }


# -- join_url and api_headers ----------------------------------------------------------------


@pytest.mark.parametrize(
    "base, path, expected",
    [
        ("https://api.trakt.tv", "/search/movie", "https://api.trakt.tv/search/movie"),
        ("https://auth.trakt.tv/", "oauth/device/code", "https://auth.trakt.tv/oauth/device/code"),
        ("https://api.trakt.tv", "users/settings", "https://api.trakt.tv/users/settings"),
    ],
)
def test_join_url(base, path, expected):
    assert trakt.join_url(base, path) == expected


def test_api_headers_carry_the_version_and_the_key():
    headers = trakt.api_headers(KEY)
    assert headers["trakt-api-version"] == "2"
    assert headers["trakt-api-key"] == KEY
    assert headers["Content-Type"] == "application/json"
    assert "User-Agent" in headers


def test_api_headers_without_a_token_are_unauthorized():
    assert "Authorization" not in trakt.api_headers(KEY)


def test_api_headers_with_a_token_bear_it():
    assert trakt.api_headers(KEY, ACCESS)["Authorization"] == f"Bearer {ACCESS}"


# -- call ------------------------------------------------------------------------------------


def test_call_returns_the_decoded_body(http):
    http.response = FakeResponse({"a": 1})
    assert trakt.call("GET", "users/settings", KEY) == {"a": 1}


def test_call_sends_the_trakt_headers(http):
    trakt.call("GET", "users/settings", KEY, access_token=ACCESS)

    call = http.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == "https://api.trakt.tv/users/settings"
    assert call["headers"]["trakt-api-key"] == KEY
    assert call["headers"]["trakt-api-version"] == "2"
    assert call["headers"]["Authorization"] == f"Bearer {ACCESS}"
    assert call["timeout"] == trakt.HTTP_TIMEOUT


def test_call_omits_the_authorization_header_without_a_token(http):
    trakt.call("GET", "search/movie,show", KEY)
    assert "Authorization" not in http.calls[0]["headers"]


def test_call_forwards_params_and_body(http):
    trakt.call("POST", "sync/ratings", KEY, access_token=ACCESS, body={"movies": []})

    call = http.calls[0]
    assert call["url"] == "https://api.trakt.tv/sync/ratings"
    assert call["json"] == {"movies": []}
    assert "params" not in call


def test_call_percent_encodes_parameter_values(http):
    trakt.call("GET", "search/movie,show", KEY, params={"query": "fight club", "limit": 20})
    assert http.calls[0]["url"] == (
        "https://api.trakt.tv/search/movie,show?query=fight%20club&limit=20"
    )
    # params are baked into the url, not handed to requests, which would use "+"
    assert "params" not in http.calls[0]


def test_call_encodes_other_reserved_characters(http):
    trakt.call("GET", "search/movie,show", KEY, params={"query": "C++ & more"})
    assert http.calls[0]["url"] == "https://api.trakt.tv/search/movie,show?query=C%2B%2B%20%26%20more"


def test_call_omits_params_and_body_when_not_given(http):
    trakt.call("GET", "users/settings", KEY)
    assert "params" not in http.calls[0]
    assert "json" not in http.calls[0]


def test_call_can_be_pointed_at_the_auth_host(http):
    trakt.call("POST", "oauth/device/code", KEY, body={"client_id": KEY}, base=trakt.AUTH_BASE)
    assert http.calls[0]["url"] == "https://auth.trakt.tv/oauth/device/code"


def test_call_refuses_an_empty_api_key(http):
    with pytest.raises(trakt.TraktError, match="No Trakt API key"):
        trakt.call("GET", "users/settings", "")
    assert http.calls == []


def test_call_reports_a_timeout(http):
    http.response = requests.Timeout()
    with pytest.raises(trakt.TraktError, match="did not answer within 10s"):
        trakt.call("GET", "users/settings", KEY)


def test_call_reports_an_unreachable_server(http):
    http.response = requests.ConnectionError("no route to host")
    with pytest.raises(trakt.TraktError, match="Cannot reach Trakt"):
        trakt.call("GET", "users/settings", KEY)


def test_call_surfaces_a_non_json_body(http):
    http.response = FakeResponse(json_error=True, status=200)
    with pytest.raises(trakt.TraktError, match="did not answer with JSON"):
        trakt.call("GET", "users/settings", KEY)


def test_call_explains_a_401_with_the_settings_hint(http):
    http.response = FakeResponse({"message": "OAuth token not provided"}, status=401)
    with pytest.raises(trakt.TraktHttpError) as exc:
        trakt.call("GET", "sync/ratings", KEY)

    message = str(exc.value)
    assert exc.value.status == 401
    assert "HTTP 401" in message
    assert "OAuth token not provided" in message
    assert "plugin settings" in message


def test_call_explains_a_403_the_same_way(http):
    http.response = FakeResponse({"message": "forbidden"}, status=403)
    with pytest.raises(trakt.TraktHttpError, match="plugin settings"):
        trakt.call("GET", "users/settings", KEY)


def test_call_surfaces_the_service_message(http):
    http.response = FakeResponse({"message": "Retry later, rate limit exceeded."}, status=429)
    with pytest.raises(trakt.TraktHttpError) as exc:
        trakt.call("GET", "search/movie,show", KEY)

    message = str(exc.value)
    assert "HTTP 429" in message
    assert "rate limit exceeded" in message
    # a rate limit is not a credentials problem, so the settings hint must not be there
    assert "plugin settings" not in message


def test_call_quotes_an_html_error_page(http):
    http.response = FakeResponse(
        json_error=True, status=502, text="<html>\n  <body>Bad Gateway</body>\n</html>"
    )
    with pytest.raises(trakt.TraktHttpError, match=r"HTTP 502.*Bad Gateway"):
        trakt.call("GET", "users/settings", KEY)


# -- fetch_search ----------------------------------------------------------------------------


def test_fetch_search_returns_movies_and_shows_only(http):
    http.response = FakeResponse([movie_hit(), show_hit(), person_hit(), {"type": "list"}])
    assert trakt.fetch_search(KEY, "", "fight") == [movie_hit(), show_hit()]

    call = http.calls[0]
    assert call["url"] == "https://api.trakt.tv/search/movie,show?query=fight&limit=20"


def test_fetch_search_passes_the_access_token_when_there_is_one(http):
    http.response = FakeResponse([])
    trakt.fetch_search(KEY, ACCESS, "fight")
    assert http.calls[0]["headers"]["Authorization"] == f"Bearer {ACCESS}"


def test_fetch_search_forwards_its_limit(http):
    http.response = FakeResponse([])
    trakt.fetch_search(KEY, "", "fight", limit=5)
    assert http.calls[0]["url"].endswith("query=fight&limit=5")


def test_fetch_search_rejects_an_unexpected_body(http):
    http.response = FakeResponse({"nonsense": True})
    with pytest.raises(trakt.TraktError, match="something unexpected"):
        trakt.fetch_search(KEY, "", "fight")


# -- rating_body and submit_rating -----------------------------------------------------------


def test_rating_body_names_the_plural_media_type():
    assert trakt.rating_body("movie", 550, 8) == {
        "movies": [{"ids": {"trakt": 550}, "rating": 8}]
    }
    assert trakt.rating_body("show", 1396, 8.5) == {
        "shows": [{"ids": {"trakt": 1396}, "rating": 8.5}]
    }


def test_rating_body_refuses_an_unknown_media_type():
    with pytest.raises(trakt.TraktError, match="Not a media type"):
        trakt.rating_body("person", 1, 8)


def test_submit_rating_posts_to_the_sync_endpoint(http):
    http.response = FakeResponse({"added": {"movies": 1, "shows": 0}, "not_found": {}})
    assert trakt.submit_rating(KEY, ACCESS, "movie", 550, 8) == {
        "added": {"movies": 1, "shows": 0},
        "not_found": {},
    }

    call = http.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://api.trakt.tv/sync/ratings"
    assert call["json"] == {"movies": [{"ids": {"trakt": 550}, "rating": 8}]}
    assert call["headers"]["Authorization"] == f"Bearer {ACCESS}"


def test_submit_rating_reports_an_unrated_movie(http):
    http.response = FakeResponse(
        {
            "added": {"movies": 0},
            "not_found": {"movies": [{"ids": {"trakt": 999}}], "shows": []},
        }
    )
    with pytest.raises(trakt.TraktError, match="does not know this movie"):
        trakt.submit_rating(KEY, ACCESS, "movie", 999, 8)


def test_submit_rating_reports_an_unrated_show(http):
    http.response = FakeResponse(
        {"added": {"shows": 0}, "not_found": {"movies": [], "shows": [{"ids": {"trakt": 7}}]}}
    )
    with pytest.raises(trakt.TraktError, match="does not know this show"):
        trakt.submit_rating(KEY, ACCESS, "show", 7, 8)


def test_submit_rating_rejects_a_body_that_is_not_an_object(http):
    http.response = FakeResponse([])
    with pytest.raises(trakt.TraktError, match="did not answer the rating"):
        trakt.submit_rating(KEY, ACCESS, "movie", 550, 8)


# -- the device-code sign-in -----------------------------------------------------------------


def test_request_device_code_asks_the_auth_host(http):
    http.response = FakeResponse({"device_code": "d", "user_code": "ABC123"})
    device = trakt.request_device_code(KEY)

    assert device["user_code"] == "ABC123"
    call = http.calls[0]
    assert call["url"] == "https://auth.trakt.tv/oauth/device/code"
    assert call["json"] == {"client_id": KEY}


def test_request_device_code_rejects_a_body_without_a_device_code(http):
    http.response = FakeResponse({"user_code": "ABC123"})
    with pytest.raises(trakt.TraktError, match="did not hand back a device code"):
        trakt.request_device_code(KEY)


def test_request_device_code_rejects_a_body_that_is_not_an_object(http):
    http.response = FakeResponse([])
    with pytest.raises(trakt.TraktError, match="did not hand back a device code"):
        trakt.request_device_code(KEY)


def test_poll_device_token_grants_a_200(http):
    http.response = FakeResponse({"access_token": ACCESS, "refresh_token": REFRESH})
    state, payload = trakt.poll_device_token(KEY, SECRET, "d-code")

    assert state == "granted"
    assert payload == {"access_token": ACCESS, "refresh_token": REFRESH}
    assert http.calls[0]["json"] == {
        "code": "d-code",
        "client_id": KEY,
        "client_secret": SECRET,
    }


def test_poll_device_token_reads_a_400_as_pending(http):
    http.response = FakeResponse(status=400)
    assert trakt.poll_device_token(KEY, SECRET, "d-code") == ("pending", None)


def test_poll_device_token_reads_a_429_as_slow_down(http):
    http.response = FakeResponse(status=429)
    assert trakt.poll_device_token(KEY, SECRET, "d-code") == ("slow_down", None)


@pytest.mark.parametrize(
    "status, message",
    [
        (404, "not valid"),
        (409, "already been used"),
        (410, "expired"),
        (418, "denied"),
    ],
)
def test_poll_device_token_explains_a_terminal_status(http, status, message):
    http.response = FakeResponse(status=status)
    with pytest.raises(trakt.TraktError, match=message):
        trakt.poll_device_token(KEY, SECRET, "d-code")


def test_poll_device_token_rejects_a_200_without_a_token(http):
    http.response = FakeResponse({"expires_in": 600})
    with pytest.raises(trakt.TraktError, match="did not hand back an access token"):
        trakt.poll_device_token(KEY, SECRET, "d-code")


def test_poll_device_token_quotes_an_unexpected_status(http):
    http.response = FakeResponse({"message": "nope"}, status=418 - 1)
    with pytest.raises(trakt.TraktHttpError, match="HTTP 417"):
        trakt.poll_device_token(KEY, SECRET, "d-code")


DEVICE = {"device_code": "d", "user_code": "ABC123", "interval": 5, "expires_in": 600}


def test_await_device_token_polls_at_the_advertised_interval(monkeypatch):
    states = iter([("pending", None), ("granted", {"access_token": ACCESS})])
    monkeypatch.setattr(trakt, "poll_device_token", lambda *a: next(states))
    clock = Clock()

    payload = trakt.await_device_token(KEY, SECRET, DEVICE, sleep=clock.sleep, now=clock.now)

    assert payload == {"access_token": ACCESS}
    assert clock.sleeps == [5, 5]


def test_await_device_token_waits_longer_after_a_slow_down(monkeypatch):
    states = iter([("slow_down", None), ("granted", {"access_token": ACCESS})])
    monkeypatch.setattr(trakt, "poll_device_token", lambda *a: next(states))
    clock = Clock()

    trakt.await_device_token(KEY, SECRET, DEVICE, sleep=clock.sleep, now=clock.now)
    assert clock.sleeps == [5, 10]


def test_await_device_token_caps_a_slow_down(monkeypatch):
    states = iter([("slow_down", None), ("granted", {"access_token": ACCESS})])
    monkeypatch.setattr(trakt, "poll_device_token", lambda *a: next(states))
    clock = Clock()
    device = dict(DEVICE, interval=58)

    trakt.await_device_token(KEY, SECRET, device, sleep=clock.sleep, now=clock.now)
    assert clock.sleeps == [58, 60]


def test_await_device_token_gives_up_when_the_code_expires(monkeypatch):
    monkeypatch.setattr(trakt, "poll_device_token", lambda *a: ("pending", None))
    clock = Clock()
    device = dict(DEVICE, expires_in=10)

    with pytest.raises(trakt.TraktError, match="expired before it was approved"):
        trakt.await_device_token(KEY, SECRET, device, sleep=clock.sleep, now=clock.now)
    assert clock.sleeps == [5, 5]


def test_await_device_token_refuses_a_payload_without_a_device_code(monkeypatch):
    def fail(*args):
        raise AssertionError("must not poll without a device code")

    monkeypatch.setattr(trakt, "poll_device_token", fail)
    with pytest.raises(trakt.TraktError, match="did not hand back a device code"):
        trakt.await_device_token(KEY, SECRET, {"interval": 5})


def test_await_device_token_propagates_a_denial(monkeypatch):
    def denied(*args):
        raise trakt.TraktError("The sign-in was denied on trakt.tv.")

    monkeypatch.setattr(trakt, "poll_device_token", denied)
    with pytest.raises(trakt.TraktError, match="denied"):
        trakt.await_device_token(KEY, SECRET, DEVICE, sleep=lambda s: None, now=lambda: 0.0)


# -- refresh_tokens and fetch_username -------------------------------------------------------


def test_refresh_tokens_posts_the_whole_pair(http):
    http.response = FakeResponse(
        {"access_token": "new-access", "refresh_token": "new-refresh"}
    )
    payload = trakt.refresh_tokens(KEY, SECRET, REFRESH)

    assert payload == {"access_token": "new-access", "refresh_token": "new-refresh"}
    call = http.calls[0]
    assert call["url"] == "https://auth.trakt.tv/oauth/token"
    assert call["json"] == {
        "refresh_token": REFRESH,
        "client_id": KEY,
        "client_secret": SECRET,
        "grant_type": "refresh_token",
    }


def test_refresh_tokens_rejects_a_body_without_a_token(http):
    http.response = FakeResponse({"token_type": "bearer"})
    with pytest.raises(trakt.TraktError, match="did not hand back an access token"):
        trakt.refresh_tokens(KEY, SECRET, REFRESH)


def test_fetch_username_reads_the_settings(http):
    http.response = FakeResponse({"user": {"username": "alice", "ids": {}}})
    assert trakt.fetch_username(KEY, ACCESS) == "alice"
    assert http.calls[0]["url"] == "https://api.trakt.tv/users/settings"


def test_fetch_username_is_empty_when_the_payload_is_junk(http):
    http.response = FakeResponse({"user": "nope"})
    assert trakt.fetch_username(KEY, ACCESS) == ""

    http.response = FakeResponse([])
    assert trakt.fetch_username(KEY, ACCESS) == ""


# -- reading the search hits -----------------------------------------------------------------


def test_hit_media_type_accepts_only_movies_and_shows():
    assert trakt.hit_media_type(movie_hit()) == "movie"
    assert trakt.hit_media_type(show_hit()) == "show"
    assert trakt.hit_media_type(person_hit()) == ""
    assert trakt.hit_media_type({}) == ""


def test_hit_object_is_the_payload_the_type_names():
    assert trakt.hit_object(movie_hit())["title"] == "Fight Club"
    assert trakt.hit_object({"type": "movie"}) == {}
    assert trakt.hit_object({}) == {}


def test_hit_title_and_year():
    assert trakt.hit_title(movie_hit()) == "Fight Club"
    assert trakt.hit_year(movie_hit()) == "1999"
    assert trakt.hit_year({"type": "movie", "movie": {"year": "1999"}}) == "1999"
    assert trakt.hit_year({"type": "movie", "movie": {}}) == ""
    assert trakt.hit_year({"type": "movie", "movie": {"year": True}}) == ""


def test_hit_ids_and_trakt_id():
    assert trakt.hit_trakt_id(movie_hit()) == 550
    assert trakt.hit_trakt_id({"type": "movie", "movie": {"ids": {}}}) is None
    assert trakt.hit_trakt_id({"type": "movie", "movie": {"ids": {"trakt": "x"}}}) is None
    assert trakt.hit_ids({}) == {}


def test_hit_slug():
    assert trakt.hit_slug(movie_hit()) == "fight-club"
    assert trakt.hit_slug({"type": "movie", "movie": {"ids": {"trakt": 1}}}) == ""


def test_hit_subtext_describes_the_hit():
    assert trakt.hit_subtext(movie_hit()) == "Movie | 1999"
    assert trakt.hit_subtext(show_hit()) == "Show | 2008"
    assert trakt.hit_subtext({"type": "movie", "movie": {}}) == "Movie"


# -- item_url --------------------------------------------------------------------------------


def test_item_url_prefers_the_slug():
    assert trakt.item_url(movie_hit()) == "https://trakt.tv/movies/fight-club"
    assert trakt.item_url(show_hit()) == "https://trakt.tv/shows/breaking-bad"


def test_item_url_falls_back_to_the_trakt_id():
    hit = {"type": "show", "show": {"title": "Severance", "ids": {"trakt": 900}}}
    assert trakt.item_url(hit) == "https://trakt.tv/search/trakt/900?type=show"


def test_item_url_points_home_when_the_payload_cannot_be_linked():
    assert trakt.item_url({"type": "movie", "movie": {"ids": {}}}) == "https://trakt.tv"
    assert trakt.item_url(person_hit()) == "https://trakt.tv"
    assert trakt.item_url({}) == "https://trakt.tv"


# -- parse_rating and parse_query ------------------------------------------------------------


@pytest.mark.parametrize(
    "word, expected",
    [
        ("1", 1),
        ("8", 8),
        ("10", 10),
        ("8.5", 8.5),
        ("0", None),
        ("11", None),
        ("7.25", None),
        ("x", None),
        ("", None),
        ("nan", None),
        ("inf", None),
    ],
)
def test_parse_rating(word, expected):
    assert trakt.parse_rating(word) == expected


def test_parse_query_reads_the_empty_query_as_status():
    assert trakt.parse_query("").mode == "status"
    assert trakt.parse_query("   ").mode == "status"


def test_parse_query_reads_a_plain_title_as_a_search():
    query = trakt.parse_query("  fight   club ")
    assert query.mode == "search"
    assert query.term == "fight club"
    assert query.rating is None


def test_parse_query_reads_the_rate_grammar():
    query = trakt.parse_query("rate 8 fight club")
    assert (query.mode, query.rating, query.term) == ("rate", 8, "fight club")

    query = trakt.parse_query("rate 8.5 fight club")
    assert query.rating == 8.5


def test_parse_query_is_case_insensitive_on_the_rate_word():
    assert trakt.parse_query("Rate 8 fight club").mode == "rate"


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("rate", "Rate with"),
        ("rate 8", "Rate with"),
        ("rate 11 fight", "Not a rating"),
        ("rate x fight", "Not a rating"),
    ],
)
def test_parse_query_explains_a_mistyped_rate(text, fragment):
    query = trakt.parse_query(text)
    assert query.mode == "error"
    assert fragment in query.message


# -- items: setup ----------------------------------------------------------------------------


def test_a_missing_key_is_asked_for_first():
    plugin = make_plugin(api_key="")
    (item,) = next(plugin.items(FakeCtx("")))

    assert "API key missing" in item.text
    assert item.actions[0].id == "open"


def test_setup_takes_precedence_over_the_query():
    plugin = make_plugin(api_key="")
    (item,) = next(plugin.items(FakeCtx("fight club")))
    assert "settings" in item.text


# -- items: the status list ------------------------------------------------------------------


def test_an_empty_query_offers_a_sign_in_when_signed_out():
    plugin = make_plugin()
    items = next(plugin.items(FakeCtx("")))

    sign_in = next(item for item in items if item.text == "Sign in to Trakt")
    assert sign_in.actions[0].id == "signin"


def test_an_empty_query_shows_the_signed_in_user():
    plugin = make_plugin(access=ACCESS, refresh=REFRESH, username="alice")
    items = next(plugin.items(FakeCtx("")))

    signed_in = next(item for item in items if "Signed in" in item.text)
    assert signed_in.text == "Signed in to Trakt as alice"
    assert [action.id for action in signed_in.actions] == ["open", "signout"]


def test_a_missing_secret_keeps_searching_but_hides_the_sign_in():
    plugin = make_plugin(api_secret="")
    items = next(plugin.items(FakeCtx("")))

    assert any("API secret" in item.text for item in items)
    assert all(item.text != "Sign in to Trakt" for item in items)


def test_a_pending_sign_in_shows_the_code_and_the_page():
    plugin = make_plugin()
    plugin._pending = dict(DEVICE, verification_url="https://auth.trakt.tv/activate")
    plugin._pending_deadline = time.monotonic() + 600

    items = next(plugin.items(FakeCtx("")))
    pending = items[0]
    assert "ABC123" in pending.text
    assert "auth.trakt.tv/activate" in pending.text
    assert [action.id for action in pending.actions] == ["open", "copy"]


def test_an_expired_pending_sign_in_is_not_shown():
    plugin = make_plugin()
    plugin._pending = dict(DEVICE)
    plugin._pending_deadline = time.monotonic() - 1

    items = next(plugin.items(FakeCtx("")))
    assert all("ABC123" not in item.text for item in items)


def test_the_pending_sign_in_sits_above_the_status_item():
    plugin = make_plugin(access=ACCESS, username="alice")
    plugin._pending = dict(DEVICE)
    plugin._pending_deadline = time.monotonic() + 600

    items = next(plugin.items(FakeCtx("")))
    assert "Waiting for sign-in" in items[0].text
    assert "Signed in" in items[1].text


# -- items: searching ------------------------------------------------------------------------


def test_a_search_lists_the_hits(monkeypatch):
    monkeypatch.setattr(trakt, "fetch_search", lambda *a, **k: [movie_hit(), show_hit()])
    plugin = make_plugin()

    items = next(plugin.items(FakeCtx("breaking")))
    assert [item.text for item in items] == ["Fight Club", "Breaking Bad"]
    assert items[0].actions[0].id == "open"


def test_a_search_hit_opens_its_trakt_page(monkeypatch):
    monkeypatch.setattr(trakt, "fetch_search", lambda *a, **k: [movie_hit()])
    urls = []

    plugin = make_plugin()
    items = next(plugin.items(FakeCtx("fight club")))
    items[0].actions[0].callable()
    urls = albert._CLIPBOARD.get("urls", [])
    assert urls[-1] == "https://trakt.tv/movies/fight-club"


def test_a_one_character_query_asks_for_more(monkeypatch):
    plugin = make_plugin()
    items = next(plugin.items(FakeCtx("f")))

    assert "Search Trakt for f" in items[0].text
    assert items[0].input_action_text == ""


def test_a_search_without_hits_says_so(monkeypatch):
    monkeypatch.setattr(trakt, "fetch_search", lambda *a, **k: [])
    plugin = make_plugin()

    items = next(plugin.items(FakeCtx("zzzz")))
    assert "Nothing on Trakt matches" in items[0].text


def test_the_search_is_capped(monkeypatch):
    hits = [movie_hit(trakt_id=index, title=f"Title {index}", slug="") for index in range(5)]
    monkeypatch.setattr(trakt, "fetch_search", lambda *a, **k: hits)
    monkeypatch.setattr(trakt, "SEARCH_LIMIT", 2)
    plugin = make_plugin()

    items = next(plugin.items(FakeCtx("title")))
    assert [item.text for item in items] == ["Title 0", "Title 1"]


def test_a_search_works_without_a_secret(monkeypatch):
    monkeypatch.setattr(trakt, "fetch_search", lambda *a, **k: [movie_hit()])
    plugin = make_plugin(api_secret="")

    items = next(plugin.items(FakeCtx("fight")))
    assert [item.text for item in items] == ["Fight Club"]


def test_a_cancelled_query_is_not_searched(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("a cancelled query must not reach the network")

    monkeypatch.setattr(trakt, "fetch_search", fail)
    plugin = make_plugin()

    assert list(plugin.items(FakeCtx("fight", valid=False))) == []


def test_the_search_sends_the_configured_key(monkeypatch):
    seen = {}

    def fake_search(api_key, access_token, term, limit=20):
        seen["api_key"], seen["access_token"], seen["term"] = api_key, access_token, term
        return []

    monkeypatch.setattr(trakt, "fetch_search", fake_search)
    make_plugin(api_key="my-key")._search("fight")
    assert seen == {"api_key": "my-key", "access_token": "", "term": "fight"}


# -- items: rating ---------------------------------------------------------------------------


def test_rate_mode_without_a_session_asks_for_the_sign_in(monkeypatch):
    plugin = make_plugin()
    (item,) = next(plugin.items(FakeCtx("rate 8 fight club")))

    assert "Sign in to Trakt to rate titles" in item.text
    assert item.actions[0].id == "signin"


def test_rate_mode_rates_the_hits_with_enter(monkeypatch):
    monkeypatch.setattr(trakt, "fetch_search", lambda *a, **k: [movie_hit()])
    recorded = []
    monkeypatch.setattr(
        trakt, "submit_rating", lambda *a: recorded.append(a) or {"added": {"movies": 1}}
    )

    plugin = make_plugin(access=ACCESS)
    items = next(plugin.items(FakeCtx("rate 8 fight club")))

    assert items[0].actions[0].id == "rate"
    assert "Fight Club 8/10" in items[0].actions[0].text
    assert items[0].subtext.endswith("| rate 8/10")

    items[0].actions[0].callable()
    assert wait_for(lambda: ("Trakt", "Rated Fight Club 8/10") in albert.Notification.SENT)
    assert recorded == [(KEY, ACCESS, "movie", 550, 8)]


def test_rate_mode_without_hits_says_so(monkeypatch):
    monkeypatch.setattr(trakt, "fetch_search", lambda *a, **k: [])
    plugin = make_plugin(access=ACCESS)

    items = next(plugin.items(FakeCtx("rate 8 zzzz")))
    assert "Nothing on Trakt matches" in items[0].text


def test_a_mistyped_rate_word_becomes_a_usage_item(monkeypatch):
    plugin = make_plugin(access=ACCESS)
    items = next(plugin.items(FakeCtx("rate x fight")))
    assert "Not a rating Trakt knows" in items[0].text
    assert items[0].actions[0].id == "open"


# -- the caches ------------------------------------------------------------------------------


def test_a_search_is_fetched_once_within_the_ttl(monkeypatch):
    calls = []

    def fake_fetch(*args, **kwargs):
        calls.append(args)
        return []

    monkeypatch.setattr(trakt, "fetch_search", fake_fetch)
    plugin = make_plugin()

    plugin._search("fight")
    plugin._search("fight")
    assert len(calls) == 1


def test_the_search_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(trakt, "SEARCH_CACHE_SIZE", 3)
    monkeypatch.setattr(trakt, "fetch_search", lambda *a, **k: [])
    plugin = make_plugin()

    for term in "abcd":
        plugin._search(term)
    assert len(plugin._searches) == 3
    assert "a" not in plugin._searches


def test_forget_drops_the_search_cache(monkeypatch):
    monkeypatch.setattr(trakt, "fetch_search", lambda *a, **k: [])
    plugin = make_plugin()
    plugin._search("fight")

    plugin._forget()
    assert plugin._searches == {}


# -- the session: refreshing on a 401 --------------------------------------------------------


def test_a_401_refreshes_the_session_and_retries(monkeypatch):
    calls = []

    def fake_submit(api_key, access_token, media_type, trakt_id, rating):
        calls.append(access_token)
        if len(calls) == 1:
            raise trakt.TraktHttpError(401, "token expired")
        return {"added": {"movies": 1}}

    monkeypatch.setattr(trakt, "submit_rating", fake_submit)
    monkeypatch.setattr(
        trakt,
        "refresh_tokens",
        lambda api_key, api_secret, refresh: {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
        },
    )

    plugin = make_plugin(access="old-access", refresh="old-refresh")
    plugin._submit_rating("movie", 550, 8)

    assert calls == ["old-access", "new-access"]
    assert plugin._access_token == "new-access"
    assert plugin._refresh_token == "new-refresh"
    config = albert.PluginInstance._CONFIG
    assert config[("python.mock", trakt.CONFIG_ACCESS_TOKEN)] == "new-access"
    assert config[("python.mock", trakt.CONFIG_REFRESH_TOKEN)] == "new-refresh"


def test_a_failed_refresh_drops_the_session(monkeypatch):
    def fake_submit(*args):
        raise trakt.TraktHttpError(401, "token expired")

    def bad_refresh(*args):
        raise trakt.TraktError("refresh token is invalid")

    monkeypatch.setattr(trakt, "submit_rating", fake_submit)
    monkeypatch.setattr(trakt, "refresh_tokens", bad_refresh)

    plugin = make_plugin(access="old-access", refresh="old-refresh", username="alice")
    with pytest.raises(trakt.TraktError, match="refresh token is invalid"):
        plugin._submit_rating("movie", 550, 8)

    assert plugin._access_token == ""
    assert plugin._refresh_token == ""
    assert plugin._username == ""
    config = albert.PluginInstance._CONFIG
    assert config[("python.mock", trakt.CONFIG_ACCESS_TOKEN)] == ""
    assert config[("python.mock", trakt.CONFIG_REFRESH_TOKEN)] == ""


def test_a_401_without_a_refresh_token_is_not_retried(monkeypatch):
    def fake_submit(*args):
        raise trakt.TraktHttpError(401, "token expired")

    refreshes = []
    monkeypatch.setattr(trakt, "submit_rating", fake_submit)
    monkeypatch.setattr(trakt, "refresh_tokens", lambda *a: refreshes.append(a))

    plugin = make_plugin(access="old-access", refresh="")
    with pytest.raises(trakt.TraktHttpError):
        plugin._submit_rating("movie", 550, 8)
    assert refreshes == []


def test_a_non_401_is_not_retried(monkeypatch):
    def fake_submit(*args):
        raise trakt.TraktHttpError(404, "no such thing")

    refreshes = []
    monkeypatch.setattr(trakt, "submit_rating", fake_submit)
    monkeypatch.setattr(trakt, "refresh_tokens", lambda *a: refreshes.append(a))

    plugin = make_plugin(access="tok", refresh="r")
    with pytest.raises(trakt.TraktHttpError):
        plugin._submit_rating("movie", 550, 8)
    assert refreshes == []


def test_a_refresh_that_raced_onto_another_one_reuses_its_session(monkeypatch):
    """The generation counter: a second caller must not spend the token twice."""

    def racing_refresh(api_key, api_secret, refresh):
        # somebody else refreshed while this call waited for the lock
        plugin._generation += 1
        plugin._access_token = "new-access"
        return {"access_token": "ignored"}

    monkeypatch.setattr(trakt, "refresh_tokens", racing_refresh)

    plugin = make_plugin(access="old-access", refresh="old-refresh")
    plugin._refresh_session()

    assert plugin._access_token == "new-access"
    assert plugin._refresh_token == "old-refresh"


# -- signing in ------------------------------------------------------------------------------


def device_payload():
    return {"device_code": "d", "user_code": "ABC123", "interval": 5, "expires_in": 600}


def test_sign_in_stores_the_session_and_the_username(monkeypatch):
    monkeypatch.setattr(trakt, "request_device_code", lambda api_key: device_payload())
    monkeypatch.setattr(
        trakt,
        "await_device_token",
        lambda api_key, api_secret, device: {
            "access_token": ACCESS,
            "refresh_token": REFRESH,
        },
    )
    monkeypatch.setattr(trakt, "fetch_username", lambda api_key, access_token: "alice")

    plugin = make_plugin()
    plugin._sign_in()

    assert plugin._access_token == ACCESS
    assert plugin._refresh_token == REFRESH
    assert plugin._username == "alice"
    assert plugin._pending is None
    assert plugin._signing_in is False

    config = albert.PluginInstance._CONFIG
    assert config[("python.mock", trakt.CONFIG_ACCESS_TOKEN)] == ACCESS
    assert config[("python.mock", trakt.CONFIG_REFRESH_TOKEN)] == REFRESH
    assert config[("python.mock", trakt.CONFIG_USERNAME)] == "alice"
    assert ("Trakt", "Signed in to Trakt as alice") in albert.Notification.SENT


def test_sign_in_announces_the_code_before_waiting(monkeypatch):
    monkeypatch.setattr(trakt, "request_device_code", lambda api_key: device_payload())
    monkeypatch.setattr(
        trakt,
        "await_device_token",
        lambda *a: {"access_token": ACCESS, "refresh_token": REFRESH},
    )
    monkeypatch.setattr(trakt, "fetch_username", lambda *a: "alice")

    plugin = make_plugin()
    plugin._sign_in()

    notices = [text for title, text in albert.Notification.SENT]
    assert any("ABC123" in text and "auth.trakt.tv/activate" in text for text in notices)


def test_the_pending_code_survives_until_the_wait_finishes(monkeypatch):
    monkeypatch.setattr(trakt, "request_device_code", lambda api_key: device_payload())
    seen = {}

    def slow_wait(api_key, api_secret, device):
        seen["pending"] = plugin._pending
        return {"access_token": ACCESS, "refresh_token": REFRESH}

    monkeypatch.setattr(trakt, "await_device_token", slow_wait)
    monkeypatch.setattr(trakt, "fetch_username", lambda *a: "alice")

    plugin = make_plugin()
    plugin._sign_in()

    assert seen["pending"]["user_code"] == "ABC123"
    assert plugin._pending is None


def test_a_denied_sign_in_is_reported_and_forgets_the_code(monkeypatch):
    monkeypatch.setattr(trakt, "request_device_code", lambda api_key: device_payload())

    def denied(api_key, api_secret, device):
        raise trakt.TraktError("The sign-in was denied on trakt.tv.")

    monkeypatch.setattr(trakt, "await_device_token", denied)

    plugin = make_plugin()
    plugin._sign_in()

    assert plugin._access_token == ""
    assert plugin._pending is None
    assert ("Trakt", "The sign-in was denied on trakt.tv.") in albert.Notification.SENT


def test_an_unexpected_sign_in_error_is_reported(monkeypatch):
    monkeypatch.setattr(trakt, "request_device_code", lambda api_key: device_payload())

    def boom(api_key, api_secret, device):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(trakt, "await_device_token", boom)

    plugin = make_plugin()
    plugin._sign_in()

    assert ("Trakt", "RuntimeError: kaboom") in albert.Notification.SENT


def test_sign_in_is_not_started_twice(monkeypatch):
    asked = []
    monkeypatch.setattr(trakt, "request_device_code", lambda api_key: asked.append(api_key))

    plugin = make_plugin()
    plugin._signing_in = True
    plugin._start_sign_in()

    assert asked == []
    assert plugin._signing_in is True


def test_sign_in_without_the_secret_says_so():
    plugin = make_plugin(api_secret="")
    plugin._start_sign_in()

    assert wait_for(
        lambda: any("API key and secret" in text for _, text in albert.Notification.SENT)
    )
    assert plugin._signing_in is False


def test_start_sign_in_runs_the_worker_on_a_thread(monkeypatch):
    done = threading.Event()

    def first_step(api_key):
        done.set()
        raise trakt.TraktError("stop here")

    monkeypatch.setattr(trakt, "request_device_code", first_step)

    plugin = make_plugin()
    plugin._start_sign_in()

    assert wait_for(done.is_set)
    assert wait_for(lambda: plugin._signing_in is False)


def test_signing_out_forgets_everything():
    plugin = make_plugin(access=ACCESS, refresh=REFRESH, username="alice")
    plugin._sign_out()

    assert plugin._access_token == ""
    assert plugin._refresh_token == ""
    assert plugin._username == ""
    config = albert.PluginInstance._CONFIG
    assert config[("python.mock", trakt.CONFIG_ACCESS_TOKEN)] == ""
    assert config[("python.mock", trakt.CONFIG_USERNAME)] == ""
    assert wait_for(lambda: ("Trakt", "Signed out of Trakt.") in albert.Notification.SENT)


# -- error and crash items -------------------------------------------------------------------


def test_a_trakt_error_becomes_a_retry_item(monkeypatch):
    def boom(*args, **kwargs):
        raise trakt.TraktError("the server said no")

    monkeypatch.setattr(trakt, "fetch_search", boom)
    plugin = make_plugin()

    items = next(plugin.items(FakeCtx("fight")))
    assert items[0].text == "the server said no"
    assert items[0].actions[0].id == "retry"


def test_an_unexpected_error_becomes_a_crash_item(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(trakt, "fetch_search", boom)
    plugin = make_plugin()

    items = next(plugin.items(FakeCtx("fight")))
    assert "Something went wrong" in items[0].text
    assert items[0].actions[0].id == "copy"


# -- actions ---------------------------------------------------------------------------------


def test_a_failed_rating_is_reported(monkeypatch):
    def boom(*args):
        raise trakt.TraktError("Trakt does not know this movie.")

    monkeypatch.setattr(trakt, "submit_rating", boom)

    plugin = make_plugin(access=ACCESS)
    item = plugin._rate_item(movie_hit(), 8)
    item.actions[0].callable()

    assert wait_for(
        lambda: ("Trakt", "Trakt does not know this movie.") in albert.Notification.SENT
    )


def test_mutate_reports_a_trakt_error():
    def work():
        raise trakt.TraktError("nope")

    trakt.Plugin._mutate(work, "should not appear")
    assert ("Trakt", "nope") in albert.Notification.SENT
    assert ("Trakt", "should not appear") not in albert.Notification.SENT


def test_mutate_reports_an_unexpected_error():
    def work():
        raise ValueError("bad thing")

    trakt.Plugin._mutate(work, "should not appear")
    assert ("Trakt", "ValueError: bad thing") in albert.Notification.SENT


# -- configuration and metadata --------------------------------------------------------------


def test_init_reads_and_strips_the_config():
    config = albert.PluginInstance._CONFIG
    config[("python.mock", trakt.CONFIG_API_KEY)] = "  key  "
    config[("python.mock", trakt.CONFIG_API_SECRET)] = "  secret  "
    config[("python.mock", trakt.CONFIG_ACCESS_TOKEN)] = "  access  "
    config[("python.mock", trakt.CONFIG_REFRESH_TOKEN)] = "  refresh  "
    config[("python.mock", trakt.CONFIG_USERNAME)] = "  alice  "

    plugin = trakt.Plugin()
    assert plugin.api_key == "key"
    assert plugin.api_secret == "secret"
    assert plugin._access_token == "access"
    assert plugin._refresh_token == "refresh"
    assert plugin._username == "alice"


def test_changing_the_key_writes_it_and_forgets_the_cache():
    plugin = make_plugin()
    plugin._searches["fight"] = (time.monotonic(), [])

    plugin.api_key = "  newkey  "
    assert plugin.api_key == "newkey"
    assert plugin._searches == {}
    config = albert.PluginInstance._CONFIG
    assert config[("python.mock", trakt.CONFIG_API_KEY)] == "newkey"


def test_changing_the_secret_writes_it_and_forgets_the_cache():
    plugin = make_plugin()
    plugin._searches["fight"] = (time.monotonic(), [])

    plugin.api_secret = "  newsecret  "
    assert plugin.api_secret == "newsecret"
    assert plugin._searches == {}
    config = albert.PluginInstance._CONFIG
    assert config[("python.mock", trakt.CONFIG_API_SECRET)] == "newsecret"


def test_the_config_widget_has_two_masked_fields():
    widget = trakt.Plugin.configWidget(make_plugin())
    fields = [entry for entry in widget if entry.get("property")]

    assert [field["property"] for field in fields] == ["api_key", "api_secret"]
    assert all(field["widget_properties"]["echoMode"] == 2 for field in fields)
    assert widget[0]["type"] == "label"


def test_the_trigger_and_synopsis():
    plugin = make_plugin()
    assert plugin.defaultTrigger() == "trakt "
    assert "rate <1-10> <title>" in plugin.synopsis("")


def test_the_icon_file_exists():
    assert (trakt.ICON_DIR / "trakt.svg").is_file()


def test_the_icon_is_loaded_from_that_file():
    icon = trakt.Plugin.makeIcon()
    assert str(trakt.ICON_PATH) in str(icon)
