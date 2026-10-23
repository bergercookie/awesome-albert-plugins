"""Jellyseerr - review and create media requests without leaving Albert.

The empty query lists the recent requests, pending ones first, so that ENTER on
one approves it. Anything typed instead is searched for on Jellyseerr's own
catalogue, and ENTER on a hit requests it.

Everything goes through Jellyseerr's REST API with the plugin's API key, and
nothing but that one server is ever contacted.
"""

import subprocess
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple
from urllib.parse import quote, urlencode, urljoin, urlparse

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
md_name = "Jellyseerr"
md_description = "Review Jellyseerr requests and request new movies and series"
md_license = "MIT"
md_url = (
    "https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/jellyseerr"
)
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["requests"]
md_bin_dependencies: List[str] = []

ICON_DIR = Path(__file__).parent
ICON_PATH = ICON_DIR / "jellyseerr.svg"

CONFIG_URL = "jellyseerr_url"
CONFIG_API_TOKEN = "jellyseerr_api_token"
CONFIG_API_TOKEN_COMMAND = "jellyseerr_api_token_command"

# Where to read about the project when the plugin is not set up yet. The link is
# written the way the project was named for its whole life; GitHub redirects it
# to wherever it lives now.
JELLYSEERR_URL = "https://github.com/Fallenbagel/jellyseerr"

# Jellyseerr runs on a home server, so a request slower than this is a server
# that is down, not one that is busy.
HTTP_TIMEOUT = 10
# How long a command that prints the API key may take. A password manager that
# has to be unlocked can be slow, but not this slow.
KEY_COMMAND_TIMEOUT = 30
# How many requests the empty query shows. Jellyseerr's own default is 10.
REQUEST_TAKE = 20
# How many hits of a search are turned into items.
SEARCH_LIMIT = 20
# Jellyseerr's search is a TMDB lookup on its side, and a single character
# matches most of the catalogue, so it is not worth a round trip.
MIN_SEARCH_CHARS = 2
# A query is only searched once it stops moving. Albert cancels the previous
# query on every keystroke, so waiting here costs nothing while typing and turns
# a typed word into one search instead of one per letter.
SEARCH_DEBOUNCE = 0.15
# How long an answer is reused before Jellyseerr is asked again.
REQUESTS_TTL = 30.0
SEARCH_TTL = 60.0
# A request payload carries no title, so every row of a list costs a lookup of
# its own. A handful at a time keeps the first query of a session quick.
TITLE_WORKERS = 8
# Searched terms remembered, which is what makes backspacing over a word free
# instead of one request per deleted letter.
SEARCH_CACHE_SIZE = 8
USER_AGENT = "awesome-albert-plugins/jellyseerr"

# MediaRequestStatus, as of Jellyseerr v1.9.2 server/constants/media.ts.
STATUS_PENDING = 1
STATUS_APPROVED = 2
STATUS_DECLINED = 3
STATUS_FAILED = 4

# MediaStatus, same file.
MEDIA_UNKNOWN = 1
MEDIA_PENDING = 2
MEDIA_PROCESSING = 3
MEDIA_PARTIAL = 4
MEDIA_AVAILABLE = 5

REQUEST_STATUS_LABELS = {
    STATUS_PENDING: "Pending",
    STATUS_APPROVED: "Approved",
    STATUS_DECLINED: "Declined",
    STATUS_FAILED: "Failed",
}

MEDIA_STATUS_LABELS = {
    MEDIA_UNKNOWN: "Not requested",
    MEDIA_PENDING: "Pending approval",
    MEDIA_PROCESSING: "Processing",
    MEDIA_PARTIAL: "Partially available",
    MEDIA_AVAILABLE: "Already available",
}

# The two kinds of media Jellyseerr can request, and what to call them.
MEDIA_LABELS = {"movie": "Movie", "tv": "Series"}

# The words Jellyseerr spells its status routes with:
# POST /api/v1/request/{id}/{status}. Note this is not the vocabulary of the
# `filter` parameter on the request list, which has no value for a declined one.
REQUEST_ROUTES = ("pending", "approve", "decline")


# plugin main functions -----------------------------------------------------------------------


class JellyseerrError(Exception):
    """A failure worth showing to the user as-is."""


def notify(msg: str, app_name: str = md_name) -> None:
    Notification(app_name, msg).send()


# urls ----------------------------------------------------------------------------------------


