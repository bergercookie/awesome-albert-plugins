"""Pastebin - share a snippet as a link.

Dockge's counterpart on the wire is a socket.io conversation; this one is plain
HTTP. Every service is its own small adapter below, because they disagree about
almost everything: how the body is encoded, what the response looks like, and
whether an account is needed at all. Only pastebin.com needs a key, and even
that one is optional for the rest.

Nothing here talks to the network while you type. A query only produces a preview
item, and every upload happens inside an action, on a worker thread, so a slow or
hanging service cannot freeze the launcher.
"""

import json
import os
import re
import select
import stat
import sys
import threading
import traceback
from pathlib import Path
from typing import Dict, Iterator, List, NamedTuple, Optional, Tuple
from urllib.parse import urljoin

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
md_name = "Pastebin"
md_description = "Share a snippet or a file as a link, via pastebin.com or another service"
md_license = "MIT"
md_url = (
    "https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/pastebin"
)
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["requests"]
md_bin_dependencies: List[str] = []

ICON_DIR = Path(__file__).parent
ICON_PATH = ICON_DIR / "pastebin.svg"

CONFIG_BACKEND = "default_backend"
CONFIG_PASTEBIN_KEY = "pastebin_api_key"
CONFIG_AUTO_COPY = "auto_copy_link"
CONFIG_AUTO_OPEN = "open_in_browser"

# Nothing here should ever take longer than this. A service that is slower than
# this is down, not slow, and the user needs to hear about it now.
HTTP_TIMEOUT = 15
# Guard against a stray `pb ~` turning into a multi-gigabyte upload. Well above
# what any of these services accepts, so it only ever catches genuine mistakes.
MAX_BYTES = 8 * 1024 * 1024
# 0x0.st rejects requests without a user agent it recognises.
USER_AGENT = "awesome-albert-plugins/pastebin"

# `pb file:<path>` asks for a file explicitly. A single token that happens to be
# an existing file is accepted too, since that is what people type - the item
# always spells out which of the two it picked, and nothing uploads until an
# action is chosen, so a misdetection cannot leak anything anywhere.
FILE_PREFIX = "file:"

# Anchor we accept in a response body, so that we never hand back a full HTML
# error page as if it were a link.
URL_RE = re.compile(r"https?://[^\s<>\"']+")


# plugin main functions -----------------------------------------------------------------------


class PasteError(Exception):
    """A failure worth showing to the user as-is."""


class Input(NamedTuple):
    """What the user asked us to paste."""

    #: "text" or "file"
    kind: str
    #: the snippet itself, already read
    text: str
    #: a name to give the service, so it can pick a syntax - None for inline text
    filename: Optional[str]
    #: set instead of text when the input could not be used
    error: Optional[str] = None


def notify(title: str, msg: str) -> None:
    Notification(title, msg).send()


# supplementary functions ---------------------------------------------------------------------


