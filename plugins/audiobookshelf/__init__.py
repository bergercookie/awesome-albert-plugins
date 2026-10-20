"""Audiobookshelf - search your audiobook library and play it locally.

The plugin keeps one server - an `Audiobookshelf`_ instance - in view. Anything
typed after the trigger is searched on that server's own library, and ENTER on a
hit plays the audiobook through a local player, `cvlc` by default.

Everything goes through Audiobookshelf's REST API with the plugin's API key, and
the audio itself is streamed straight from the server to the player, so the
server keeps track of nothing and nothing else is ever contacted.

.. _Audiobookshelf: https://www.audiobookshelf.org/
"""

import shlex
import subprocess
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple
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
md_name = "Audiobookshelf"
md_description = "Search an Audiobookshelf library and play audiobooks with a local player"
md_license = "MIT"
md_url = (
    "https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/"
    "audiobookshelf"
)
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["requests"]
md_bin_dependencies = ["cvlc"]

ICON_DIR = Path(__file__).parent
ICON_PATH = ICON_DIR / "audiobookshelf.svg"

CONFIG_URL = "audiobookshelf_url"
CONFIG_API_TOKEN = "audiobookshelf_api_token"
CONFIG_API_TOKEN_COMMAND = "audiobookshelf_api_token_command"
CONFIG_PLAYER = "audiobookshelf_player"

AUDIOBOOKSHELF_URL = "https://www.audiobookshelf.org/"

# Audiobookshelf groups its media into libraries, and only one kind of library
# holds audiobooks; podcasts are a library of their own and are left alone.
AUDIOBOOK_MEDIA_TYPE = "book"

HTTP_TIMEOUT = 10
KEY_COMMAND_TIMEOUT = 30
# How many hits one search asks each library for. It is also the cap on the
# merged list, since a hit in a second library is no more useful than one in the
# first.
SEARCH_LIMIT = 20
# An author match carries no books of its own, so each one is followed up with a
# second request. Only the first few are followed, which is enough to keep an
# author search useful without turning it into a burst of requests.
AUTHOR_LIMIT = 3
MIN_SEARCH_CHARS = 2
# Albert runs a fresh query per keystroke and cancels the one before it, so this
# is a debounce with no timer of the plugin's own: a term that is still being
# typed never reaches the server.
SEARCH_DEBOUNCE = 0.25
# The library list changes rarely, so it is cached for much longer than a search.
LIBRARIES_TTL = 300
SEARCH_TTL = 60
# Searched terms remembered, which is what makes backspacing over a word free
# instead of one search per deleted character.
SEARCH_CACHE_SIZE = 8
DEFAULT_PLAYER = "cvlc"
USER_AGENT = "awesome-albert-plugins/audiobookshelf"


# -- the plugin's own error -------------------------------------------------------------------


class AudiobookshelfError(Exception):
    """A sentence worth showing to the user, not a stack trace."""


def notify(msg: str, app_name: str = md_name) -> None:
    Notification(app_name, msg).send()


# -- urls ------------------------------------------------------------------------------------


def join_url(base_url: str, path: str) -> str:
    """Join *path* onto the Audiobookshelf base URL.

    The leading slash is dropped on purpose: an Audiobookshelf behind a reverse
    proxy keeps its prefix on the API routes as well as on the web UI routes, and
    a leading slash would climb back out of that prefix.

    >>> join_url("http://localhost:13378", "api/libraries")
    'http://localhost:13378/api/libraries'
    >>> join_url("http://localhost:13378/", "/api/libraries")
    'http://localhost:13378/api/libraries'
    >>> join_url("https://audio.example.com/abs", "/item/abc")
    'https://audio.example.com/abs/item/abc'
    """
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def home_url(base_url: str) -> str:
    """The Audiobookshelf web UI root, without its trailing slash.

    >>> home_url("http://localhost:13378/")
    'http://localhost:13378'
    """
    return base_url.rstrip("/")


def item_url(base_url: str, item_id: Any) -> str:
    """The web UI page of one library item.

    >>> item_url("http://localhost:13378", "abc")
    'http://localhost:13378/item/abc'
    """
    return join_url(base_url, f"item/{item_id}")


