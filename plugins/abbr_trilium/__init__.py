"""Abbreviations stored in a Trilium note.

The plugin reads abbreviation lines from a designated note through Trilium's
ETAPI, searches them like the plain-file abbreviations plugin, and appends new
ones back to the same note.
"""

import html
import re
import subprocess
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

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
from fuzzywuzzy import process

md_iid = "5.0"
md_version = "0.1"
md_name = "Abbreviations (Trilium)"
md_description = "Store and look up abbreviations in a Trilium note"
md_license = "MIT"
md_url = (
    "https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/abbr_trilium"
)
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["fuzzywuzzy", "requests"]
md_bin_dependencies: List[str] = []

ICON_PATH = Path(__file__).parent / "abbr.png"

CONFIG_URL = "trilium_url"
CONFIG_TOKEN = "trilium_etapi_token"
CONFIG_TOKEN_COMMAND = "trilium_etapi_token_command"
CONFIG_NOTE_ID = "trilium_note_id"
CONFIG_VERIFY_SSL = "trilium_verify_ssl"

DEFAULT_SEPARATOR = ":"
HTTP_TIMEOUT = 10
# How long a command that prints the ETAPI token may take. A password manager
# that has to be unlocked can be slow, but not this slow.
KEY_COMMAND_TIMEOUT = 30
NOTE_TTL = 30.0
USER_AGENT = "awesome-albert-plugins/abbr_trilium"