def extract_url(body: str) -> Optional[str]:
    """Pull the paste URL out of a response body, or None if there isn't one.

    The keyless services answer with a bare URL, but some of them fall back to
    an HTML error page with a 2xx status, so a body that merely *contains* a URL
    is not good enough - the first thing in the body has to be the link.
    """
    if not body:
        return None

    body = body.strip()

    # dpaste's default format wraps the link in quotes
    if len(body) > 1 and body[0] == body[-1] and body[0] in "\"'":
        body = body[1:-1].strip()

    # ix.io answers with json when we ask nicely
    if body.startswith("{"):
        try:
            payload = json.loads(body)
        except ValueError:
            return None
        for key in ("url", "link", "key", "id"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                if value.startswith(("http://", "https://")):
                    return value
                # a bare key means "the service's root plus the key"
                base = payload.get("base_url")
                if base:
                    return urljoin(str(base).rstrip("/") + "/", value)
        return None

    # a bare link, on its own, and nothing else
    if "://" in body and not any(ch in body for ch in ("<", ">")):
        return body.split()[0]

    return None


def read_snippet(path: str) -> Tuple[str, Optional[str]]:
    """Read *path* as text.

    Returns the text and the name to hand the service.

    .. raises:: PasteError
    """
    try:
        expanded = Path(os.path.expanduser(path.strip()))
        size = expanded.stat().st_size
    except OSError as e:
        raise PasteError(f"Cannot read {path}: {e.strerror or e}") from e

    if size > MAX_BYTES:
        raise PasteError(
            f"{path} is {size} bytes, which is over the {MAX_BYTES} byte limit. "
            "Split it up, or upload it somewhere meant for files."
        )

    try:
        text = expanded.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise PasteError(
            f"{path} is not UTF-8 text. These services only take text - try "
            "0x0.st for binary."
        ) from e
    except OSError as e:
        raise PasteError(f"Cannot read {path}: {e.strerror or e}") from e

    return text, expanded.name


def stdin_snippet() -> Optional[str]:
    """The piped-in snippet, if there is one ready.

    `albert pb < notes.txt` reaches us with a pipe instead of a terminal.

    This is called on every keystroke while the query is being edited, so it must
    never wait for more input: a pipe that stays open but idle (a terminal
    launcher that hands us its stdin, say) would otherwise freeze the query
    thread forever. `select` with a zero timeout reads only what is already
    there, and a regular file - which is what a shell redirect actually gives us
    - is always ready and always returns at once.
    """
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return None

        fd = sys.stdin.fileno()
        if not stat.S_ISREG(os.fstat(fd).st_mode) and not select.select([fd], [], [], 0)[0]:
            return None

        # drain only what is ready, so a slow writer cannot make us block either
        chunks = []
        size = 0
        while size < MAX_BYTES:
            if not select.select([fd], [], [], 0)[0]:
                break
            chunk = os.read(fd, min(65536, MAX_BYTES - size + 1))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
    except (OSError, ValueError):
        return None

    if not chunks:
        return None

    if size > MAX_BYTES:
        # truncated pastes would be uploaded as if they were the whole thing
        raise PasteError(
            f"The piped input is over the {MAX_BYTES} byte limit. Split it up, "
            "or upload it somewhere meant for files."
        )

    try:
        piped = b"".join(chunks).decode("utf-8")
    except UnicodeDecodeError:
        return None

    return piped if piped.strip() else None


# backends ------------------------------------------------------------------------------------


class Backend(NamedTuple):
    """One paste service."""

    id: str
    label: str
    url: str
    #: True when the service will not accept a paste without a key
    needs_key: bool
    #: a sentence about the service, shown under the item
    note: str


def _post(
    backend: Backend,
    *,
    data=None,
    files=None,
    headers=None,
    api_key: str = "",
) -> str:
    """POST to *backend* and hand back the body.

    .. raises:: PasteError
    """
    all_headers = {"User-Agent": USER_AGENT}
    if headers:
        all_headers.update(headers)

    try:
        response = requests.post(
            backend.url,
            data=data,
            files=files,
            headers=all_headers,
            timeout=HTTP_TIMEOUT,
        )
    except requests.Timeout as e:
        raise PasteError(
            f"{backend.label} did not answer within {HTTP_TIMEOUT}s."
        ) from e
    except requests.RequestException as e:
        raise PasteError(f"Cannot reach {backend.label}: {e}") from e

    body = str(response.text or "")

    if response.status_code >= 400:
        detail = body.strip().replace("\n", " ")
        raise PasteError(
            f"{backend.label} refused the paste (HTTP {response.status_code})"
            + (f": {detail[:200]}" if detail else ".")
        )

    return body


def _paste_termbin(backend: Backend, text: str, filename: Optional[str], api_key: str) -> str:
    """termbin.com takes the raw body and answers with the link.

    It keeps everything for a week and needs no account. fiche, the software
    behind it, answers with an HTML page when the body is not text it likes, so
    the result is checked rather than assumed.
    """
    body = _post(backend, data=text.encode("utf-8"), headers={"Content-Type": "text/plain"})

    url = extract_url(body)
    if not url:
        raise PasteError(
            f"{backend.label} did not return a link. It may have rejected the "
            "content - termbin only accepts text."
        )
    return url


def _paste_dpaste(backend: Backend, text: str, filename: Optional[str], api_key: str) -> str:
    """dpaste.org takes a form post and, with format=url, answers with the link.

    `filename` is passed through so dpaste can pick a syntax for highlighting.
    """
    data = {"content": text, "format": "url"}
    if filename:
        data["filename"] = filename

    body = _post(backend, data=data)

    url = extract_url(body)
    if not url:
        raise PasteError(f"{backend.label} did not return a link.")
    return url


def _paste_0x0(backend: Backend, text: str, filename: Optional[str], api_key: str) -> str:
    """0x0.st takes a multipart upload and answers with the link.

    The odd field name is the service's, not a typo: its API wants `file`.
    """
    body = _post(backend, files={"file": (filename or "snippet.txt", text, "text/plain")})

    url = extract_url(body)
    if not url:
        raise PasteError(f"{backend.label} did not return a link.")
    return url


def _paste_ix(backend: Backend, text: str, filename: Optional[str], api_key: str) -> str:
    """ix.io wants the content in a multipart field called `f:1`."""
    body = _post(
        backend,
        files={"f:1": (filename or "snippet.txt", text, "text/plain")},
        headers={"Accept": "application/json"},
    )

    url = extract_url(body)
    if not url:
        raise PasteError(f"{backend.label} did not return a link.")
    return url


def _paste_pastebin(backend: Backend, text: str, filename: Optional[str], api_key: str) -> str:
    """pastebin.com, which is the only one of these that needs a developer key.

    The key is a paid subscription, and without one the API answers with an error
    rather than an empty result, so it is checked here rather than after the fact.
    """
    if not api_key:
        raise PasteError(
            "pastebin.com needs a Developer API key. Add it in the plugin settings, "
            "or use one of the services that needs no key."
        )

    data = {
        "api_dev_key": api_key,
        "api_option": "paste",
        "api_paste_code": text,
    }
    if filename:
        # the paste title, which is the only name pastebin.com takes
        data["api_paste_name"] = filename

    body = _post(backend, data=data)

    try:
        payload = json.loads(body)
    except ValueError as e:
        raise PasteError(f"{backend.label} did not return a link.") from e

    if not isinstance(payload, dict):
        raise PasteError(f"{backend.label} did not return a link.")

    if payload.get("error"):
        raise PasteError(f"{backend.label}: {payload.get('message') or payload['error']}")

    # api_paste_url would hand us the finished link, but building it from the key
    # keeps working if that flag is ever dropped from the response
    if isinstance(payload.get("url"), str) and payload["url"]:
        return str(payload["url"])
    key = payload.get("key")
    if isinstance(key, str) and key:
        return urljoin("https://pastebin.com/", key)

    raise PasteError(f"{backend.label} did not return a link.")


TERMBIN = Backend(
    id="termbin",
    label="termbin.com",
    url="https://termbin.com",
    needs_key=False,
    note="No account. Deleted after a week.",
)
DPASTE = Backend(
    id="dpaste",
    label="dpaste.org",
    url="https://dpaste.org/api/",
    needs_key=False,
    note="No account. Syntax highlighting, picks it from the file name.",
)
ZEROX0 = Backend(
    id="0x0.st",
    label="0x0.st",
    url="https://0x0.st",
    needs_key=False,
    note="No account. Takes the largest pastes of the bunch.",
)
IXIO = Backend(
    id="ix.io",
    label="ix.io",
    url="https://ix.io",
    needs_key=False,
    note="No account. The smallest service here.",
)
PASTEBIN = Backend(
    id="pastebin.com",
    label="pastebin.com",
    url="https://pastebin.com/api/api_post.php",
    needs_key=True,
    note="Needs a Developer API key. The only service here with a paid key.",
)

#: Every service, in the order they are offered.
BACKENDS: Dict[str, Backend] = {
    b.id: b
    for b in (TERMBIN, DPASTE, ZEROX0, IXIO, PASTEBIN)
}

#: The combobox stores the label, so this is how a stored value finds its backend.
BACKENDS_BY_LABEL: Dict[str, Backend] = {b.label: b for b in BACKENDS.values()}


def paste(
    backend: Backend, text: str, filename: Optional[str] = None, api_key: str = ""
) -> str:
    """Upload *text* to *backend* and return the link to it.

    .. raises:: PasteError
    """
    if not text.strip():
        raise PasteError("There is nothing to paste.")

    handler = {
        TERMBIN.id: _paste_termbin,
        DPASTE.id: _paste_dpaste,
        ZEROX0.id: _paste_0x0,
        IXIO.id: _paste_ix,
        PASTEBIN.id: _paste_pastebin,
    }[backend.id]

    return handler(backend, text, filename, api_key)


# main plugin class --------------------------------------------------------------------------


class Plugin(PluginInstance, GeneratorQueryHandler):
    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)

        self.cache_path = Path(self.cacheLocation())
        self.config_path = Path(self.configLocation())
        self.data_path = Path(self.dataLocation())
        for p in (self.cache_path, self.config_path, self.data_path):
            p.mkdir(parents=True, exist_ok=True)

        stored = (self.readConfig(CONFIG_BACKEND, str) or "").strip()
        # a stored label that no longer names a service falls back to the default
        self._default_backend: Backend = BACKENDS_BY_LABEL.get(stored, TERMBIN)
        # readConfig is untyped in the stub and hands back whatever was stored,
        # so a hand-edited config value can be anything
        self._pastebin_key: str = str(self.readConfig(CONFIG_PASTEBIN_KEY, str) or "").strip()
        self._auto_copy: bool = bool(self.readConfig(CONFIG_AUTO_COPY, bool))
        self._auto_open: bool = bool(self.readConfig(CONFIG_AUTO_OPEN, bool))

    # -- config, bound to the settings widget below ---------------------------------------

    @property
    def default_backend(self) -> str:
        return self._default_backend.label

    @default_backend.setter
    def default_backend(self, value: str):
        backend = BACKENDS_BY_LABEL.get((value or "").strip(), TERMBIN)
        self._default_backend = backend
        self.writeConfig(CONFIG_BACKEND, backend.label)

    @property
    def pastebin_api_key(self) -> str:
        return self._pastebin_key

    @pastebin_api_key.setter
    def pastebin_api_key(self, value: str):
        self._pastebin_key = (value or "").strip()
        self.writeConfig(CONFIG_PASTEBIN_KEY, self._pastebin_key)

    @property
    def auto_copy_link(self) -> bool:
        return self._auto_copy

    @auto_copy_link.setter
    def auto_copy_link(self, value: bool):
        self._auto_copy = bool(value)
        self.writeConfig(CONFIG_AUTO_COPY, self._auto_copy)

    @property
    def open_in_browser(self) -> bool:
        return self._auto_open

    @open_in_browser.setter
    def open_in_browser(self, value: bool):
        self._auto_open = bool(value)
        self.writeConfig(CONFIG_AUTO_OPEN, self._auto_open)

    def configWidget(self):
        return [
            {
                "type": "label",
                "text": (
                    "Termbin, dpaste, 0x0.st and ix.io need no account and no key. "
                    "pastebin.com is the exception: it only accepts pastes from a "
                    "paid Developer API key, which you can add below."
                ),
            },
            {
                "type": "combobox",
                "property": "default_backend",
                "label": "Default service",
                "items": [b.label for b in BACKENDS.values()],
                "widget_properties": {"editable": False},
            },
            {
                "type": "lineedit",
                "property": "pastebin_api_key",
                "label": "pastebin.com Developer API key",
                "widget_properties": {
                    "echoMode": 2,
                    "placeholderText": "only needed for pastebin.com",
                },
            },
            {
                "type": "label",
                "text": "What should happen once the paste is up?",
            },
            {
                "type": "checkbox",
                "property": "auto_copy_link",
                "label": "Copy the link to the clipboard",
            },
            {
                "type": "checkbox",
                "property": "open_in_browser",
                "label": "Open the link in the browser",
            },
        ]

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "pb "

    def synopsis(self, query):
        return "a snippet, or file:<path>"

    # -- input --------------------------------------------------------------------------------

    @staticmethod
    def parse_input(query: str) -> Input:
        """Work out what the user wants to paste.

        The order matters: a pipe wins over the query, because
        `albert pb < notes.txt` is asking for the file, not for the text
        "notes.txt".
        """
        piped = None
        try:
            piped = stdin_snippet()
        except PasteError as e:
            return Input("text", "", None, str(e))
        if piped is not None:
            return Input("text", piped, None)

        query = query.strip()
        if not query:
            return Input("text", "", None)

        if query.startswith(FILE_PREFIX):
            return Plugin._input_from_path(query[len(FILE_PREFIX) :])

        # a bare single token that is an existing file
        if " " not in query:
            path = os.path.expanduser(query)
            if os.path.isfile(path):
                return Plugin._input_from_path(query)

        return Input("text", query, None)

    @staticmethod
    def _input_from_path(path: str) -> Input:
        if not path.strip():
            return Input("file", "", None, "No file given after 'file:'.")
        try:
            text, name = read_snippet(path)
        except PasteError as e:
            return Input("file", "", None, str(e))
        return Input("file", text, name)

    # -- items --------------------------------------------------------------------------------

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        results: List[StandardItem] = []

        try:
            if not ctx.query.strip():
                yield [self._help_item()]
                return

            parsed = self.parse_input(ctx.query)

            if parsed.error:
                yield [
                    StandardItem(
                        id=f"{self.id()}.error",
                        icon_factory=self.makeIcon,
                        text=parsed.error,
                        subtext="Press [ENTER] to copy the error.",
                        actions=[
                            Action(
                                "copy",
                                "Copy error",
                                lambda e=parsed.error: setClipboardText(e),
                            ),
                        ],
                    )
                ]
                return

            if not parsed.text.strip():
                yield [self._help_item()]
                return

            results = self._paste_actions(parsed)
            yield results

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

    def _help_item(self) -> StandardItem:
        return StandardItem(
            id=f"{self.id()}.help",
            icon_factory=self.makeIcon,
            text="Paste a snippet to get a link",
            subtext=(
                f"pb <text> or pb file:<path> - default service: {self._default_backend.label}"
            ),
            input_action_text="",
            actions=[
                Action("readme", "How this works", lambda: openUrl(md_url)),
            ],
        )

    def _paste_actions(self, parsed: Input) -> List[StandardItem]:
        """One item offering every service as an action.

        The configured default goes first, because the first action is what
        ENTER runs.
        """
        source = f"file: {parsed.filename}" if parsed.kind == "file" else "text"

        # the default first, then the rest in their natural order
        ordered = [self._default_backend] + [
            b for b in BACKENDS.values() if b.id != self._default_backend.id
        ]
        actions = [
            Action(
                backend.id,
                f"Paste to {backend.label}",
                lambda b=backend, p=parsed: self._paste_async(b, p),
            )
            for backend in ordered
        ]

        return [
            StandardItem(
                id=f"{self.id()}.paste",
                icon_factory=self.makeIcon,
                text=f"Paste {self._preview(parsed.text)}",
                subtext=(
                    f"{source} - {len(parsed.text)} bytes - "
                    f"default: {self._default_backend.label}"
                ),
                input_action_text=(
                    f"{self.defaultTrigger()}{parsed.text}" if parsed.kind == "text" else None
                ),
                actions=actions,
            )
        ]

    @staticmethod
    def _preview(text: str) -> str:
        """A one-line, length-capped look at the snippet."""
        lines = [line for line in text.strip().splitlines() if line.strip()]
        head = " ".join(lines[0].split()) if lines else ""
        if len(head) > 60:
            head = head[:57] + "..."
        if len(lines) > 1:
            return f"({len(lines)} lines) {head}"
        return head

    # -- the upload itself --------------------------------------------------------------------

    def _paste_async(self, backend: Backend, parsed: Input) -> None:
        """Upload on a worker thread, so a slow service cannot freeze albert."""
        threading.Thread(
            target=self._paste_worker,
            args=(backend, parsed),
            name="pastebin-paste",
            daemon=True,
        ).start()

    def _paste_worker(self, backend: Backend, parsed: Input) -> None:
        try:
            url = paste(
                backend,
                parsed.text,
                filename=parsed.filename,
                api_key=self._pastebin_key,
            )
        except PasteError as e:
            debug(traceback.format_exc())
            notify(f"{backend.label} - failed", str(e))
            return
        except Exception:
            trace = traceback.format_exc()
            critical(trace)
            notify(
                f"{backend.label} - failed",
                trace.strip().splitlines()[-1] if trace.strip() else "unknown error",
            )
            return

        # captured here, not in a closure over the exception, so the actions below
        # never read a traceback that is already gone
        note = []
        if self._auto_copy:
            setClipboardText(url)
            note.append("copied to the clipboard")
        if self._auto_open:
            openUrl(url)
            note.append("opened in the browser")

        suffix = f" - {', '.join(note)}" if note else ""
        notify(backend.label, f"{url}{suffix}")