def join_url(base_url: str, path: str) -> str:
    """Join *path* onto the Jellyseerr base URL.

    The leading slash is dropped on purpose: a Jellyseerr behind a reverse proxy
    keeps its prefix on the API routes as well as on the web UI routes, and a
    leading slash would climb back out of that prefix.

    >>> join_url("http://localhost:5055", "api/v1/request")
    'http://localhost:5055/api/v1/request'
    >>> join_url("http://localhost:5055/", "/api/v1/request")
    'http://localhost:5055/api/v1/request'
    >>> join_url("https://media.example.com/jellyseerr", "movie/42")
    'https://media.example.com/jellyseerr/movie/42'
    """
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def home_url(base_url: str) -> str:
    """The Jellyseerr web UI root.

    >>> home_url("http://localhost:5055/")
    'http://localhost:5055'
    """
    return base_url.rstrip("/")


def requests_url(base_url: str) -> str:
    """The request queue in the Jellyseerr web UI.

    >>> requests_url("http://localhost:5055")
    'http://localhost:5055/requests'
    """
    return join_url(base_url, "requests")


def media_url(base_url: str, media_type: str, tmdb_id: Any) -> str:
    """Deep link to a title's page in the Jellyseerr web UI.

    Jellyseerr's frontend has a route per media type and takes the TMDB id, e.g.
    /movie/27205 and /tv/1396. Anything else - a person, a collection, a payload
    whose ids did not survive - links to the web UI root instead of to a page
    that would not exist.

    >>> media_url("http://localhost:5055", "movie", 27205)
    'http://localhost:5055/movie/27205'
    >>> media_url("http://localhost:5055/", "tv", 1396)
    'http://localhost:5055/tv/1396'
    >>> media_url("http://localhost:5055", "person", 5)
    'http://localhost:5055'
    """
    if media_type in MEDIA_LABELS and tmdb_id is not None:
        return join_url(base_url, f"{media_type}/{tmdb_id}")
    return home_url(base_url)


# the api key ---------------------------------------------------------------------------------


def resolve_api_key(token: str, command: str) -> str:
    """The API key to send, from the plaintext *token* or from *command*.

    A *command* wins over the plaintext key, so the latter can be left out of
    Albert's config entirely. The command is run through the shell and is
    expected to print the key on stdout, e.g. ``pass show jellyseerr`` or
    ``rbw get jellyseerr``; everything around it is ignored. Whatever it prints
    is held in memory only - it is never written back to the config.

    >>> resolve_api_key("  plain  ", "")
    'plain'

    .. raises:: JellyseerrError
    """
    command = (command or "").strip()
    if not command:
        return (token or "").strip()

    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=KEY_COMMAND_TIMEOUT,
        )
    except subprocess.TimeoutExpired as e:
        raise JellyseerrError(
            f'"{command}" took longer than {KEY_COMMAND_TIMEOUT}s to print the API key.'
        ) from e
    except OSError as e:
        raise JellyseerrError(f'Could not run "{command}": {e}') from e

    if proc.returncode != 0:
        detail = " ".join((proc.stderr or "").split())
        message = f'"{command}" failed to print the API key'
        raise JellyseerrError(f"{message}: {detail}" if detail else f"{message}.")

    key = (proc.stdout or "").strip()
    if not key:
        raise JellyseerrError(
            f'"{command}" printed nothing; it must print the API key on stdout.'
        )
    return key


# talking to the server -----------------------------------------------------------------------


def call(
    method: str,
    base_url: str,
    token: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    timeout: float = HTTP_TIMEOUT,
) -> Any:
    """One round trip to Jellyseerr, returning the decoded JSON body.

    Jellyseerr authenticates with an `X-API-Key` header and acts as the
    administrator account the key belongs to, which is why nothing here ever
    sends a user.

    .. raises:: JellyseerrError
    """
    if not base_url:
        raise JellyseerrError(
            "No Jellyseerr URL is configured. Add one in the plugin settings."
        )

    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise JellyseerrError(
            f'"{base_url}" is not a full URL. The plugin setting should look like '
            "http://localhost:5055."
        )

    kwargs: Dict[str, Any] = {
        "headers": {
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "X-API-Key": token,
        },
        "timeout": timeout,
    }
    if body is not None:
        kwargs["json"] = body

    url = join_url(base_url, path)
    if params:
        # requests url-encodes parameters with quote_plus, which turns a space
        # into "+". Jellyseerr's query parser reads the "+" literally and then
        # rejects it as a reserved character, so a multi-word search like
        # "Fight Club" comes back HTTP 400. Encode with quote instead, which
        # writes a space as %20, and hand requests the query pre-built.
        url = f"{url}?{urlencode(params, quote_via=quote)}"

    try:
        response = requests.request(method, url, **kwargs)
    except requests.Timeout as e:
        raise JellyseerrError(
            f"{base_url} did not answer within {timeout:g}s."
        ) from e
    except requests.RequestException as e:
        raise JellyseerrError(f"Cannot reach {base_url}: {e}") from e

    return _payload(response, base_url)