BREAK_RE = re.compile(r"<\s*(?:br|/p|/div|/li|/h[1-6])\s*/?\s*>", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")


# plugin main functions -----------------------------------------------------------------------


class TriliumError(Exception):
    """A failure worth showing to the user as-is."""


def notify(msg: str, app_name: str = md_name) -> None:
    Notification(app_name, msg).send()


# the ETAPI token -----------------------------------------------------------------------------


def resolve_api_key(token: str, command: str) -> str:
    """The ETAPI token to send, from the plaintext *token* or from *command*.

    A *command* wins over the plaintext token, so the latter can be left out of
    Albert's config entirely. The command is run through the shell and is
    expected to print the token on stdout, e.g. ``pass show trilium`` or
    ``rbw get trilium``; everything around it is ignored. Whatever it prints is
    held in memory only - it is never written back to the config.

    >>> resolve_api_key("  plain  ", "")
    'plain'
    >>> resolve_api_key("  plain  ", "   ")
    'plain'

    .. raises:: TriliumError
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
        raise TriliumError(
            f'"{command}" took longer than {KEY_COMMAND_TIMEOUT}s to print the ETAPI token.'
        ) from e
    except OSError as e:
        raise TriliumError(f'Could not run "{command}": {e}') from e

    if proc.returncode != 0:
        detail = " ".join((proc.stderr or "").split())
        message = f'"{command}" failed to print the ETAPI token'
        raise TriliumError(f"{message}: {detail}" if detail else f"{message}.")

    key = (proc.stdout or "").strip()
    if not key:
        raise TriliumError(
            f'"{command}" printed nothing; it must print the ETAPI token on stdout.'
        )
    return key


# supplementary functions ---------------------------------------------------------------------


def join_url(base_url: str, path: str) -> str:
    """Join *path* onto the Trilium base URL, keeping a reverse-proxy prefix."""
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def normalize_note_id(value: str) -> str:
    """The ETAPI note ID from a note URL, a note path, or a bare note ID.

    Trilium URLs carry the whole path to the note after a ``#``, but the ETAPI
    only wants the last segment.

    >>> normalize_note_id("v9MDnZFkTKYF")
    'v9MDnZFkTKYF'
    >>> normalize_note_id("#root/QIaJXuFX5LkL/qWEdT6qn61dY/v9MDnZFkTKYF")
    'v9MDnZFkTKYF'
    >>> normalize_note_id("https://trilium.example.com/#root/QIaJXuFX5LkL/v9MDnZFkTKYF")
    'v9MDnZFkTKYF'
    """
    value = (value or "").strip()
    if not value:
        return ""

    parsed = urlparse(value)
    path = parsed.fragment or parsed.path or value
    segment = path.rstrip("/").rsplit("/", 1)[-1]
    return segment.split("?", 1)[0].split("#", 1)[0].strip()


def html_to_text(content: str) -> str:
    """Turn the HTML content of a Trilium text note into plain text lines."""
    content = BREAK_RE.sub("\n", content)
    content = TAG_RE.sub("", content)
    return html.unescape(content)


def make_latest_entries(
    conts: List[str], separator: str = DEFAULT_SEPARATOR
) -> List[Tuple[str, str]]:
    entries = []
    for li in conts:
        tokens = li.split(separator, maxsplit=1)
        if len(tokens) == 2:
            if any(not t for t in tokens):
                continue

            tokens = [t.strip().strip("*").strip() for t in tokens]
            entries.append((tokens[0], tokens[1]))

    return entries


def make_search_index(entries: List[Tuple[str, str]]) -> Dict[str, List[int]]:
    """Map every abbreviation and description to the entries that contain it."""
    index: Dict[str, List[int]] = {}
    for i, entry in enumerate(entries):
        for term in entry:
            index.setdefault(term, []).append(i)

    return index


def abbreviation_line(name: str, desc: str, separator: str = DEFAULT_SEPARATOR) -> str:
    return f"* {name}{separator} {desc}"


def append_abbreviation(content: str, note_type: str, line: str) -> str:
    """Append *line* to note *content*, as a list item for a text note."""
    if note_type == "text":
        text = line[2:] if line.startswith("* ") else line
        item = f"<li>{html.escape(text)}</li>"
        stripped = content.rstrip()
        if stripped.endswith("</ul>"):
            return f"{stripped[:-5]}{item}</ul>"
        return f"{content}<ul>{item}</ul>"

    if content and not content.endswith("\n"):
        content += "\n"
    return f"{content}{line}\n"


# talking to Trilium --------------------------------------------------------------------------


def request(
    method: str,
    base_url: str,
    token: str,
    path: str,
    verify: bool,
    *,
    data: Optional[str] = None,
    content_type: Optional[str] = None,
    timeout: float = HTTP_TIMEOUT,
) -> requests.Response:
    """One round trip to Trilium's ETAPI.

    .. raises:: TriliumError
    """
    if not base_url:
        raise TriliumError("No Trilium URL is configured. Add one in the plugin settings.")

    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise TriliumError(
            f'"{base_url}" is not a full URL. The plugin setting should look like '
            "https://trilium.example.com."
        )

    headers = {"Authorization": token, "User-Agent": USER_AGENT}
    if content_type:
        headers["Content-Type"] = content_type

    try:
        response = requests.request(
            method,
            join_url(base_url, path),
            headers=headers,
            data=data,
            verify=verify,
            timeout=timeout,
        )
    except requests.Timeout as e:
        raise TriliumError(f"{base_url} did not answer within {timeout:g}s.") from e
    except requests.RequestException as e:
        raise TriliumError(f"Cannot reach {base_url}: {e}") from e

    if response.status_code >= 400:
        raise TriliumError(error_message(response, base_url))

    return response


def error_message(response: Any, base_url: str) -> str:
    detail = ""
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        for key in ("message", "code"):
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
        message += ". Check the ETAPI token in the plugin settings."
    if response.status_code == 404:
        message += ". Check the note ID or URL in the plugin settings."
    return message


def fetch_note(base_url: str, token: str, note_id: str, verify: bool) -> Dict[str, Any]:
    response = request("GET", base_url, token, f"etapi/notes/{note_id}", verify)
    try:
        payload = response.json()
    except ValueError as e:
        raise TriliumError(
            f"{base_url} did not answer with JSON (HTTP {response.status_code})."
        ) from e

    if not isinstance(payload, dict):
        raise TriliumError(f"{base_url} answered the note with something unexpected.")
    return payload


def fetch_note_content(base_url: str, token: str, note_id: str, verify: bool) -> str:
    response = request(
        "GET", base_url, token, f"etapi/notes/{note_id}/content", verify
    )
    return str(response.text)


def put_note_content(
    base_url: str, token: str, note_id: str, verify: bool, content: str
) -> None:
    request(
        "PUT",
        base_url,
        token,
        f"etapi/notes/{note_id}/content",
        verify,
        data=content,
        content_type="text/plain",
    )


# main plugin class --------------------------------------------------------------------------


class Plugin(PluginInstance, GeneratorQueryHandler):
    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)

        self._url: str = str(self.readConfig(CONFIG_URL, str) or "").strip()
        self._token: str = str(self.readConfig(CONFIG_TOKEN, str) or "").strip()
        self._token_command: str = str(
            self.readConfig(CONFIG_TOKEN_COMMAND, str) or ""
        ).strip()
        self._note_id: str = normalize_note_id(
            str(self.readConfig(CONFIG_NOTE_ID, str) or "")
        )
        verify = self.readConfig(CONFIG_VERIFY_SSL, bool)
        self._verify_ssl: bool = True if verify is None else bool(verify)

        self._lock = threading.Lock()
        self._cache: Optional[
            Tuple[float, List[Tuple[str, str]], Dict[str, List[int]]]
        ] = None
        # The token a command printed, once it has been fetched. In memory only,
        # so a token sourced from a command never touches the config on disk.
        self._resolved_token: Optional[str] = None

    # -- config, bound to the settings widget below ---------------------------------------

    @property
    def trilium_url(self) -> str:
        return self._url

    @trilium_url.setter
    def trilium_url(self, value: str):
        self._url = (value or "").strip()
        self.writeConfig(CONFIG_URL, self._url)
        self._forget()

    @property
    def etapi_token(self) -> str:
        return self._token

    @etapi_token.setter
    def etapi_token(self, value: str):
        self._token = (value or "").strip()
        self.writeConfig(CONFIG_TOKEN, self._token)
        self._resolved_token = None
        self._forget()

    @property
    def etapi_token_command(self) -> str:
        return self._token_command

    @etapi_token_command.setter
    def etapi_token_command(self, value: str):
        self._token_command = (value or "").strip()
        self.writeConfig(CONFIG_TOKEN_COMMAND, self._token_command)
        self._resolved_token = None
        self._forget()

    @property
    def note_id(self) -> str:
        return self._note_id

    @note_id.setter
    def note_id(self, value: str):
        self._note_id = normalize_note_id(value)
        self.writeConfig(CONFIG_NOTE_ID, self._note_id)
        self._forget()

    @property
    def verify_ssl(self) -> bool:
        return self._verify_ssl

    @verify_ssl.setter
    def verify_ssl(self, value: bool):
        self._verify_ssl = bool(value)
        self.writeConfig(CONFIG_VERIFY_SSL, self._verify_ssl)
        self._forget()

    def configWidget(self):
        return [
            {
                "type": "label",
                "text": (
                    "Point this at your Trilium server and the note that holds the "
                    "abbreviations. Each line is read as '* abbreviation: description', "
                    "and new abbreviations are appended to the same note."
                ),
            },
            {
                "type": "lineedit",
                "property": "trilium_url",
                "label": "Trilium URL",
                "widget_properties": {"placeholderText": "https://trilium.example.com"},
            },
            {
                "type": "lineedit",
                "property": "etapi_token",
                "label": "ETAPI token",
                "widget_properties": {
                    "echoMode": 2,
                    "placeholderText": "Options > ETAPI",
                },
            },
            {
                "type": "label",
                "text": (
                    "A token typed above is kept by Albert in plaintext. To keep it off "
                    "the disk entirely, leave that field empty and put a command here "
                    "instead: it is run through the shell and must print the token on "
                    "stdout, e.g. 'pass show trilium'. The command wins over the field "
                    "above, and the token it prints is held in memory only."
                ),
            },
            {
                "type": "lineedit",
                "property": "etapi_token_command",
                "label": "ETAPI token command",
                "widget_properties": {"placeholderText": "pass show trilium"},
            },
            {
                "type": "lineedit",
                "property": "note_id",
                "label": "Abbreviations note ID or URL",
                "widget_properties": {
                    "placeholderText": "e.g. https://trilium.example.com/#root/.../i6ra4ZshJhgN"
                },
            },
            {
                "type": "checkbox",
                "property": "verify_ssl",
                "label": "Verify TLS certificate (turn off only for self-signed setups)",
            },
            {
                "type": "label",
                "text": (
                    "Create the token in Trilium under Options > ETAPI. Paste the whole "
                    "note URL or just its last path segment (the note ID). A Text note "
                    "gets HTML bullet list items; a Code note with a plain-text MIME "
                    "type is written as-is."
                ),
            },
        ]

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "abt "

    def synopsis(self, query):
        return "abbreviation to look for"

    # -- note cache -------------------------------------------------------------------------

    def _forget(self) -> None:
        with self._lock:
            self._cache = None

    def _api_key(self) -> str:
        """The ETAPI token to send, running the configured command at most once.

        .. raises:: TriliumError
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

    def _load(self) -> Tuple[List[Tuple[str, str]], Dict[str, List[int]]]:
        with self._lock:
            cached = self._cache
        if cached is not None and time.monotonic() - cached[0] < NOTE_TTL:
            return cached[1], cached[2]

        token = self._api_key()
        note = fetch_note(self._url, token, self._note_id, self._verify_ssl)
        note_type = str(note.get("type") or "text")
        content = fetch_note_content(self._url, token, self._note_id, self._verify_ssl)
        text = html_to_text(content) if note_type == "text" else content

        entries = make_latest_entries(text.splitlines())
        index = make_search_index(entries)
        with self._lock:
            self._cache = (time.monotonic(), entries, index)

        return entries, index

    def _save(self, name: str, desc: str) -> None:
        try:
            token = self._api_key()
            note = fetch_note(self._url, token, self._note_id, self._verify_ssl)
            note_type = str(note.get("type") or "text")
            content = fetch_note_content(self._url, token, self._note_id, self._verify_ssl)
            line = abbreviation_line(name, desc)
            put_note_content(
                self._url,
                token,
                self._note_id,
                self._verify_ssl,
                append_abbreviation(content, note_type, line),
            )
            self._forget()
            notify(f'Saved "{name}" to the Trilium note.')
        except TriliumError as e:
            debug(traceback.format_exc())
            notify(str(e))
        except Exception:
            trace = traceback.format_exc()
            critical(trace)
            notify("Could not save the abbreviation - see the Albert logs.")

    # -- items --------------------------------------------------------------------------------

    def _setup_item(self) -> Optional[StandardItem]:
        if not self._url:
            return StandardItem(
                id=f"{self.id()}.setup-url",
                icon_factory=self.makeIcon,
                text="Please fill in the plugin settings - Trilium URL missing",
                subtext="Open the Abbreviations (Trilium) plugin in the Albert settings.",
                actions=[],
            )

        if not self._token and not self._token_command:
            return StandardItem(
                id=f"{self.id()}.setup-token",
                icon_factory=self.makeIcon,
                text="Please fill in the plugin settings - ETAPI token missing",
                subtext=(
                    "Create one in Trilium under Options > ETAPI, then paste it, or a "
                    "command that prints it, in the settings."
                ),
                actions=[],
            )

        if not self._note_id:
            return StandardItem(
                id=f"{self.id()}.setup-note",
                icon_factory=self.makeIcon,
                text="Please fill in the plugin settings - abbreviations note missing",
                subtext="Paste the note's URL or its last path segment (the note ID).",
                actions=[],
            )

        return None

    def _error_item(self, message: str) -> StandardItem:
        return StandardItem(
            id=f"{self.id()}.error",
            icon_factory=self.makeIcon,
            text=message,
            subtext="Check the Trilium URL, ETAPI token, note ID and SSL setting.",
            actions=[
                Action(
                    "copy",
                    "Copy the error",
                    lambda t=message: setClipboardText(t),
                )
            ],
        )

    def get_abbr_as_item(self, abbr: Tuple[str, str], suffix: str = "") -> StandardItem:
        """Return the abbreviation pair as an item ready for Albert.

        `suffix` keeps items with the same abbreviation and description apart.
        """
        text = abbr[0].strip()
        subtext = abbr[1].strip()

        return StandardItem(
            id=f"abbr-trilium-{text}-{suffix}" if suffix else f"abbr-trilium-{text}",
            icon_factory=self.makeIcon,
            text=f"{text}",
            subtext=f"{subtext}",
            actions=[
                Action(
                    "open",
                    "Open in Google",
                    lambda u=f"https://www.google.com/search?&q={text}": openUrl(u),
                ),
                Action("copy", "Copy abbreviation", lambda t=text: setClipboardText(t)),
                Action("copy", "Copy description", lambda t=subtext: setClipboardText(t)),
            ],
        )

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        """Called by albert with *every new keypress*."""
        try:
            setup = self._setup_item()
            if setup is not None:
                yield [setup]
                return

            query_str = ctx.query

            if len(query_str.strip().split()) == 0:
                yield [
                    StandardItem(
                        id=f"{self.id()}.hint-new",
                        icon_factory=self.makeIcon,
                        text="[new] Add a new abbreviation",
                        subtext="new <u>abbreviation</u> <u>description</u>",
                        input_action_text=f"{ctx.trigger} new ",
                    ),
                    StandardItem(
                        id=f"{self.id()}.hint-query",
                        icon_factory=self.makeIcon,
                        text="Write more to query the Trilium note",
                        subtext="",
                        input_action_text=ctx.trigger,
                    ),
                ]

                return

            tokens = query_str.split()
            if len(tokens) >= 1 and tokens[0] == "new":
                name = tokens[1] if len(tokens) > 1 else ""
                desc = " ".join(tokens[2:]) if len(tokens) > 2 else ""

                yield [
                    StandardItem(
                        id=f"{self.id()}.new-{name}",
                        icon_factory=self.makeIcon,
                        text=f"New abbreviation: {name}",
                        subtext=f"Description: {desc}",
                        actions=[
                            Action(
                                "save",
                                "Save abbreviation to Trilium",
                                lambda name=name, desc=desc: self._save(name, desc),
                            )
                        ],
                    )
                ]

                return

            entries, index = self._load()

            if not entries:
                yield [
                    StandardItem(
                        id=f"{self.id()}.no-entries",
                        icon_factory=self.makeIcon,
                        text=f'No lines split by "{DEFAULT_SEPARATOR}" in the Trilium note',
                        actions=[
                            Action(
                                "copy",
                                "Copy the note ID",
                                lambda t=self._note_id: setClipboardText(t),
                            )
                        ],
                    )
                ]

                return

            results = []
            seen = set()
            matched = process.extract(query_str, index.keys(), limit=10)
            for term in [elem[0] for elem in matched]:
                for i in index[term]:
                    if i in seen:
                        continue

                    seen.add(i)
                    results.append(self.get_abbr_as_item(entries[i], str(i)))

            yield results

        except TriliumError as e:
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
                    actions=[
                        Action(
                            "copy",
                            f"Copy error - report it to {md_url[8:]}",
                            lambda t=trace: setClipboardText(t),
                        )
                    ],
                )
            ]
