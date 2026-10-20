"""Trakt - search movies and shows on trakt.tv and rate them.

The empty query shows whether the plugin is signed in, and starts a sign-in
when it is not. Anything typed is searched on trakt.tv and <ENTER> opens the hit
in the browser; `rate <1-10> <title>` instead rates it, which is the only thing
that needs a signed-in session.

Everything goes through Trakt's own API with the plugin's API key, and nothing
but api.trakt.tv and auth.trakt.tv is ever contacted.
"""

import math
import threading
import time
import traceback
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    NamedTuple,
    Optional,
    Sequence,
    Tuple,
    Union,
)
from urllib.parse import quote, urlencode

import requests
from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    Notification,
    PluginInstance,
    StandardItem,
    openUrl,
    setClipboardText,
)

md_iid = "5.0"
md_version = "0.1"
md_name = "Trakt"
md_description = "Search movies and shows on trakt.tv and rate them"
md_license = "MIT"
md_url = (
    "https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/trakt"
)
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["requests"]
md_bin_dependencies: List[str] = []

ICON_DIR = Path(__file__).parent
ICON_PATH = ICON_DIR / "trakt.svg"

CONFIG_API_KEY = "trakt_api_key"
CONFIG_API_SECRET = "trakt_api_secret"
CONFIG_ACCESS_TOKEN = "trakt_access_token"
CONFIG_REFRESH_TOKEN = "trakt_refresh_token"
CONFIG_USERNAME = "trakt_username"

# Trakt splits its API from its OAuth endpoints on purpose, and only the latter
# hands out and refreshes tokens.
API_BASE = "https://api.trakt.tv"
AUTH_BASE = "https://auth.trakt.tv"

# Where a device-code sign-in is approved by hand, and where an application -
# the source of the API key and secret - is registered.
ACTIVATE_URL = "https://auth.trakt.tv/activate"
APP_URL = "https://trakt.tv/oauth/applications"
TRAKT_HOME = "https://trakt.tv"

# Trakt is a public service on the far side of the internet, not a server on the
# same LAN.
HTTP_TIMEOUT = 10
# Trakt's search matches substrings, so a single character is most of the
# catalogue and not worth a round trip.
MIN_SEARCH_CHARS = 2
# A query is only searched once it stops moving. Albert cancels the previous
# query on every keystroke, so waiting here costs nothing while typing and turns
# a typed word into one search instead of one per letter.
SEARCH_DEBOUNCE = 0.15
# How long an answer is reused before Trakt is asked again.
SEARCH_TTL = 60.0
# How many hits of a search are turned into items.
SEARCH_LIMIT = 20
# Searched terms remembered, which is what makes backspacing over a word free
# instead of one request per deleted letter.
SEARCH_CACHE_SIZE = 8
# What a 429 on the device-token poll asks for on top of the current interval,
# and the most it may ever grow to.
POLL_SLOW_DOWN = 5
POLL_INTERVAL_MAX = 60
USER_AGENT = "awesome-albert-plugins/trakt"

# The two kinds of media Trakt's search returns that the plugin can act on, and
# what to call them. `person` and `list` results are dropped.
MEDIA_LABELS = {"movie": "Movie", "show": "Show"}
# Trakt spells the plural of a media type differently from its own type word:
# POST /sync/ratings takes "movies" and "shows".
MEDIA_PLURALS = {"movie": "movies", "show": "shows"}

RATING_MIN = 1
RATING_MAX = 10

# The device-token poll answers a poll that is too early with a bare status
# code rather than a body. 400 and 429 mean keep waiting; the rest end the
# sign-in, each with its own reason.
DEVICE_FAILURES = {
    404: "That device code is not valid.",
    409: "That device code has already been used.",
    410: "That device code expired. Sign in again.",
    418: "The sign-in was denied on trakt.tv.",
}


class TraktError(Exception):
    """A failure worth showing to the user as-is."""