def stream_url(base_url: str, content_url: str, token: str) -> str:
    """A playable, authenticated URL for one audio file.

    The player is a separate process and cannot send the API key as a header, so
    the key goes into the query string - which Audiobookshelf's authentication
    accepts - and nowhere else.

    >>> stream_url("http://x:13378", "/api/items/abc/file/1", "k")
    'http://x:13378/api/items/abc/file/1?token=k'
    >>> stream_url("http://x:13378/", "api/items/abc/file/1", "")
    'http://x:13378/api/items/abc/file/1'
    """
    url = join_url(base_url, content_url)
    if token:
        url = f"{url}?{urlencode({'token': token})}"
    return url


# -- the API key -----------------------------------------------------------------------------


def resolve_api_key(token: str, command: str) -> str:
    """The API key to send, from the plaintext *token* or from *command*.

    A *command* wins over the plaintext key, so the latter can be left out of
    Albert's config entirely. The command is run through the shell and is
    expected to print the key on stdout, e.g. ``pass show audiobookshelf`` or
    ``rbw get audiobookshelf``; everything around it is ignored. Whatever it
    prints is held in memory only - it is never written back to the config.

    >>> resolve_api_key("  plain  ", "")
    'plain'
    >>> resolve_api_key("  plain  ", "   ")
    'plain'

    .. raises:: AudiobookshelfError
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
        raise AudiobookshelfError(
            f'"{command}" took longer than {KEY_COMMAND_TIMEOUT}s to print the API key.'
        ) from e
    except OSError as e:
        raise AudiobookshelfError(f'Could not run "{command}": {e}') from e

    if proc.returncode != 0:
        detail = " ".join((proc.stderr or "").split())
        message = f'"{command}" failed to print the API key'
        raise AudiobookshelfError(f"{message}: {detail}" if detail else f"{message}.")

    key = (proc.stdout or "").strip()
    if not key:
        raise AudiobookshelfError(
            f'"{command}" printed nothing; it must print the API key on stdout.'
        )
    return key


# -- talking to the server -------------------------------------------------------------------


def call(
    method: str,
    base_url: str,
    token: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: float = HTTP_TIMEOUT,
) -> Any:
    """One round trip to Audiobookshelf, returning the decoded JSON body.

    Audiobookshelf authenticates with a bearer token - either a personal API
    token or an administrator's API key - and acts as the user it belongs to.

    .. raises:: AudiobookshelfError
    """
    if not base_url:
        raise AudiobookshelfError(
            "No Audiobookshelf URL is configured. Add one in the plugin settings."
        )

    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise AudiobookshelfError(
            f'"{base_url}" is not a full URL. The plugin setting should look like '
            "http://localhost:13378."
        )

    kwargs: Dict[str, Any] = {
        "headers": {
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "Authorization": f"Bearer {token}",
        },
        "timeout": timeout,
    }

    url = join_url(base_url, path)
    if params:
        # requests url-encodes parameters with quote_plus, which turns a space
        # into "+". Encode with quote instead, which writes a space as %20 and a
        # literal plus as %2B, so a title like "C++" survives the round trip.
        url = f"{url}?{urlencode(params, quote_via=quote)}"

    try:
        response = requests.request(method, url, **kwargs)
    except requests.Timeout as e:
        raise AudiobookshelfError(f"{base_url} did not answer within {timeout:g}s.") from e
    except requests.RequestException as e:
        raise AudiobookshelfError(f"Cannot reach {base_url}: {e}") from e

    return _payload(response, base_url)


def _payload(response: Any, base_url: str) -> Any:
    """Decode *response*, turning an error status into an AudiobookshelfError.

    .. raises:: AudiobookshelfError
    """
    if response.status_code == 204:
        return None

    if response.status_code >= 400:
        raise AudiobookshelfError(_error_message(response, base_url))

    try:
        return response.json()
    except ValueError as e:
        raise AudiobookshelfError(
            f"{base_url} did not answer with JSON (HTTP {response.status_code})."
        ) from e


def _error_message(response: Any, base_url: str) -> str:
    """A sentence about what Audiobookshelf refused and why.

    Its handlers answer `{"error": ...}` or `{"message": ...}`, and a reverse
    proxy in front of it may answer with a page of HTML. All three end up here.
    """
    detail = ""
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        for key in ("error", "message"):
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


# -- reading Audiobookshelf ------------------------------------------------------------------


def _list(value: Any) -> List[Any]:
    """*value* when it is a list, an empty list otherwise."""
    return value if isinstance(value, list) else []


def _int(value: Any, default: int = 0) -> int:
    """*value* as an int, or *default* when it is not one."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def item_id(item: Dict) -> Optional[str]:
    """The library item's id, None when the payload does not carry one."""
    value = item.get("id")
    return str(value) if value is not None else None