def _payload(response: Any, base_url: str) -> Any:
    """Decode *response*, turning an error status into a JellyseerrError.

    .. raises:: JellyseerrError
    """
    if response.status_code == 204:
        return None

    if response.status_code >= 400:
        raise JellyseerrError(_error_message(response, base_url))

    try:
        return response.json()
    except ValueError as e:
        raise JellyseerrError(
            f"{base_url} did not answer with JSON (HTTP {response.status_code})."
        ) from e


def _error_message(response: Any, base_url: str) -> str:
    """A sentence about what Jellyseerr refused and why.

    Its error handler answers `{"message": ...}`, but the authentication
    middleware answers `{"error": ...}`, and a reverse proxy in front of it may
    answer with a page of HTML. All three end up in the same place here.
    """
    detail = ""
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        for key in ("message", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                detail = " ".join(value.split())
                break

    if not detail:
        detail = " ".join(str(response.text or "").split())[:200]

    message = f"{base_url} answered HTTP {response.status_code}"
    if detail:
        message += f": {detail}"
    if response.status_code in (401, 403):
        message += ". Check the API key in the plugin settings."
    return message


def fetch_requests(base_url: str, token: str, take: int = REQUEST_TAKE) -> List[Dict]:
    """The recent requests, newest first.

    Jellyseerr's own default sort is `request.id DESC`, and `take` is its page
    size, so this asks for the same page its web UI shows at /requests.

    .. raises:: JellyseerrError
    """
    payload = call(
        "GET", base_url, token, "api/v1/request", params={"take": take, "skip": 0}
    )

    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise JellyseerrError(
            f"{base_url} answered the request list with something unexpected."
        )
    return [request for request in results if isinstance(request, dict)]


def fetch_search(base_url: str, token: str, query: str, page: int = 1) -> List[Dict]:
    """Search Jellyseerr's catalogue, which is a TMDB lookup on its side.

    Only the hits that are a movie or a series come back: `person` and
    `collection` results cannot be requested through the API.

    .. raises:: JellyseerrError
    """
    payload = call(
        "GET", base_url, token, "api/v1/search", params={"query": query, "page": page}
    )

    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise JellyseerrError(f"{base_url} answered the search with something unexpected.")
    return [
        result
        for result in results
        if isinstance(result, dict) and result_media_type(result) in MEDIA_LABELS
    ]


def fetch_title(base_url: str, token: str, media_type: str, tmdb_id: Any) -> str:
    """The display name of one movie or series.

    Request and search payloads carry no title at all - Jellyseerr's Media
    entity has no such column - so its own request list fetches one per row.
    This is that lookup.

    .. raises:: JellyseerrError
    """
    payload = call("GET", base_url, token, f"api/v1/{media_type}/{tmdb_id}")
    if not isinstance(payload, dict):
        return ""
    # TMDB calls a movie's name `title` and a series' `name`
    name = payload.get("title") if media_type == "movie" else payload.get("name")
    return str(name or "")


def resolve_titles(
    base_url: str,
    token: str,
    titles: Dict[str, str],
    refs: Iterable[Tuple[str, Any]],
) -> None:
    """Fill *titles* in with the display names it is still missing.

    Concurrently, because it is one round trip per row of the list being built
    and none of them depends on another. A title that cannot be resolved is
    logged and left empty - the item then names its media by type and id, which
    is not worth failing a whole query over.

    .. raises:: JellyseerrError
    """
    missing = [ref for ref in refs if _title_key(*ref) not in titles]
    if not missing:
        return

    def lookup(ref: Tuple[str, Any]) -> str:
        try:
            return fetch_title(base_url, token, ref[0], ref[1])
        except JellyseerrError:
            debug(f"could not resolve the title of {_title_key(*ref)}")
            return ""

    with ThreadPoolExecutor(max_workers=min(TITLE_WORKERS, len(missing))) as pool:
        for ref, name in zip(missing, pool.map(lookup, missing)):
            titles[_title_key(*ref)] = name


def set_request_status(base_url: str, token: str, request_id: Any, status: str) -> Any:
    """Approve, decline or reset one request.

    *status* is Jellyseerr's own word for it, since the route is
    POST /api/v1/request/{id}/{status}.

    .. raises:: JellyseerrError
    """
    if status not in REQUEST_ROUTES:
        raise JellyseerrError(f"Not a request status Jellyseerr knows: {status!r}.")
    return call("POST", base_url, token, f"api/v1/request/{request_id}/{status}")


def create_request(base_url: str, token: str, media_type: str, tmdb_id: Any) -> Any:
    """Ask Jellyseerr for one movie, or for every season of one series.

    The API key belongs to Jellyseerr's own administrator account, so the
    request comes back approved rather than queued for one.

    .. raises:: JellyseerrError
    """
    if media_type not in MEDIA_LABELS:
        raise JellyseerrError(f"Not a media type Jellyseerr knows: {media_type!r}.")

    try:
        media_id = int(tmdb_id)
    except (TypeError, ValueError) as e:
        raise JellyseerrError(f"Cannot request a {media_type} without a TMDB id.") from e

    body: Dict[str, Any] = {"mediaType": media_type, "mediaId": media_id}
    if media_type == "tv":
        # A series 500s without its seasons; 'all' is Jellyseerr's own word for
        # every season TMDB knows about, and it drops the ones already there.
        body["seasons"] = "all"

    payload = call("POST", base_url, token, "api/v1/request", body=body)

    # A created request carries an id. The exception is a 202, which Jellyseerr
    # returns when it accepted the call but there were no seasons left to ask
    # for - that one is only a message, and it still means nothing was created.
    if not (isinstance(payload, dict) and payload.get("id")):
        detail = payload.get("message") if isinstance(payload, dict) else None
        raise JellyseerrError(
            str(detail) if detail else "Jellyseerr did not create the request."
        )

    return payload


# reading the payloads ------------------------------------------------------------------------


def _title_key(media_type: str, tmdb_id: Any) -> str:
    """The key a title is cached under."""
    return f"{media_type}:{tmdb_id}"


def _int(value: Any, default: int = 0) -> int:
    """*value* as an int, or *default* when it is not one.

    Every number read out of a payload goes through here: they are JSON with no
    schema the plugin can rely on, and a hand-written Jellyseerr on the other
    end is the one that decides what is in them.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_timestamp(value: Any) -> Optional[datetime]:
    """The UTC moment an ISO-8601 *value* names, or None if it names none."""
    if not isinstance(value, str) or not value.strip():
        return None

    text = value.strip()
    if text[-1] in ("Z", "z"):
        # fromisoformat only learned to read "Z" in python 3.11
        text = text[:-1] + "+00:00"

    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None

    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def relative_time(value: Any, now: Optional[datetime] = None) -> str:
    """How long ago the ISO-8601 timestamp *value* was, "" if it is not one.

    Jellyseerr sends every timestamp as UTC, which is what makes this a plain
    subtraction rather than a timezone problem.

    >>> mayday = datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc)
    >>> relative_time("2024-05-01T12:00:00.000Z", mayday)
    'just now'
    >>> relative_time("2024-05-01T12:00:00.000Z", mayday.replace(minute=2))
    '2 minutes ago'
    >>> relative_time("2024-05-01T12:00:00.000Z", mayday.replace(hour=13))
    '1 hour ago'
    >>> relative_time("2024-05-01T12:00:00.000Z", mayday.replace(day=3))
    '2 days ago'
    >>> relative_time("2024-05-01T12:00:00.000Z", mayday.replace(month=8, day=9))
    '3 months ago'
    >>> relative_time(None)
    ''
    >>> relative_time("last tuesday")
    ''
    """
    stamp = _parse_timestamp(value)
    if stamp is None:
        return ""

    if now is None:
        now = datetime.now(timezone.utc)

    # a clock that is a little ahead of ours still reads as "now", not as a
    # countdown of negative minutes
    seconds = max(int((now - stamp).total_seconds()), 0)
    if seconds < 60:
        return "just now"

    minutes = seconds // 60
    if minutes < 60:
        return _ago(minutes, "minute")
    hours = minutes // 60
    if hours < 24:
        return _ago(hours, "hour")
    days = hours // 24
    if days < 30:
        return _ago(days, "day")
    months = days // 30
    if months < 12:
        return _ago(months, "month")
    return _ago(round(days / 365), "year")


def _ago(count: int, unit: str) -> str:
    return f"{count} {unit}{'s' if count != 1 else ''} ago"


def sort_requests(requests: List[Dict]) -> List[Dict]:
    """What is worth acting on first.

    The ones waiting for a decision go on top and the rest keep Jellyseerr's own
    newest-first order, so the list is a queue with a tail rather than a log.
    """

    def key(request: Dict) -> Tuple[bool, float, int]:
        created = _parse_timestamp(request.get("createdAt"))
        return (
            request_status(request) != STATUS_PENDING,
            -(created.timestamp() if created else 0.0),
            -_int(request.get("id")),
        )

    return sorted(requests, key=key)


def request_media_type(request: Dict) -> str:
    """'movie' or 'tv', whichever *request* is for, "" when the payload is odd."""
    media = request.get("media")
    if isinstance(media, dict) and media.get("mediaType") in MEDIA_LABELS:
        return str(media["mediaType"])
    media_type = request.get("type")
    return media_type if media_type in MEDIA_LABELS else ""


def request_tmdb_id(request: Dict) -> Any:
    """The TMDB id of the media *request* is for."""
    media = request.get("media")
    return media.get("tmdbId") if isinstance(media, dict) else None


def request_status(request: Dict) -> int:
    """The MediaRequestStatus of *request*."""
    return _int(request.get("status"))


def request_refs(requests: Sequence[Dict]) -> List[Tuple[str, Any]]:
    """The (media type, TMDB id) pairs a list of requests is about."""
    return [(request_media_type(request), request_tmdb_id(request)) for request in requests]


def request_title(request: Dict, titles: Dict[str, str]) -> str:
    """The title of *request*, or the best stand-in for it.

    A request payload names no title, so this is whatever a lookup of it came
    back with; when that lookup failed the media is named by its type and id,
    which is uglier but still says which one to open in the browser.
    """
    media_type = request_media_type(request)
    known = titles.get(_title_key(media_type, request_tmdb_id(request)))
    if known:
        return known

    label = MEDIA_LABELS.get(media_type, "Media")
    tmdb_id = request_tmdb_id(request)
    return f"{label} {tmdb_id}" if tmdb_id is not None else label


def season_label(request: Dict) -> str:
    """Which seasons a series request covers: "S1, S3" or "5 seasons"."""
    if request_media_type(request) != "tv":
        return ""

    seasons = request.get("seasons")
    numbers = sorted(
        _int(season.get("seasonNumber"))
        for season in (seasons if isinstance(seasons, list) else [])
        if isinstance(season, dict)
    )
    numbers = [number for number in numbers if number > 0]
    if not numbers:
        # older payloads only carry the count
        count = _int(request.get("seasonCount"))
        return _seasons(count) if count else ""

    if len(numbers) <= 4:
        return ", ".join(f"S{number}" for number in numbers)
    return _seasons(len(numbers))


def _seasons(count: int) -> str:
    return f"{count} season{'s' if count != 1 else ''}"


def request_subtext(request: Dict) -> str:
    """One line describing a request: type, seasons, status, who and when."""
    parts = [MEDIA_LABELS.get(request_media_type(request), "Media")]

    seasons = season_label(request)
    if seasons:
        parts.append(seasons)

    parts.append(REQUEST_STATUS_LABELS.get(request_status(request), "Unknown status"))

    user = request.get("requestedBy")
    if isinstance(user, dict) and user.get("displayName"):
        parts.append(f"requested by {user['displayName']}")

    age = relative_time(request.get("createdAt"))
    if age:
        parts.append(age)

    return " | ".join(parts)


def result_media_type(result: Dict) -> str:
    """'movie' or 'tv' for a search hit that can be requested, "" otherwise."""
    media_type = result.get("mediaType")
    return media_type if media_type in MEDIA_LABELS else ""


def result_title(result: Dict) -> str:
    """The title of a search hit - TMDB calls a series' one `name`."""
    return str(result.get("title") or result.get("name") or "")