class TraktHttpError(TraktError):
    """An error status from Trakt, carrying the status code it came with."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def notify(msg: str, app_name: str = md_name) -> None:
    Notification(app_name, msg).send()


# urls ----------------------------------------------------------------------------------------


def join_url(base: str, path: str) -> str:
    """Join *path* onto a Trakt host.

    >>> join_url("https://api.trakt.tv", "/search/movie")
    'https://api.trakt.tv/search/movie'
    >>> join_url("https://auth.trakt.tv/", "oauth/device/code")
    'https://auth.trakt.tv/oauth/device/code'
    """
    return base.rstrip("/") + "/" + path.lstrip("/")


def api_headers(api_key: str, access_token: str = "") -> Dict[str, str]:
    """The headers every Trakt request carries.

    The API key goes in `trakt-api-key` on every call, signed in or not; the
    bearer token is only there once a user has authorised the application.

    >>> headers = api_headers("key")
    >>> sorted(headers)
    ['Content-Type', 'User-Agent', 'trakt-api-key', 'trakt-api-version']
    >>> headers["trakt-api-version"], headers["trakt-api-key"]
    ('2', 'key')
    >>> api_headers("key", "token")["Authorization"]
    'Bearer token'
    """
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "trakt-api-version": "2",
        "trakt-api-key": api_key,
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


# talking to the servers ----------------------------------------------------------------------


def _request(
    method: str,
    path: str,
    api_key: str,
    access_token: str = "",
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    timeout: float = HTTP_TIMEOUT,
    base: str = API_BASE,
) -> Any:
    """One round trip, returning the raw response rather than a decoded body.

    The device-token poll needs the status code of a "not yet" answer, which is
    the one case where the body alone does not say enough.

    .. raises:: TraktError
    """
    if not api_key:
        raise TraktError(
            f"No Trakt API key is configured. Create an application at {APP_URL} "
            "and paste its Client ID in the plugin settings."
        )

    url = join_url(base, path)
    if params:
        url = f"{url}?{urlencode(params, quote_via=quote)}"

    kwargs: Dict[str, Any] = {
        "headers": api_headers(api_key, access_token),
        "timeout": timeout,
    }
    if body is not None:
        kwargs["json"] = body

    try:
        return requests.request(method, url, **kwargs)
    except requests.Timeout as e:
        raise TraktError(f"Trakt did not answer within {timeout:g}s.") from e
    except requests.RequestException as e:
        raise TraktError(f"Cannot reach Trakt: {e}") from e


def call(
    method: str,
    path: str,
    api_key: str,
    access_token: str = "",
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    timeout: float = HTTP_TIMEOUT,
    base: str = API_BASE,
) -> Any:
    """One round trip to Trakt, returning the decoded JSON body.

    .. raises:: TraktError
    """
    response = _request(method, path, api_key, access_token, params, body, timeout, base)
    return _payload(response, path)


def _payload(response: Any, path: str) -> Any:
    """Decode *response*, turning an error status into a TraktHttpError.

    .. raises:: TraktError
    """
    if response.status_code >= 400:
        raise TraktHttpError(response.status_code, _error_message(response, path))

    try:
        return response.json()
    except ValueError as e:
        raise TraktError(
            f"Trakt did not answer with JSON (HTTP {response.status_code})."
        ) from e


def _error_detail(response: Any) -> str:
    """The message Trakt put in an error body, or the start of the body itself."""
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return " ".join(message.split())

    # a reverse proxy in front of Trakt answers with a page, not a body
    return " ".join(str(response.text or "").split())[:200]


def _error_message(response: Any, path: str) -> str:
    """A sentence about what Trakt refused and why."""
    status = response.status_code
    detail = _error_detail(response)

    message = f"Trakt answered HTTP {status} on /{path.lstrip('/')}"
    if detail:
        message += f": {detail}"
    if status in (401, 403):
        message += ". Check the API key and secret in the plugin settings."
    return message


# the API, endpoint by endpoint ---------------------------------------------------------------


def fetch_search(
    api_key: str, access_token: str, query: str, limit: int = SEARCH_LIMIT
) -> List[Dict]:
    """Search trakt.tv for movies and shows matching *query*.

    The search endpoint is public, so this works with the API key alone; the
    access token is only carried for the sake of Trakt's rate accounting and
    never required.

    .. raises:: TraktError
    """
    payload = call(
        "GET",
        "search/movie,show",
        api_key,
        access_token=access_token,
        params={"query": query, "limit": limit},
    )
    if not isinstance(payload, list):
        raise TraktError("Trakt answered the search with something unexpected.")
    return [
        hit for hit in payload if isinstance(hit, dict) and hit_media_type(hit) in MEDIA_LABELS
    ]


def rating_body(media_type: str, trakt_id: int, rating: Union[int, float]) -> Dict[str, Any]:
    """The POST /sync/ratings body that rates one movie or show.

    >>> rating_body("movie", 550, 8)
    {'movies': [{'ids': {'trakt': 550}, 'rating': 8}]}
    >>> rating_body("show", 1396, 8.5)
    {'shows': [{'ids': {'trakt': 1396}, 'rating': 8.5}]}

    .. raises:: TraktError
    """
    if media_type not in MEDIA_PLURALS:
        raise TraktError(f"Not a media type Trakt rates: {media_type!r}.")
    return {MEDIA_PLURALS[media_type]: [{"ids": {"trakt": trakt_id}, "rating": rating}]}


def submit_rating(
    api_key: str,
    access_token: str,
    media_type: str,
    trakt_id: int,
    rating: Union[int, float],
) -> Dict:
    """Rate one movie or show, returning what Trakt made of it.

    A rating the sync endpoint cannot place - a wrong id, a title that has since
    vanished - comes back HTTP 201 with the miss listed under `not_found`, so
    that is read as a failure here rather than as a success.

    .. raises:: TraktError
    """
    payload = call(
        "POST",
        "sync/ratings",
        api_key,
        access_token=access_token,
        body=rating_body(media_type, trakt_id, rating),
    )
    if not isinstance(payload, dict):
        raise TraktError("Trakt did not answer the rating.")

    not_found = payload.get("not_found")
    if isinstance(not_found, dict):
        for plural, label in (("movies", "movie"), ("shows", "show")):
            missing = not_found.get(plural)
            if isinstance(missing, list) and missing:
                raise TraktError(f"Trakt does not know this {label}.")
    return payload


def request_device_code(api_key: str) -> Dict:
    """Start a device-code sign-in, asking Trakt for a code to enter.

    The code and the page to enter it on are what the user needs; the
    device_code that goes back into the poll never leaves this plugin.

    .. raises:: TraktError
    """
    payload = call(
        "POST", "oauth/device/code", api_key, body={"client_id": api_key}, base=AUTH_BASE
    )
    if not isinstance(payload, dict) or not payload.get("device_code"):
        raise TraktError("Trakt did not hand back a device code.")
    return payload


def poll_device_token(
    api_key: str, api_secret: str, device_code: str
) -> Tuple[str, Optional[Dict]]:
    """One poll of the device-token endpoint.

    Trakt answers a poll that is too early with a bare status code rather than
    a body: 400 means keep waiting, 429 means wait longer than you were. Both
    are states, not failures; everything else that is not a 200 ends the
    sign-in, each with its own reason.

    Returns ("granted", payload), ("pending", None) or ("slow_down", None).

    .. raises:: TraktError
    """
    response = _request(
        "POST",
        "oauth/device/token",
        api_key,
        body={"code": device_code, "client_id": api_key, "client_secret": api_secret},
        base=AUTH_BASE,
    )

    status = response.status_code
    if status == 200:
        try:
            payload = response.json()
        except ValueError as e:
            raise TraktError("Trakt did not answer with JSON.") from e
        if not isinstance(payload, dict) or not payload.get("access_token"):
            raise TraktError("Trakt did not hand back an access token.")
        return "granted", payload
    if status == 400:
        return "pending", None
    if status == 429:
        return "slow_down", None
    if status in DEVICE_FAILURES:
        raise TraktError(DEVICE_FAILURES[status])
    raise TraktHttpError(status, _error_message(response, "oauth/device/token"))


def await_device_token(
    api_key: str,
    api_secret: str,
    device: Dict,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> Dict:
    """Poll Trakt until the code is approved on trakt.tv, or give up.

    *device* is what request_device_code handed back. The wait between polls is
    what Trakt asked for, plus the five extra seconds every 429 says to take,
    capped so that a long slow-down cannot stall the sign-in for good.

    .. raises:: TraktError
    """
    code = str(device.get("device_code") or "")
    if not code:
        raise TraktError("Trakt did not hand back a device code.")

    interval = max(int(device.get("interval") or 5), 1)
    deadline = now() + max(int(device.get("expires_in") or 600), interval)

    while now() < deadline:
        sleep(interval)
        state, payload = poll_device_token(api_key, api_secret, code)
        if state == "granted":
            if payload is None:
                raise TraktError("Trakt did not hand back an access token.")
            return payload
        if state == "slow_down":
            interval = min(interval + POLL_SLOW_DOWN, POLL_INTERVAL_MAX)

    raise TraktError("The device code expired before it was approved on trakt.tv.")


def refresh_tokens(api_key: str, api_secret: str, refresh_token: str) -> Dict:
    """Exchange a refresh token for a new session.

    A refresh token is single-use: Trakt hands back a new one alongside the new
    access token, and the old pair stops working the moment it is spent. That is
    why only one refresh may ever be in flight at a time, and why a failure here
    leaves the plugin signed out rather than retrying.

    .. raises:: TraktError
    """
    payload = call(
        "POST",
        "oauth/token",
        api_key,
        body={
            "refresh_token": refresh_token,
            "client_id": api_key,
            "client_secret": api_secret,
            "grant_type": "refresh_token",
        },
        base=AUTH_BASE,
    )
    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise TraktError("Trakt did not hand back an access token.")
    return payload


def fetch_username(api_key: str, access_token: str) -> str:
    """The Trakt username of whoever signed in, "" when it cannot be read.

    .. raises:: TraktError
    """
    payload = call("GET", "users/settings", api_key, access_token=access_token)
    user = payload.get("user") if isinstance(payload, dict) else None
    username = user.get("username") if isinstance(user, dict) else None
    return str(username or "")


# reading the payloads ------------------------------------------------------------------------


def hit_media_type(hit: Dict) -> str:
    """'movie' or 'show' for a hit the plugin can act on, "" otherwise.

    >>> hit_media_type({"type": "movie", "movie": {}})
    'movie'
    >>> hit_media_type({"type": "person", "person": {}})
    ''
    >>> hit_media_type({})
    ''
    """
    media_type = hit.get("type")
    return media_type if media_type in MEDIA_LABELS else ""


def hit_object(hit: Dict) -> Dict:
    """The movie or show a search hit is about, {} when the payload is odd."""
    media = hit.get(hit_media_type(hit))
    return media if isinstance(media, dict) else {}


def hit_title(hit: Dict) -> str:
    """The title of a search hit, "" when the payload has none."""
    return str(hit_object(hit).get("title") or "")


def hit_year(hit: Dict) -> str:
    """Just the year of a search hit, "" when there is none.

    Trakt sends it as a number; an older or hand-edited payload may spell it
    out, so either is read the same way.
    """
    year = hit_object(hit).get("year")
    if isinstance(year, bool):
        return ""
    if isinstance(year, int):
        return str(year)
    if isinstance(year, str) and year.isdigit():
        return year
    return ""


def hit_ids(hit: Dict) -> Dict:
    """The ids a search hit carries, {} when there are none."""
    ids = hit_object(hit).get("ids")
    return ids if isinstance(ids, dict) else {}


def hit_trakt_id(hit: Dict) -> Optional[int]:
    """The Trakt id of a search hit, None when the payload has none."""
    trakt_id = hit_ids(hit).get("trakt")
    if isinstance(trakt_id, bool) or not isinstance(trakt_id, int):
        return None
    return trakt_id


def hit_slug(hit: Dict) -> str:
    """The slug a search hit's page is named after, "" when there is none."""
    slug = hit_ids(hit).get("slug")
    return str(slug) if isinstance(slug, str) and slug else ""