def item_media(item: Dict) -> Dict:
    """The `media` object of a library item, {} when there is not one."""
    media = item.get("media")
    return media if isinstance(media, dict) else {}


def item_metadata(item: Dict) -> Dict:
    """The metadata of a library item, {} when there is not any.

    Metadata comes in two shapes: the minified and expanded listings carry flat
    `authorName`/`narratorName` fields, while an old-style item spells the same
    things as arrays. Both are read below.
    """
    metadata = item_media(item).get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def item_title(item: Dict) -> str:
    """The title of an audiobook, with a stand-in when it has none."""
    metadata = item_metadata(item)
    title = metadata.get("title") or item_media(item).get("title") or ""
    return str(title).strip() or "Untitled audiobook"


def _joined_names(value: Any) -> str:
    """The `name` of every object in a list, joined with commas."""
    names = [
        str(entry.get("name")).strip()
        for entry in _list(value)
        if isinstance(entry, dict) and entry.get("name")
    ]
    return ", ".join(name for name in names if name)


def item_author(item: Dict) -> str:
    """The author of an audiobook, "" when the payload names none."""
    metadata = item_metadata(item)
    name = metadata.get("authorName")
    return str(name).strip() if name else _joined_names(metadata.get("authors"))


def item_narrator(item: Dict) -> str:
    """The narrator of an audiobook, "" when the payload names none."""
    metadata = item_metadata(item)
    name = metadata.get("narratorName")
    if name:
        return str(name).strip()
    narrators = [str(n).strip() for n in _list(metadata.get("narrators")) if str(n).strip()]
    return ", ".join(narrators)


def item_series(item: Dict) -> str:
    """The series an audiobook belongs to, "" when it belongs to none."""
    metadata = item_metadata(item)
    name = metadata.get("seriesName")
    return str(name).strip() if name else _joined_names(metadata.get("series"))


def item_year(item: Dict) -> str:
    """The publication year of an audiobook, "" when there is none."""
    year = _int(item_metadata(item).get("publishedYear"))
    return str(year) if year else ""


def item_duration(item: Dict) -> int:
    """The length of an audiobook in seconds, 0 when it is not known."""
    return _int(item_media(item).get("duration"))


def format_duration(seconds: int) -> str:
    """A human length for *seconds*, "" when there is nothing to say.

    >>> format_duration(0)
    ''
    >>> format_duration(59)
    '<1m'
    >>> format_duration(125)
    '2m'
    >>> format_duration(3600)
    '1h'
    >>> format_duration(3720)
    '1h 2m'
    """
    if seconds <= 0:
        return ""

    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    if minutes:
        return f"{minutes}m"
    return "<1m"


def item_subtext(item: Dict) -> str:
    """One line describing an audiobook: author, narrator, series, year, length."""
    parts: List[str] = []
    author = item_author(item)
    if author:
        parts.append(author)

    narrator = item_narrator(item)
    if narrator and narrator != author:
        parts.append(f"narrated by {narrator}")

    series = item_series(item)
    if series:
        parts.append(series)

    year = item_year(item)
    if year:
        parts.append(year)

    length = format_duration(item_duration(item))
    if length:
        parts.append(length)

    return " | ".join(parts)