def result_year(result: Dict) -> str:
    """Just the year of a search hit's release or first-air date, "" if there is none."""
    date = str(result.get("releaseDate") or result.get("firstAirDate") or "")
    return date[:4] if len(date) >= 4 and date[:4].isdigit() else ""


def result_media_status(result: Dict) -> int:
    """The MediaStatus of the library entry a search hit already has, if any."""
    media = result.get("mediaInfo")
    return (
        _int(media.get("status"), MEDIA_UNKNOWN) if isinstance(media, dict) else MEDIA_UNKNOWN
    )


def can_request(result: Dict) -> bool:
    """True when asking Jellyseerr for *result* is likely to be accepted.

    The search response carries the library entry a hit already has, but not the
    requests against it, so the media status is as much as this can go on:

      - Available: everything is in the library already, nothing to ask for.
      - A series: some seasons may well be missing, and Jellyseerr drops the
        ones that are not rather than refusing, so it is always worth asking.
      - A movie: either untouched or already requested. A declined request sets
        the media status back to unknown, so "already requested" is exactly what
        pending, processing and partially available mean here.
    """
    status = result_media_status(result)
    if status == MEDIA_AVAILABLE:
        return False
    if result_media_type(result) == "tv":
        return True
    return status == MEDIA_UNKNOWN