def hit_subtext(hit: Dict) -> str:
    """One line describing a search hit: its kind and its year.

    >>> hit_subtext({"type": "movie", "movie": {"title": "Fight Club", "year": 1999}})
    'Movie | 1999'
    """
    parts = [MEDIA_LABELS.get(hit_media_type(hit), "Media")]
    year = hit_year(hit)
    if year:
        parts.append(year)
    return " | ".join(parts)


def item_url(hit: Dict) -> str:
    """The trakt.tv page of a search hit.

    The slug is what the site names its own pages after, so it is preferred; a
    hit whose ids carry no slug is opened through the search-by-id page, which
    redirects to the same place. Anything the payload cannot describe links to
    the site's front page rather than to a page that would not exist.

    >>> item_url({"type": "movie", "movie": {"ids": {"trakt": 550, "slug": "fight-club"}}})
    'https://trakt.tv/movies/fight-club'
    >>> item_url({"type": "show", "show": {"ids": {"trakt": 1396}}})
    'https://trakt.tv/search/trakt/1396?type=show'
    >>> item_url({"type": "person"})
    'https://trakt.tv'
    """
    media_type = hit_media_type(hit)
    if not media_type:
        return TRAKT_HOME

    slug = hit_slug(hit)
    if slug:
        return f"{TRAKT_HOME}/{MEDIA_PLURALS[media_type]}/{slug}"

    trakt_id = hit_trakt_id(hit)
    if trakt_id is not None:
        return f"{TRAKT_HOME}/search/trakt/{trakt_id}?type={media_type}"
    return TRAKT_HOME