def item_tracks(item: Dict) -> List[str]:
    """The audio files of an audiobook as relative content URLs, in order.

    An expanded item names each file under `tracks`; a minified one carries
    neither `tracks` nor `audioFiles`, so this can be empty - the play action
    fetches the expanded item before it needs the files.
    """
    media = item_media(item)
    urls = [
        track["contentUrl"]
        for track in _list(media.get("tracks"))
        if isinstance(track, dict) and track.get("contentUrl")
    ]
    if urls:
        return [str(url) for url in urls]

    item_key = item_id(item)
    files = []
    for audio in _list(media.get("audioFiles")):
        if isinstance(audio, dict) and audio.get("ino") is not None and item_key:
            files.append(f"/api/items/{item_key}/file/{audio['ino']}")
    return files


def playable_urls(base_url: str, token: str, item: Dict) -> List[str]:
    """Every audio file of an audiobook as an absolute, authenticated URL."""
    return [stream_url(base_url, content_url, token) for content_url in item_tracks(item)]


def search_payload_items(payload: Dict) -> List[Dict]:
    """The library items a search payload names, in the order they matter.

    A book hit is one; a series hit is the books in it, so that typing a series
    name plays its books rather than showing the series itself.
    """
    items = []
    for entry in _list(payload.get("book")):
        if isinstance(entry, dict) and isinstance(entry.get("libraryItem"), dict):
            items.append(entry["libraryItem"])

    for entry in _list(payload.get("series")):
        if not isinstance(entry, dict):
            continue
        for book in _list(entry.get("books")):
            if isinstance(book, dict):
                items.append(book)

    return items


def search_payload_authors(payload: Dict, limit: int = AUTHOR_LIMIT) -> List[Tuple[str, str]]:
    """The (id, name) of the authors a search payload names, capped at *limit*.

    An author hit carries no books, so each one is a follow-up request; only the
    first few are worth that.
    """
    authors = []
    for entry in _list(payload.get("authors")):
        if isinstance(entry, dict) and entry.get("id"):
            authors.append((str(entry["id"]), str(entry.get("name") or "")))
    return authors[:limit]


def dedupe_items(items: Sequence[Dict]) -> List[Dict]:
    """The first item per id, in order, dropping anything without an id."""
    seen = set()
    result = []
    for item in items:
        key = item_id(item)
        if key is None or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


# -- talking to an Audiobookshelf library ----------------------------------------------------


def fetch_libraries(base_url: str, token: str) -> List[Dict]:
    """Every library on the server.

    .. raises:: AudiobookshelfError
    """
    payload = call("GET", base_url, token, "api/libraries")

    libraries = payload.get("libraries") if isinstance(payload, dict) else None
    if not isinstance(libraries, list):
        raise AudiobookshelfError(
            f"{base_url} answered the library list with something unexpected."
        )
    return [library for library in libraries if isinstance(library, dict)]


def fetch_audiobook_libraries(base_url: str, token: str) -> List[Dict]:
    """The libraries that hold audiobooks, podcasts left aside.

    .. raises:: AudiobookshelfError
    """
    return [
        library
        for library in fetch_libraries(base_url, token)
        if library.get("mediaType") == AUDIOBOOK_MEDIA_TYPE
    ]


def fetch_library_search(
    base_url: str, token: str, library_id: str, query: str, limit: int = SEARCH_LIMIT
) -> Dict:
    """Search one library's books, series and authors.

    .. raises:: AudiobookshelfError
    """
    payload = call(
        "GET",
        base_url,
        token,
        f"api/libraries/{library_id}/search",
        params={"q": query, "limit": limit},
    )
    if not isinstance(payload, dict):
        raise AudiobookshelfError(f"{base_url} answered the search with something unexpected.")
    return payload


def fetch_author_items(
    base_url: str, token: str, library_id: str, author_id: str, limit: int = SEARCH_LIMIT
) -> List[Dict]:
    """The books one author has in one library.

    .. raises:: AudiobookshelfError
    """
    payload = call(
        "GET",
        base_url,
        token,
        f"api/libraries/{library_id}/items",
        params={"filter": f"authors.{author_id}", "limit": limit},
    )

    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise AudiobookshelfError(
            f"{base_url} answered an author's books with something unexpected."
        )
    return [item for item in results if isinstance(item, dict)]