def result_subtext(result: Dict) -> str:
    """One line describing a search hit: type, year and what the library has."""
    parts = [MEDIA_LABELS.get(result_media_type(result), "Media")]

    year = result_year(result)
    if year:
        parts.append(year)

    parts.append(MEDIA_STATUS_LABELS.get(result_media_status(result), "Unknown status"))
    return " | ".join(parts)


# main plugin class --------------------------------------------------------------------------


class Plugin(PluginInstance, GeneratorQueryHandler):
    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)

        # readConfig is untyped in the stub and hands back whatever was stored,
        # so a value edited by hand can be anything
        self._url: str = str(self.readConfig(CONFIG_URL, str) or "").strip()
        self._token: str = str(self.readConfig(CONFIG_API_TOKEN, str) or "").strip()
        self._token_command: str = str(
            self.readConfig(CONFIG_API_TOKEN_COMMAND, str) or ""
        ).strip()

        # Guards the three caches below. They are in memory only: a restart of
        # albert is a good enough reason to ask Jellyseerr again, and nothing
        # here is expensive enough to be worth writing to disk.
        self._lock = threading.Lock()
        self._requests: Optional[Tuple[float, List[Dict]]] = None
        self._titles: Dict[str, str] = {}
        self._searches: Dict[str, Tuple[float, List[Dict]]] = {}
        # The key a command printed, once it has been fetched. In memory only,
        # so a key sourced from a command never touches the config on disk.
        self._resolved_token: Optional[str] = None

    # -- config, bound to the settings widget below ---------------------------------------

    @property
    def jellyseerr_url(self) -> str:
        return self._url

    @jellyseerr_url.setter
    def jellyseerr_url(self, value: str):
        self._url = (value or "").strip()
        self.writeConfig(CONFIG_URL, self._url)
        self._forget()

    @property
    def api_key(self) -> str:
        return self._token

    @api_key.setter
    def api_key(self, value: str):
        self._token = (value or "").strip()
        self.writeConfig(CONFIG_API_TOKEN, self._token)
        self._resolved_token = None
        self._forget()

    @property
    def api_key_command(self) -> str:
        return self._token_command

    @api_key_command.setter
    def api_key_command(self, value: str):
        self._token_command = (value or "").strip()
        self.writeConfig(CONFIG_API_TOKEN_COMMAND, self._token_command)
        self._resolved_token = None
        self._forget()

    def configWidget(self):
        return [
            {
                "type": "label",
                "text": (
                    "Point this at your Jellyseerr server and give it an API key. The "
                    "plugin only ever talks to that one server, and it reads and writes "
                    "nothing but media requests."
                ),
            },
            {
                "type": "lineedit",
                "property": "jellyseerr_url",
                "label": "Jellyseerr URL",
                "widget_properties": {"placeholderText": "http://localhost:5055"},
            },
            {
                "type": "lineedit",
                "property": "api_key",
                "label": "API key",
                "widget_properties": {
                    "echoMode": 2,
                    "placeholderText": "Settings > General > API Key",
                },
            },
            {
                "type": "label",
                "text": (
                    "A key typed above is kept by Albert in plaintext. To keep it off the "
                    "disk entirely, leave that field empty and put a command here instead: "
                    "it is run through the shell and must print the key on stdout, e.g. "
                    "'pass show jellyseerr' or 'rbw get jellyseerr'. The command wins over "
                    "the field above, and the key it prints is held in memory only."
                ),
            },
            {
                "type": "lineedit",
                "property": "api_key_command",
                "label": "API key command",
                "widget_properties": {"placeholderText": "pass show jellyseerr"},
            },
            {
                "type": "label",
                "text": (
                    "Jellyseerr's own name for the key is API Key; find it in its web UI "
                    "under Settings > General. Requests made here are made as the user "
                    "that key belongs to, which for an administrator's key means they are "
                    "approved on the spot instead of being queued."
                ),
            },
        ]

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "seerr "

    def synopsis(self, query):
        return "a title, or nothing for the recent requests"

    # -- caches ---------------------------------------------------------------------------

    def _forget(self) -> None:
        """Drop every cached answer, so the next query asks Jellyseerr again."""
        with self._lock:
            self._requests = None
            self._titles = {}
            self._searches = {}

    def _api_key(self) -> str:
        """The API key to send, running the configured command at most once.

        The plaintext key is used as-is when no command is set. Once a command
        has printed a key it is remembered in memory, so an ordinary session
        runs it once rather than on every keystroke; a failure is not cached, so
        unlocking the password manager and retrying just works.

        .. raises:: JellyseerrError
        """
        if not self._token_command:
            return self._token

        with self._lock:
            cached = self._resolved_token
        if cached is not None:
            return cached

        # run the command outside the lock: it is a subprocess, not a lookup
        key = resolve_api_key(self._token, self._token_command)
        with self._lock:
            self._resolved_token = key
        return key

    def _request_list(self) -> List[Dict]:
        """The recent requests, refetched at most every REQUESTS_TTL seconds.

        .. raises:: JellyseerrError
        """
        with self._lock:
            cached = self._requests
        if cached is not None and time.monotonic() - cached[0] < REQUESTS_TTL:
            return cached[1]

        requests_list = sort_requests(fetch_requests(self._url, self._api_key()))

        # resolved outside the lock and swapped in after: this is one round trip
        # per row, and holding the lock through it would block every action
        with self._lock:
            titles = dict(self._titles)
        resolve_titles(self._url, self._api_key(), titles, request_refs(requests_list))
        with self._lock:
            self._titles = titles
            self._requests = (time.monotonic(), requests_list)

        return requests_list

    def _search(self, term: str) -> List[Dict]:
        """The search hits for *term*, refetched at most every SEARCH_TTL seconds.

        .. raises:: JellyseerrError
        """
        with self._lock:
            cached = self._searches.get(term)
        if cached is not None and time.monotonic() - cached[0] < SEARCH_TTL:
            return cached[1]

        results = fetch_search(self._url, self._api_key(), term)

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
        still being typed is gone within the delay and never reaches Jellyseerr,
        which matters because every search is a TMDB lookup on its side.
        """
        deadline = time.monotonic() + delay
        while ctx.isValid and time.monotonic() < deadline:
            time.sleep(0.02)
        return bool(ctx.isValid)

    # -- items --------------------------------------------------------------------------------

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        try:
            setup = self._setup_item()
            if setup is not None:
                yield [setup]
                return

            term = ctx.query.strip()

            if not term:
                requests_list = self._request_list()
                if not ctx.isValid:
                    return
                yield self._request_items(requests_list)
                return

            if len(term) < MIN_SEARCH_CHARS:
                yield [self._short_query_item(term)]
                return

            if not self._wait_for_still_input(ctx):
                return

            results = self._search(term)
            if not ctx.isValid:
                return
            yield self._search_items(term, results)

        except JellyseerrError as e:
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
        """The one item to show while the plugin is not configured yet."""
        if not self._url:
            return StandardItem(
                id=f"{self.id()}.setup-url",
                icon_factory=self.makeIcon,
                text="Please fill in the plugin settings - Jellyseerr URL missing",
                subtext="Open the Jellyseerr plugin in the Albert settings to configure it.",
                input_action_text="",
                actions=[
                    Action(
                        "open",
                        "Open the Jellyseerr website",
                        lambda: openUrl(JELLYSEERR_URL),
                    )
                ],
            )

        if not self._token and not self._token_command:
            return StandardItem(
                id=f"{self.id()}.setup-key",
                icon_factory=self.makeIcon,
                text="Please fill in the plugin settings - Jellyseerr API key missing",
                subtext=(
                    f"Paste the key, or a command that prints it, in the plugin settings. "
                    f"Find it in Jellyseerr at {home_url(self._url)} under "
                    "Settings > General > API Key."
                ),
                input_action_text="",
                actions=[
                    Action("open", "Open Jellyseerr", lambda: openUrl(home_url(self._url)))
                ],
            )

        return None

    def _request_items(self, requests_list: Sequence[Dict]) -> List[StandardItem]:
        if not requests_list:
            return [self._no_requests_item()]

        with self._lock:
            titles = dict(self._titles)
        return [self._request_item(request, titles) for request in requests_list]

    def _request_item(self, request: Dict, titles: Dict[str, str]) -> StandardItem:
        """One row of the request list.

        ENTER approves a pending request - deciding on them is the point of the
        plugin - and opens anything else in the browser, because there is
        nothing left to decide about it.
        """
        request_id = request.get("id")
        title = request_title(request, titles)
        page = media_url(self._url, request_media_type(request), request_tmdb_id(request))

        actions: List[Action] = []
        if request_status(request) == STATUS_PENDING:
            actions.append(
                Action(
                    "approve",
                    f"Approve {title}",
                    lambda i=request_id, t=title: self._approve(i, t),
                )
            )
            actions.append(
                Action(
                    "decline",
                    f"Decline {title}",
                    lambda i=request_id, t=title: self._decline(i, t),
                )
            )
        actions.append(Action("open", "Open in browser", lambda url=page: openUrl(url)))
        actions.append(
            Action("site", "Open Jellyseerr", lambda: openUrl(requests_url(self._url)))
        )
        actions.append(Action("reload", "Reload the request list", self._forget))

        return StandardItem(
            id=f"{self.id()}.request-{request_id}",
            icon_factory=self.makeIcon,
            text=title,
            subtext=request_subtext(request),
            input_action_text=f"{self.defaultTrigger()}{title}",
            actions=actions,
        )

    def _no_requests_item(self) -> StandardItem:
        return StandardItem(
            id=f"{self.id()}.no-requests",
            icon_factory=self.makeIcon,
            text="No requests on this Jellyseerr yet",
            subtext="Type a movie or series title to request one",
            input_action_text="",
            actions=[
                Action("site", "Open Jellyseerr", lambda: openUrl(requests_url(self._url))),
                Action("reload", "Reload the request list", self._forget),
            ],
        )

    def _search_items(self, term: str, results: Sequence[Dict]) -> List[StandardItem]:
        if not results:
            return [self._no_match_item(term)]
        return [self._result_item(result) for result in results[:SEARCH_LIMIT]]

    def _result_item(self, result: Dict) -> StandardItem:
        """One search hit.

        ENTER requests it when there is anything left to request, and opens its
        page in the browser otherwise.
        """
        media_type = result_media_type(result)
        tmdb_id = result.get("id")
        title = result_title(result)
        page = media_url(self._url, media_type, tmdb_id)

        actions = [Action("open", "Open in browser", lambda url=page: openUrl(url))]
        if can_request(result):
            actions.insert(
                0,
                Action(
                    "request",
                    f"Request {title}",
                    lambda t=title, m=media_type, i=tmdb_id: self._request(m, i, t),
                ),
            )
        actions.append(Action("site", "Open Jellyseerr", lambda: openUrl(home_url(self._url))))

        return StandardItem(
            id=f"{self.id()}.result-{media_type}-{tmdb_id}",
            icon_factory=self.makeIcon,
            text=title,
            subtext=result_subtext(result),
            input_action_text=f"{self.defaultTrigger()}{title}",
            actions=actions,
        )

    def _short_query_item(self, term: str) -> StandardItem:
        return StandardItem(
            id=f"{self.id()}.short-query",
            icon_factory=self.makeIcon,
            text=f"Search Jellyseerr for {term}",
            subtext=(
                f"Jellyseerr is searched from {MIN_SEARCH_CHARS} characters - clear the "
                "query for the recent requests"
            ),
            input_action_text="",
            actions=[
                Action("site", "Open Jellyseerr", lambda: openUrl(home_url(self._url)))
            ],
        )

    def _no_match_item(self, term: str) -> StandardItem:
        return StandardItem(
            id=f"{self.id()}.no-match",
            icon_factory=self.makeIcon,
            text=f'Nothing on Jellyseerr matches "{term}"',
            subtext="It searches TMDB, so the title may simply not be known there yet",
            input_action_text="",
            actions=[
                Action("site", "Open Jellyseerr", lambda: openUrl(home_url(self._url))),
                Action("reload", "Search again", self._forget),
            ],
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

    # -- the actions --------------------------------------------------------------------------

    def _approve(self, request_id: Any, title: str) -> None:
        # the key is resolved inside the worker, so a command that fails to
        # print one is reported like any other action failure
        self._async(
            lambda: set_request_status(self._url, self._api_key(), request_id, "approve"),
            f"Approved {title}",
        )

    def _decline(self, request_id: Any, title: str) -> None:
        self._async(
            lambda: set_request_status(self._url, self._api_key(), request_id, "decline"),
            f"Declined {title}",
        )

    def _request(self, media_type: str, tmdb_id: Any, title: str) -> None:
        self._async(
            lambda: create_request(self._url, self._api_key(), media_type, tmdb_id),
            f"Requested {title}",
        )

    def _async(self, work: Callable[[], Any], note: str) -> None:
        """Drop the caches, then run *work* off the UI thread and report it.

        The caches go first so that a query arriving while the request is still
        in flight does not rebuild the list as it was before the change.
        """
        self._forget()
        threading.Thread(
            target=self._mutate, args=(work, note), name="jellyseerr-action", daemon=True
        ).start()

    @staticmethod
    def _mutate(work: Callable[[], Any], note: str) -> None:
        try:
            work()
        except JellyseerrError as e:
            debug(traceback.format_exc())
            notify(str(e))
        except Exception:
            trace = traceback.format_exc()
            critical(trace)
            notify(trace.strip().splitlines()[-1] if trace.strip() else "unknown error")
        else:
            notify(note)