def parse_rating(word: str) -> Optional[Union[int, float]]:
    """The rating *word* names, or None when it is not one.

    Trakt rates in whole and half stars, 1 to 10.

    >>> parse_rating("8")
    8
    >>> parse_rating("8.5")
    8.5
    >>> parse_rating("0") is None
    True
    >>> parse_rating("11") is None
    True
    >>> parse_rating("x") is None
    True
    """
    try:
        rating = float(word)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(rating):
        return None
    if abs(rating * 2 - round(rating * 2)) > 1e-9:
        return None
    if not (RATING_MIN <= rating <= RATING_MAX):
        return None
    return int(rating) if rating == int(rating) else rating


class ParsedQuery(NamedTuple):
    """What a typed query is asking the plugin to do.

    `mode` is one of "status" (the empty query), "search", "rate" or "error";
    `rating` is only set in rate mode, and `message` only in error mode.
    """

    mode: str
    rating: Optional[Union[int, float]]
    term: str
    message: str


def parse_query(text: str) -> ParsedQuery:
    """What the typed *text* is asking for.

    A leading `rate` word is always read as the rating grammar, even when what
    follows it could have been a title: "rate my trainer" is a mistyped rating,
    not a search, because a title that starts with a rating is far rarer than a
    mistyped one.

    >>> parse_query("").mode
    'status'
    >>> parse_query("fight club").term
    'fight club'
    >>> query = parse_query("rate 8 fight club")
    >>> query.mode, query.rating, query.term
    ('rate', 8, 'fight club')
    >>> parse_query("Rate 8 fight club").rating
    8
    >>> parse_query("rate").mode
    'error'
    >>> parse_query("rate 8").mode
    'error'
    >>> parse_query("rate 11 fight").mode
    'error'
    >>> parse_query("rate x fight").mode
    'error'
    """
    words = text.split()
    if not words:
        return ParsedQuery("status", None, "", "")

    if words[0].lower() == "rate":
        if len(words) < 3:
            return ParsedQuery("error", None, "", "Rate with: rate <1-10> <title>")
        rating = parse_rating(words[1])
        if rating is None:
            return ParsedQuery(
                "error", None, "", f"Not a rating Trakt knows: {words[1]!r}. Use 1-10."
            )
        return ParsedQuery("rate", rating, " ".join(words[2:]), "")

    return ParsedQuery("search", None, " ".join(words), "")