def fetch_item(base_url: str, token: str, item_id: Any) -> Dict:
    """One library item, expanded so that its audio files are named.

    .. raises:: AudiobookshelfError
    """
    if not item_id:
        raise AudiobookshelfError("Cannot play a library item without an id.")

    payload = call(
        "GET", base_url, token, f"api/items/{item_id}", params={"expanded": "1"}
    )
    if not isinstance(payload, dict):
        raise AudiobookshelfError(f"{base_url} answered the item with something unexpected.")
    return payload


def search_books(
    base_url: str,
    token: str,
    query: str,
    libraries: Sequence[Dict],
    limit: int = SEARCH_LIMIT,
) -> List[Dict]:
    """Search every audiobook library and return the playable items.

    An author or a series match is followed up with whatever books it is about,
    so the list is audiobooks to play rather than the authors and series around
    them.

    .. raises:: AudiobookshelfError
    """
    found: List[Dict] = []
    for library in libraries:
        library_id = library.get("id")
        if not library_id:
            continue

        payload = fetch_library_search(base_url, token, str(library_id), query, limit)
        found.extend(search_payload_items(payload))
        for author_id, _name in search_payload_authors(payload):
            author_items = fetch_author_items(
                base_url, token, str(library_id), author_id, limit
            )
            found.extend(author_items)

        if len(found) >= limit:
            break

    return dedupe_items(found)[:limit]


def fetch_item_detail(base_url: str, token: str, item: Dict) -> Dict:
    """The expanded library item behind *item*, refetched by its id.

    A listing may only carry the minified item, which names no audio files, so
    the id is all that can be relied on.

    .. raises:: AudiobookshelfError
    """
    item_key = item_id(item)
    if not item_key:
        raise AudiobookshelfError("That Audiobookshelf entry has no id to play by.")
    return fetch_item(base_url, token, item_key)


# -- the local player ------------------------------------------------------------------------


def player_argv(player: str) -> List[str]:
    """The player command split into an argument vector.

    >>> player_argv("cvlc")
    ['cvlc']
    >>> player_argv("cvlc --play-and-exit")
    ['cvlc', '--play-and-exit']

    .. raises:: AudiobookshelfError
    """
    argv = shlex.split(player or "")
    if not argv:
        raise AudiobookshelfError("No player is configured. Add one in the plugin settings.")
    return argv


def launch_player(player: str, urls: Sequence[str]) -> None:
    """Start *player* on *urls*, detached, so it outlives the query.

    .. raises:: AudiobookshelfError
    """
    if not urls:
        raise AudiobookshelfError("There is nothing to play.")

    argv = player_argv(player) + list(urls)
    try:
        subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as e:
        raise AudiobookshelfError(f'Could not run "{argv[0]}": {e}') from e


# -- the plugin ------------------------------------------------------------------------------


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
        self._player: str = (
            str(self.readConfig(CONFIG_PLAYER, str) or "").strip() or DEFAULT_PLAYER
        )

        # Guards the caches below. They are in memory only: a restart of albert
        # is a good enough reason to ask Audiobookshelf again.
        self._lock = threading.Lock()
        self._libraries: Optional[Tuple[float, List[Dict]]] = None
        self._searches: Dict[str, Tuple[float, List[Dict]]] = {}
        # The key a command printed, once it has been fetched. In memory only,
        # so a key sourced from a command never touches the config on disk.
        self._resolved_token: Optional[str] = None

    # -- config, bound to the settings widget below ---------------------------------------

    @property
    def audiobookshelf_url(self) -> str:
        return self._url

    @audiobookshelf_url.setter
    def audiobookshelf_url(self, value: str):
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

    @property
    def player_command(self) -> str:
        return self._player

    @player_command.setter
    def player_command(self, value: str):
        self._player = str(value or "").strip() or DEFAULT_PLAYER
        self.writeConfig(CONFIG_PLAYER, self._player)

    def configWidget(self):
        return [
            {
                "type": "label",
                "text": (
                    "Point this at your Audiobookshelf server and give it an API key. "
                    "The plugin only ever talks to that one server, reads your "
                    "audiobooks and hands their files to a local player."
                ),
            },
            {
                "type": "lineedit",
                "property": "audiobookshelf_url",
                "label": "Audiobookshelf URL",
                "widget_properties": {"placeholderText": "http://localhost:13378"},
            },
            {
                "type": "lineedit",
                "property": "api_key",
                "label": "API key",
                "widget_properties": {
                    "echoMode": 2,
                    "placeholderText": "an API key or personal token",
                },
            },
            {
                "type": "label",
                "text": (
                    "A key typed above is kept by Albert in plaintext. To keep it off the "
                    "disk entirely, leave that field empty and put a command here instead: "
                    "it is run through the shell and must print the key on stdout, e.g. "
                    "'pass show audiobookshelf'. The command wins over the field above, and "
                    "the key it prints is held in memory only."
                ),
            },
            {
                "type": "lineedit",
                "property": "api_key_command",
                "label": "API key command",
                "widget_properties": {"placeholderText": "pass show audiobookshelf"},
            },
            {
                "type": "lineedit",
                "property": "player_command",
                "label": "Player command",
                "widget_properties": {"placeholderText": DEFAULT_PLAYER},
            },
            {
                "type": "label",
                "text": (
                    "Audiobookshelf's own name for the key is API token; an administrator "
                    "creates API keys in its web UI under Settings > API Keys. The audio is "
                    "streamed to the player command above, 'cvlc' unless changed; extra "
                    "flags are allowed, e.g. 'cvlc --play-and-exit'."
                ),
            },
        ]

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "abs "

    def synopsis(self, query):
        return "an audiobook title, series or author"

    # -- caches --------------------------------------------------------------------------

    def _forget(self) -> None:
        """Drop every cached answer, so the next query asks Audiobookshelf again."""
        with self._lock:
            self._libraries = None
            self._searches = {}

    def _api_key(self) -> str:
        """The API key to send, running the configured command at most once.

        .. raises:: AudiobookshelfError
        """
        if not self._token_command:
            return self._token

        with self._lock:
            cached = self._resolved_token
        if cached is not None:
            return cached

        key = resolve_api_key(self._token, self._token_command)

        with self._lock:
            self._resolved_token = key
        return key

    def _audiobook_libraries(self) -> List[Dict]:
        """The audiobook libraries, refetched at most every LIBRARIES_TTL seconds.

        .. raises:: AudiobookshelfError
        """
        with self._lock:
            cached = self._libraries
        if cached is not None and time.monotonic() - cached[0] < LIBRARIES_TTL:
            return cached[1]

        libraries = fetch_audiobook_libraries(self._url, self._api_key())

        with self._lock:
            self._libraries = (time.monotonic(), libraries)
        return libraries

    def _search(self, term: str, libraries: Sequence[Dict]) -> List[Dict]:
        """The playable items for *term*, refetched at most every SEARCH_TTL seconds.

        .. raises:: AudiobookshelfError
        """
        with self._lock:
            cached = self._searches.get(term)
        if cached is not None and time.monotonic() - cached[0] < SEARCH_TTL:
            return cached[1]

        results = search_books(self._url, self._api_key(), term, libraries)

        with self._lock:
            self._searches[term] = (time.monotonic(), results)
            # only the most recent terms are kept, so the dict cannot grow for
            # the whole session while backspacing over a word stays free
            while len(self._searches) > SEARCH_CACHE_SIZE:
                oldest = min(self._searches, key=lambda key: self._searches[key][0])
                del self._searches[oldest]

        return results

    @staticmethod
    def _wait_for_still_input(ctx, delay: float = SEARCH_DEBOUNCE) -> bool:
        """Wait for the typing to stop, or False when the query was replaced."""
        deadline = time.monotonic() + delay
        while ctx.isValid and time.monotonic() < deadline:
            time.sleep(0.02)
        return bool(ctx.isValid)

    # -- items ---------------------------------------------------------------------------

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        try:
            setup = self._setup_item()
            if setup is not None:
                yield [setup]
                return

            term = ctx.query.strip()

            if not term:
                yield [self._hint_item()]
                return

            if len(term) < MIN_SEARCH_CHARS:
                yield [self._short_query_item(term)]
                return

            if not self._wait_for_still_input(ctx):
                return

            libraries = self._audiobook_libraries()
            if not ctx.isValid:
                return

            if not libraries:
                yield [self._no_library_item()]
                return

            results = self._search(term, libraries)
            if not ctx.isValid:
                return
            yield self._result_items(results)

        except AudiobookshelfError as e:
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
                text="Please fill in the plugin settings - Audiobookshelf URL missing",
                subtext=(
                    "Open the Audiobookshelf plugin in the Albert settings to configure it."
                ),
                input_action_text="",
                actions=[
                    Action(
                        "open",
                        "Open the Audiobookshelf website",
                        lambda: openUrl(AUDIOBOOKSHELF_URL),
                    )
                ],
            )

        if not self._token and not self._token_command:
            return StandardItem(
                id=f"{self.id()}.setup-key",
                icon_factory=self.makeIcon,
                text="Please fill in the plugin settings - Audiobookshelf API key missing",
                subtext=(
                    "Paste a key, or a command that prints one, in the plugin settings. An "
                    f"administrator creates them at {home_url(self._url)} under "
                    "Settings > API Keys."
                ),
                input_action_text="",
                actions=[
                    Action("open", "Open Audiobookshelf", lambda: openUrl(home_url(self._url)))
                ],
            )

        return None

    def _result_items(self, results: Sequence[Dict]) -> List[StandardItem]:
        if not results:
            return [self._no_match_item()]
        return [self._result_item(item) for item in results]

    def _result_item(self, item: Dict) -> StandardItem:
        """One audiobook. ENTER plays it, through the configured player."""
        item_key = item_id(item)
        title = item_title(item)
        page = item_url(self._url, item_key)

        return StandardItem(
            id=f"{self.id()}.result-{item_key}",
            icon_factory=self.makeIcon,
            text=title,
            subtext=item_subtext(item),
            input_action_text=f"{self.defaultTrigger()}{title}",
            actions=[
                Action("play", f"Play {title}", lambda i=item, t=title: self._play(i, t)),
                Action("open", "Open in browser", lambda url=page: openUrl(url)),
                self._site_action(),
            ],
        )

    def _site_action(self) -> Action:
        return Action("site", "Open Audiobookshelf", lambda: openUrl(home_url(self._url)))

    def _hint_item(self) -> StandardItem:
        return StandardItem(
            id=f"{self.id()}.hint",
            icon_factory=self.makeIcon,
            text="Search your Audiobookshelf library",
            subtext=(
                f"Type at least {MIN_SEARCH_CHARS} characters of an audiobook title, "
                "series or author to play one"
            ),
            input_action_text="",
            actions=[self._site_action()],
        )

    def _short_query_item(self, term: str) -> StandardItem:
        return StandardItem(
            id=f"{self.id()}.short-query",
            icon_factory=self.makeIcon,
            text=f"Search Audiobookshelf for {term}",
            subtext=f"Audiobookshelf is searched from {MIN_SEARCH_CHARS} characters",
            input_action_text="",
            actions=[self._site_action()],
        )

    def _no_library_item(self) -> StandardItem:
        return StandardItem(
            id=f"{self.id()}.no-library",
            icon_factory=self.makeIcon,
            text="No audiobook libraries on this Audiobookshelf",
            subtext="The server has no library of the 'book' kind to search",
            input_action_text="",
            actions=[self._site_action()],
        )

    def _no_match_item(self) -> StandardItem:
        return StandardItem(
            id=f"{self.id()}.no-match",
            icon_factory=self.makeIcon,
            text="Nothing in your Audiobookshelf library matches",
            subtext="It searches titles, series and authors of the books you have",
            input_action_text="",
            actions=[
                self._site_action(),
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

    # -- the action ----------------------------------------------------------------------

    def _play(self, item: Dict, title: str) -> None:
        threading.Thread(
            target=self._play_worker,
            args=(item, title),
            name="audiobookshelf-play",
            daemon=True,
        ).start()

    def _play_worker(self, item: Dict, title: str) -> None:
        try:
            token = self._api_key()
            detail = fetch_item_detail(self._url, token, item)
            urls = playable_urls(self._url, token, detail)
            launch_player(self._player, urls)
        except AudiobookshelfError as e:
            debug(traceback.format_exc())
            notify(str(e))
        except Exception:
            trace = traceback.format_exc()
            critical(trace)
            notify(trace.strip().splitlines()[-1] if trace.strip() else "unknown error")
        else:
            notify(f"Playing {title}")