# main plugin class ---------------------------------------------------------------------------


class Plugin(PluginInstance, GeneratorQueryHandler):
    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)

        # readConfig is untyped in the stub and hands back whatever was stored,
        # so a value edited by hand can be anything
        self._api_key: str = str(self.readConfig(CONFIG_API_KEY, str) or "").strip()
        self._api_secret: str = str(self.readConfig(CONFIG_API_SECRET, str) or "").strip()
        self._access_token: str = str(self.readConfig(CONFIG_ACCESS_TOKEN, str) or "").strip()
        self._refresh_token: str = str(
            self.readConfig(CONFIG_REFRESH_TOKEN, str) or ""
        ).strip()
        self._username: str = str(self.readConfig(CONFIG_USERNAME, str) or "").strip()

        # Guards the session and the caches below. The tokens are under the lock
        # as well because a refresh token is single-use: two 401s arriving at
        # once must not both spend it.
        self._lock = threading.Lock()
        self._searches: Dict[str, Tuple[float, List[Dict]]] = {}
        # Bumped on every token change. A refresh that finds the generation
        # moved on found somebody else's already done the work, and must not
        # spend the old token a second time.
        self._generation = 0
        self._signing_in = False
        # The device code awaiting approval on trakt.tv, and when it stops being
        # worth showing.
        self._pending: Optional[Dict] = None
        self._pending_deadline = 0.0

    # -- config, bound to the settings widget below ---------------------------------------

    @property
    def api_key(self) -> str:
        return self._api_key

    @api_key.setter
    def api_key(self, value: str):
        self._api_key = (value or "").strip()
        self.writeConfig(CONFIG_API_KEY, self._api_key)
        self._forget()

    @property
    def api_secret(self) -> str:
        return self._api_secret

    @api_secret.setter
    def api_secret(self, value: str):
        self._api_secret = (value or "").strip()
        self.writeConfig(CONFIG_API_SECRET, self._api_secret)
        self._forget()

    def configWidget(self):
        return [
            {
                "type": "label",
                "text": (
                    "Create an application on trakt.tv to get a Client ID and a Client "
                    "Secret, paste them below, then clear the query and press [ENTER] on "
                    "'Sign in to Trakt' to finish on the website. Searching works with "
                    "the Client ID alone; signing in and rating need both."
                ),
            },
            {
                "type": "lineedit",
                "property": "api_key",
                "label": "Client ID (API key)",
                "widget_properties": {
                    "echoMode": 2,
                    "placeholderText": "the Client ID of your Trakt application",
                },
            },
            {
                "type": "lineedit",
                "property": "api_secret",
                "label": "Client Secret",
                "widget_properties": {
                    "echoMode": 2,
                    "placeholderText": "the Client Secret of your Trakt application",
                },
            },
            {
                "type": "label",
                "text": (
                    "Everything you paste here, including the access and refresh tokens "
                    "a sign-in stores, is kept by Albert in plaintext. The plugin only "
                    "ever talks to api.trakt.tv and auth.trakt.tv; it searches, opens "
                    "titles on trakt.tv and rates them - nothing else."
                ),
            },
        ]

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "trakt "

    def synopsis(self, query):
        return "a title, or rate <1-10> <title>, or nothing for the sign-in status"

    # -- the session ----------------------------------------------------------------------

    def _has_session(self) -> bool:
        return bool(self._access_token)

    def _has_credentials(self) -> bool:
        return bool(self._api_key and self._api_secret)

    def _store_session_locked(self, payload: Dict) -> None:
        """Remember a granted session. Caller must hold the lock."""
        access = str(payload.get("access_token") or "")
        refresh = str(payload.get("refresh_token") or "")
        self._access_token = access
        if refresh:
            self._refresh_token = refresh
        self._generation += 1
        self.writeConfig(CONFIG_ACCESS_TOKEN, access)
        if refresh:
            self.writeConfig(CONFIG_REFRESH_TOKEN, refresh)

    def _clear_session_locked(self) -> None:
        """Forget the session entirely. Caller must hold the lock."""
        self._access_token = ""
        self._refresh_token = ""
        self._username = ""
        self._generation += 1
        self.writeConfig(CONFIG_ACCESS_TOKEN, "")
        self.writeConfig(CONFIG_REFRESH_TOKEN, "")
        self.writeConfig(CONFIG_USERNAME, "")

    def _refresh_session(self) -> None:
        """Exchange the refresh token for a new session.

        Under the lock for the whole exchange: the refresh token is single-use,
        so two callers taking their turn must not both spend it. The generation
        check is what makes the second one reuse the session the first one
        fetched instead of refreshing again - and finding nothing left to
        refresh with, failing the whole idea.

        .. raises:: TraktError
        """
        with self._lock:
            refresh = self._refresh_token
            generation = self._generation
            if not refresh:
                raise TraktError("Signed out. Sign in to Trakt again to rate titles.")

            try:
                payload = refresh_tokens(self._api_key, self._api_secret, refresh)
            except TraktError:
                self._clear_session_locked()
                raise

            if self._generation != generation:
                return

            access = str(payload.get("access_token") or "")
            if not access:
                self._clear_session_locked()
                raise TraktError("Trakt did not hand back an access token.")

            self._access_token = access
            new_refresh = str(payload.get("refresh_token") or "")
            if new_refresh:
                self._refresh_token = new_refresh
            self._generation += 1
            self.writeConfig(CONFIG_ACCESS_TOKEN, access)
            if new_refresh:
                self.writeConfig(CONFIG_REFRESH_TOKEN, new_refresh)

    def _sign_out(self) -> None:
        with self._lock:
            self._clear_session_locked()
        notify("Signed out of Trakt.")

    # -- caches ---------------------------------------------------------------------------

    def _forget(self) -> None:
        """Drop every cached answer, so the next query asks Trakt again."""
        with self._lock:
            self._searches = {}

    def _search(self, term: str) -> List[Dict]:
        """The search hits for *term*, refetched at most every SEARCH_TTL seconds.

        .. raises:: TraktError
        """
        with self._lock:
            cached = self._searches.get(term)
        if cached is not None and time.monotonic() - cached[0] < SEARCH_TTL:
            return cached[1]

        results = fetch_search(self._api_key, "", term)

        with self._lock:
            self._searches[term] = (time.monotonic(), results)
            # only the most recent terms are kept: that makes backspacing over a
            # word free without letting the dict grow for the whole session
            while len(self._searches) > SEARCH_CACHE_SIZE:
                oldest = min(self._searches, key=lambda key: self._searches[key][0])
                del self._searches[oldest]

        return results

    @staticmethod
    def _wait_for_still_input(ctx, delay: float = SEARCH_DEBOUNCE) -> bool:
        """Wait for the typing to stop, or False when the query was replaced.

        Albert runs a fresh query per keystroke and cancels the one before it, so
        this is a debounce with no timer of the plugin's own: a term that is
        still being typed is gone within the delay and never reaches Trakt.
        """
        deadline = time.monotonic() + delay
        while ctx.isValid and time.monotonic() < deadline:
            time.sleep(0.02)
        return bool(ctx.isValid)

    # -- items ----------------------------------------------------------------------------

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        try:
            setup = self._setup_item()
            if setup is not None:
                yield [setup]
                return

            parsed = parse_query(ctx.query.strip())

            if parsed.mode == "status":
                yield self._status_items()
                return

            if parsed.mode == "error":
                yield [self._usage_item(parsed.message)]
                return

            if parsed.mode == "rate" and not self._has_session():
                yield [self._need_sign_in_item()]
                return

            if len(parsed.term) < MIN_SEARCH_CHARS:
                yield [self._short_query_item(parsed.term)]
                return

            if not self._wait_for_still_input(ctx):
                return

            results = self._search(parsed.term)
            if not ctx.isValid:
                return

            if parsed.mode == "rate":
                if parsed.rating is None:  # cannot happen: parse_query sets it in rate mode
                    yield [self._usage_item("Rate with: rate <1-10> <title>")]
                    return
                yield self._rate_items(parsed.rating, results)
            else:
                yield self._search_items(parsed.term, results)

        except TraktError as e:
            debug(traceback.format_exc())
            yield [self._error_item(str(e))]
        except Exception:  # user to report error
            trace = traceback.format_exc()
            critical(trace)

            yield [
                StandardItem(
                    id=f"{self.id()}.crash",
                    icon_factory=self.makeIcon,
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    input_action_text="",
                    actions=[
                        Action(
                            "copy",
                            f"Copy error - report it to {md_url[8:]}",
                            lambda t=trace: setClipboardText(t),
                        )
                    ],
                )
            ]

    def _setup_item(self) -> Optional[StandardItem]:
        """The one item to show while the plugin cannot do anything at all."""
        if not self._api_key:
            return StandardItem(
                id=f"{self.id()}.setup-key",
                icon_factory=self.makeIcon,
                text="Please fill in the plugin settings - Trakt API key missing",
                subtext=(
                    "Create an application on trakt.tv and paste its Client ID in the "
                    "plugin settings."
                ),
                input_action_text="",
                actions=[
                    Action(
                        "open", "Open the Trakt application page", lambda: openUrl(APP_URL)
                    )
                ],
            )
        return None

    def _status_items(self) -> List[StandardItem]:
        """What the empty query shows: a pending sign-in, or where things stand."""
        items: List[StandardItem] = []

        pending = self._pending_item()
        if pending is not None:
            items.append(pending)

        if self._has_session():
            username = self._username
            profile = f"{TRAKT_HOME}/users/{username}" if username else TRAKT_HOME
            signed_in = "Signed in to Trakt"
            if username:
                signed_in += f" as {username}"
            items.append(
                StandardItem(
                    id=f"{self.id()}.signed-in",
                    icon_factory=self.makeIcon,
                    text=signed_in,
                    subtext="Type a title to open it, or rate <1-10> <title> to rate one.",
                    input_action_text="",
                    actions=[
                        Action("open", "Open your Trakt profile", lambda: openUrl(profile)),
                        Action("signout", "Sign out of Trakt", self._sign_out),
                    ],
                )
            )
        elif self._has_credentials():
            items.append(
                StandardItem(
                    id=f"{self.id()}.sign-in",
                    icon_factory=self.makeIcon,
                    text="Sign in to Trakt",
                    subtext=(
                        "Press [ENTER] to start a device-code sign-in; the code is "
                        "entered once on trakt.tv."
                    ),
                    input_action_text="",
                    actions=[
                        Action(
                            "signin", "Start a device-code sign-in", self._start_sign_in
                        )
                    ],
                )
            )
        else:
            items.append(self._secret_item())

        return items

    def _secret_item(self) -> StandardItem:
        """The one item to show while searching works but rating cannot."""
        return StandardItem(
            id=f"{self.id()}.setup-secret",
            icon_factory=self.makeIcon,
            text="Add the Trakt API secret to sign in and rate titles",
            subtext=(
                "Searching titles works without it. The secret is the Client Secret "
                "of your Trakt application, next to the Client ID."
            ),
            input_action_text="",
            actions=[
                Action("open", "Open the Trakt application page", lambda: openUrl(APP_URL))
            ],
        )

    def _need_sign_in_item(self) -> StandardItem:
        return StandardItem(
            id=f"{self.id()}.need-sign-in",
            icon_factory=self.makeIcon,
            text="Sign in to Trakt to rate titles",
            subtext=(
                "Clear the query and press [ENTER] on 'Sign in to Trakt', or type "
                "just a title to open it in the browser."
            ),
            input_action_text="",
            actions=[
                Action("signin", "Start a device-code sign-in", self._start_sign_in),
                Action("open", "Open trakt.tv", lambda: openUrl(TRAKT_HOME)),
            ],
        )

    def _pending_item(self) -> Optional[StandardItem]:
        """The sign-in-in-progress row, while its code is still worth entering."""
        with self._lock:
            device = self._pending
            deadline = self._pending_deadline
        if not device or time.monotonic() > deadline:
            return None

        code = str(device.get("user_code") or "")
        url = str(device.get("verification_url") or ACTIVATE_URL)
        return StandardItem(
            id=f"{self.id()}.pending",
            icon_factory=self.makeIcon,
            text=f"Waiting for sign-in: open {url} and enter {code}",
            subtext="Approve the code on trakt.tv, or press [ENTER] to open the page.",
            input_action_text="",
            actions=[
                Action("open", "Open trakt.tv/activate", lambda: openUrl(url)),
                Action("copy", "Copy the code", lambda c=code: setClipboardText(c)),
            ],
        )

    def _search_items(self, term: str, results: Sequence[Dict]) -> List[StandardItem]:
        if not results:
            return [self._no_match_item(term)]
        return [self._result_item(hit) for hit in results[:SEARCH_LIMIT]]

    def _result_item(self, hit: Dict) -> StandardItem:
        """One search hit. ENTER opens its page on trakt.tv."""
        media_type = hit_media_type(hit)
        title = hit_title(hit) or MEDIA_LABELS.get(media_type, "Title")
        page = item_url(hit)

        return StandardItem(
            id=f"{self.id()}.result-{media_type}-{hit_trakt_id(hit)}",
            icon_factory=self.makeIcon,
            text=title,
            subtext=hit_subtext(hit),
            input_action_text=f"{self.defaultTrigger()}{title}",
            actions=[Action("open", "Open in browser", lambda url=page: openUrl(url))],
        )

    def _rate_items(
        self, rating: Union[int, float], results: Sequence[Dict]
    ) -> List[StandardItem]:
        if not results:
            return [self._no_match_item(f"rate {rating}")]
        return [self._rate_item(hit, rating) for hit in results[:SEARCH_LIMIT]]

    def _rate_item(self, hit: Dict, rating: Union[int, float]) -> StandardItem:
        """One search hit, in a rate query. ENTER rates it on Trakt."""
        media_type = hit_media_type(hit)
        title = hit_title(hit) or MEDIA_LABELS.get(media_type, "Title")
        page = item_url(hit)
        trakt_id = hit_trakt_id(hit)

        return StandardItem(
            id=f"{self.id()}.rate-{media_type}-{trakt_id}",
            icon_factory=self.makeIcon,
            text=title,
            subtext=f"{hit_subtext(hit)} | rate {rating}/10",
            input_action_text=f"{self.defaultTrigger()}rate {rating} {title}",
            actions=[
                Action(
                    "rate",
                    f"Rate {title} {rating}/10",
                    lambda m=media_type, i=trakt_id, r=rating, t=title: self._rate(m, i, r, t),
                ),
                Action("open", "Open in browser", lambda url=page: openUrl(url)),
            ],
        )

    def _short_query_item(self, term: str) -> StandardItem:
        return StandardItem(
            id=f"{self.id()}.short-query",
            icon_factory=self.makeIcon,
            text=f"Search Trakt for {term}",
            subtext=(
                f"Trakt is searched from {MIN_SEARCH_CHARS} characters - clear the "
                "query for the sign-in status"
            ),
            input_action_text="",
            actions=[Action("open", "Open trakt.tv", lambda: openUrl(TRAKT_HOME))],
        )

    def _no_match_item(self, term: str) -> StandardItem:
        return StandardItem(
            id=f"{self.id()}.no-match",
            icon_factory=self.makeIcon,
            text=f'Nothing on Trakt matches "{term}"',
            subtext="Try fewer words, or the title in its original language",
            input_action_text="",
            actions=[
                Action("open", "Open trakt.tv", lambda: openUrl(TRAKT_HOME)),
                Action("reload", "Search again", self._forget),
            ],
        )

    def _usage_item(self, message: str) -> StandardItem:
        return StandardItem(
            id=f"{self.id()}.usage",
            icon_factory=self.makeIcon,
            text=message,
            subtext="Rate with: rate <1-10> <title>, or just type a title to open it.",
            input_action_text="",
            actions=[Action("open", "Open trakt.tv", lambda: openUrl(TRAKT_HOME))],
        )

    def _error_item(self, message: str) -> StandardItem:
        return StandardItem(
            id=f"{self.id()}.error",
            icon_factory=self.makeIcon,
            text=message,
            subtext="Press [ENTER] to retry.",
            input_action_text="",
            actions=[
                Action("retry", "Retry", self._forget),
                Action("copy", "Copy error", lambda m=message: setClipboardText(m)),
            ],
        )

    # -- signing in -----------------------------------------------------------------------

    def _start_sign_in(self) -> None:
        """Kick off a device-code sign-in in the background."""
        if not self._has_credentials():
            notify("Add the Trakt API key and secret in the plugin settings first.")
            return

        with self._lock:
            if self._signing_in:
                return
            self._signing_in = True
        threading.Thread(target=self._sign_in, name="trakt-sign-in", daemon=True).start()

    def _sign_in(self) -> None:
        """The device-code sign-in, from the first request to the stored tokens.

        Runs on a thread of its own: it waits for a human to open trakt.tv and
        type a code, which takes as long as it takes.
        """
        try:
            device = request_device_code(self._api_key)
            with self._lock:
                self._pending = device
                self._pending_deadline = time.monotonic() + max(
                    int(device.get("expires_in") or 600), 1
                )

            code = str(device.get("user_code") or "")
            url = str(device.get("verification_url") or ACTIVATE_URL)
            notify(f"Sign in to Trakt: open {url} and enter {code}")

            payload = await_device_token(self._api_key, self._api_secret, device)
            username = fetch_username(self._api_key, str(payload.get("access_token") or ""))

            with self._lock:
                self._store_session_locked(payload)
                self._username = username
                self._pending = None
                self._pending_deadline = 0.0
            if username:
                self.writeConfig(CONFIG_USERNAME, username)
            notify(f"Signed in to Trakt as {username}" if username else "Signed in to Trakt")

        except TraktError as e:
            debug(traceback.format_exc())
            notify(str(e))
        except Exception:
            trace = traceback.format_exc()
            critical(trace)
            notify(trace.strip().splitlines()[-1] if trace.strip() else "unknown error")
        finally:
            with self._lock:
                self._pending = None
                self._pending_deadline = 0.0
                self._signing_in = False

    # -- the actions ----------------------------------------------------------------------

    def _rate(
        self, media_type: str, trakt_id: int, rating: Union[int, float], title: str
    ) -> None:
        self._async(
            lambda: self._submit_rating(media_type, trakt_id, rating),
            f"Rated {title} {rating}/10",
        )

    def _submit_rating(self, media_type: str, trakt_id: int, rating: Union[int, float]) -> Any:
        """Rate one title, refreshing an expired session once and trying again.

        .. raises:: TraktError
        """
        try:
            return submit_rating(
                self._api_key, self._access_token, media_type, trakt_id, rating
            )
        except TraktHttpError as e:
            if e.status != 401 or not self._refresh_token:
                raise
        self._refresh_session()
        return submit_rating(
            self._api_key, self._access_token, media_type, trakt_id, rating
        )

    def _async(self, work: Callable[[], Any], note: str) -> None:
        """Run *work* off the UI thread and report what came of it."""
        threading.Thread(
            target=self._mutate, args=(work, note), name="trakt-action", daemon=True
        ).start()

    @staticmethod
    def _mutate(work: Callable[[], Any], note: str) -> None:
        try:
            work()
        except TraktError as e:
            debug(traceback.format_exc())
            notify(str(e))
        except Exception:
            trace = traceback.format_exc()
            critical(trace)
            notify(trace.strip().splitlines()[-1] if trace.strip() else "unknown error")
        else:
            notify(note)
