"""Dockge - control the docker stacks of a running Dockge server."""

import queue
import shutil
import subprocess
import threading
import time
import traceback
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Iterator, List, NamedTuple, Optional, Sequence, Tuple
from urllib.parse import quote, urljoin

import socketio
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
md_name = "Dockge"
md_description = "Control the docker stacks of a running Dockge server"
md_license = "MIT"
md_url = (
    "https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/dockge"
)
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["python-socketio"]
md_bin_dependencies: List[str] = []

ICON_DIR = Path(__file__).parent
ICON_PATH = ICON_DIR / "dockge.svg"

CONFIG_URL = "server_url"
CONFIG_USERNAME = "username"
CONFIG_PASSWORD = "password"
CONFIG_RBW_ENTRY = "password_rbw_entry"

# dockge has no REST API - the whole protocol is a socket.io conversation, so
# every timeout below is really "how long to wait for the next ack/event".
CONNECT_TIMEOUT = 10
LOGIN_TIMEOUT = 10
CALL_TIMEOUT = 20
STACKLIST_TIMEOUT = 10
# Grace period for dockge's `autoLogin`, which it pushes on connect when it runs
# without authentication - in that case it never acknowledges a login as ok.
DISABLED_AUTH_TIMEOUT = 2
# dockge re-pushes the stack list every 10s on its own; poll at the same rate.
# This doubles as the delay before a reconnect after a failure.
REFRESH_INTERVAL = 10
# How long a query is willing to block waiting for the very first answer. Once
# the poller has something, queries never block.
FIRST_RESULT_TIMEOUT = 3
RBW_TIMEOUT = 30

# The endpoint dockge itself runs its docker commands on. Remote dockge agents
# are not managed from here - upstream only proxies a request to them when it
# is addressed to a named agent, so "" (the local one) is the only address that
# means "the dockge I'm talking to".
LOCAL_ENDPOINT = ""

# start/stop/restart/update as dockge names them on the wire.
CONTROL_EVENTS = {
    "start": "startStack",
    "stop": "stopStack",
    "restart": "restartStack",
    "update": "updateStack",
}

# Stack.status, as of dockge's common/util-common.ts.
# Stack status, as of dockge's common/util-common.ts: UNKNOWN, CREATED_FILE,
# CREATED_STACK, RUNNING, EXITED - and statusName(), which calls 1 "draft" and
# 2 "created_stack".
STACK_STATUS_STATES = {
    0: "unknown",
    1: "draft",
    2: "created_stack",
    3: "running",
    4: "exited",
}

# Container state (or health check status, which dockge prefers when it has one)
# -> the icon file standing for it.
STATE_ICONS = {
    "running": "dockge-running.svg",
    "healthy": "dockge-running.svg",
    "restarting": "dockge-restarting.svg",
    "starting": "dockge-restarting.svg",
    "paused": "dockge-restarting.svg",
    "unhealthy": "dockge-error.svg",
    "dead": "dockge-error.svg",
    "removing": "dockge-error.svg",
    "exited": "dockge-stopped.svg",
    "created": "dockge-stopped.svg",
    "created_stack": "dockge-stopped.svg",
    "draft": "dockge-stopped.svg",
    "unknown": "dockge-unknown.svg",
}

# Most informative first: the first state found among a stack's containers is
# the one shown as *its* state.
STATE_PRIORITY = (
    "restarting",
    "dead",
    "removing",
    "unhealthy",
    "paused",
    "starting",
    "running",
    "exited",
    "created",
)

# Health check results that say nothing about whether the container is up.
STATE_NOISE = {"none", ""}


# plugin main functions -----------------------------------------------------------------------


class DockgeError(Exception):
    """A failure worth showing to the user as-is."""


class Settings(NamedTuple):
    """Everything needed to (re)connect to a dockge server."""

    url: str
    username: str
    password: str
    rbw_entry: str


class Snapshot(NamedTuple):
    """An immutable view of the last successful poll."""

    stacks: Dict[str, Dict]
    services: Dict[str, Dict[str, List[str]]]
    error: Optional[str]


def notify(msg: str, app_name: str = md_name) -> None:
    Notification(app_name, msg).send()


# supplementary functions ---------------------------------------------------------------------


def resolve_password(password: str, rbw_entry: str) -> str:
    """Return the dockge password.

    A bitwarden entry name wins over the plaintext password, so that the latter
    can be left empty in Albert's config.

    .. raises:: DockgeError
    """
    entry = (rbw_entry or "").strip()
    if not entry:
        return (password or "").strip()

    if shutil.which("rbw") is None:
        raise DockgeError(
            f'"{entry}" is set as the password source but the rbw command is not installed.'
        )

    try:
        proc = subprocess.run(
            ["rbw", "get", entry],
            capture_output=True,
            check=False,
            timeout=RBW_TIMEOUT,
        )
    except subprocess.TimeoutExpired as e:
        raise DockgeError(
            f'"rbw get {entry}" took longer than {RBW_TIMEOUT}s to answer.'
        ) from e

    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", "replace").strip()
        raise DockgeError(f'"rbw get {entry}" failed: {stderr}')

    return proc.stdout.decode("utf-8", "replace").strip()


def stack_url(base_url: str, name: str, endpoint: str = "") -> str:
    """Deep link to *name*'s compose page in dockge's web UI.

    A stack that belongs to a *remote* dockge agent needs the agent's endpoint in
    the path. dockge's frontend has two routes for this (frontend/src/router.ts):

        /compose/:stackName
        /compose/:stackName/:endpoint

    and the agent route has to come first. Without the endpoint, a stack served
    by another agent resolves against the local one and you land on a page for a
    stack that does not exist here. The endpoint rides along on every stack in
    the `stackList` push: Stack.toSimpleJSON() (backend/stack.ts) puts it in
    every entry, and emitAgent() stamps it on as well. For a stack served by the
    dockge we are talking to it is the empty string, hence the short route.

    >>> stack_url("http://localhost:5001", "media")
    'http://localhost:5001/compose/media'
    >>> stack_url("http://localhost:5001", "my stack")
    'http://localhost:5001/compose/my%20stack'
    >>> stack_url("https://host/dockge", "baikal", "agent.example.com")
    'https://host/dockge/compose/baikal/agent.example.com'
    """
    path = f"compose/{quote(name, safe='')}"
    if endpoint:
        path += f"/{quote(endpoint, safe='')}"
    return urljoin(base_url.rstrip("/") + "/", path)


def endpoint_of(stack: Dict) -> str:
    """The dockge agent serving *stack*, or "" when it is the local one."""
    value = stack.get("endpoint")
    return value.strip() if isinstance(value, str) else ""


# -- searching ------------------------------------------------------------------------------


def fuzzy_score(needle: str, haystack: str) -> float:
    """How well *needle* matches *haystack*, 0.0 when it does not match at all.

    A plain subsequence test plus a similarity ratio, so both `baikal` and
    `bkl` find `baikal`, and a typo still finds its stack instead of the list
    going blank. Deliberately not `difflib.get_close_matches` on its own: that
    insists on roughly the same length in both strings, so typing the first two
    letters of a long stack name would match nothing.

    >>> fuzzy_score("bai", "baikal") > 0.9
    True
    >>> fuzzy_score("bkl", "baikal") > 0      # skipped letters still match
    True
    >>> fuzzy_score("baikal", "nginx")        # nothing in common
    0.0
    """
    needle = needle.strip().lower()
    haystack = haystack.strip().lower()
    if not needle:
        return 1.0
    if not haystack:
        return 0.0

    if needle == haystack:
        return 1.0
    if haystack.startswith(needle):
        return 0.95

    if needle in haystack:
        # a hit that starts early is a better hit
        return 0.85 - 0.15 * (haystack.index(needle) / max(len(haystack), 1))

    # every character of the needle present, in order: `bkl` -> `baikal`
    it = iter(haystack)
    if not all(char in it for char in needle):
        # last resort, so a typo narrows the list instead of emptying it
        ratio = SequenceMatcher(None, needle, haystack).ratio()
        return ratio * 0.7 if ratio >= 0.6 else 0.0

    # reward tight, early subsequences over scattered ones
    positions = [haystack.index(char) for char in needle]
    span = positions[-1] - positions[0] + 1
    return 0.6 + 0.25 * (len(needle) / span)


def search_stacks(stacks: Dict[str, Dict], term: str) -> List[str]:
    """Stack names matching *term*, best first.

    The endpoint is searched as well as the name, so `xf85` finds the stacks that
    a given remote agent is serving.
    """
    term = term.strip()
    if not term:
        return sorted(stacks)

    scored: List[Tuple[float, str]] = []
    for name, stack in stacks.items():
        # a name match always beats an endpoint match
        best = max(
            fuzzy_score(term, name),
            fuzzy_score(term, endpoint_of(stack)) * 0.9 if endpoint_of(stack) else 0.0,
        )
        if best > 0.0:
            scored.append((best, name))

    # name, so that equally good matches stay in a stable, predictable order
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [name for _, name in scored]


def state_of(name: str, stack: Dict, services: Dict[str, Dict[str, List[str]]]) -> str:
    """The state to show for stack *name*.

    The containers know better than dockge's own summary, so they win; dockge's
    status is the fallback for a stack that isn't deployed (or doesn't answer).
    """
    stack_services: Dict[str, List[str]] = services.get(name, {})
    containers = [
        state.lower()
        for states in stack_services.values()
        for state in states
        if state and state.lower() not in STATE_NOISE
    ]
    for candidate in STATE_PRIORITY:
        if candidate in containers:
            return candidate

    return STACK_STATUS_STATES.get(int(stack.get("status", 0)), "unknown")


def summarize(states: Sequence[str]) -> str:
    """One-line summary of the container *states* of a single service."""
    counts = Counter(state.upper() for state in states)
    return ", ".join(
        state if count == 1 else f"{count}x {state}" for state, count in sorted(counts.items())
    )


# main plugin class --------------------------------------------------------------------------


class DockgeClient:
    """Keeps one live socket.io connection to a dockge server.

    Dockge speaks socket.io exclusively, and answering a query over a websocket
    is far too slow to do on every keypress. So all of the talking happens on a
    single daemon thread which keeps a snapshot up to date, and both the query
    handler and the action callbacks only read from (or queue onto) that thread.
    """

    def __init__(self) -> None:
        # guards the snapshot below, so readers never see a half-updated one
        self._lock = threading.Lock()
        self._stacks: Dict[str, Dict] = {}
        self._services: Dict[str, Dict[str, List[str]]] = {}
        self._error: Optional[str] = None
        self._generation = 0

        self._stacklist_arrived = threading.Event()
        self._auto_login = threading.Event()
        self._settled = threading.Event()
        self._stop: Optional[threading.Event] = None
        self._thread: Optional[threading.Thread] = None
        self._settings: Optional[Settings] = None

        self._tasks: queue.Queue = queue.Queue()

    # -- public API ---------------------------------------------------------------------

    def start(self, settings: Settings) -> None:
        """Poll *settings* in the background, replacing the poller if it changed."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                if self._settings == settings:
                    return
                self._stop_poller()

            self._settings = settings
            self._stop = threading.Event()
            self._thread = threading.Thread(
                target=self._run,
                args=(settings, self._stop),
                name="dockge-poller",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """Shut the poller down and drop the cached stacks."""
        with self._lock:
            self._stop_poller()
            self._settings = None
            self._stacks = {}
            self._services = {}
            self._error = None
            self._generation += 1

        self._stacklist_arrived.set()
        self._settled.clear()

    def control(self, name: str, action: str) -> None:
        """Queue start/stop/restart/update for *name*, or a `refresh` of the list."""
        self._tasks.put((action, name))

    def snapshot(self, timeout: float = 0.0) -> Snapshot:
        """Return the last poll, waiting up to *timeout* for the very first one."""
        if timeout:
            self._settled.wait(timeout)

        with self._lock:
            return Snapshot(dict(self._stacks), self._services, self._error)

    # -- lifecycle ----------------------------------------------------------------------

    def _stop_poller(self) -> None:
        """Ask the poller to finish. Its socket is cleaned up by the thread itself."""
        if self._stop is not None:
            self._stop.set()
        self._thread = None

    def _run(self, settings: Settings, stop: threading.Event) -> None:
        sio = None
        try:
            while not stop.is_set():
                try:
                    if sio is None:
                        sio = self._connect(settings)
                    self._poll(sio)
                except Exception:
                    trace = traceback.format_exc()
                    debug(trace)
                    self._set_error(_friendly_error(settings, trace))
                    sio = self._disconnect(sio)
                finally:
                    # a query has something to show from here on - error or not
                    self._settled.set()

                self._run_next_task(sio, stop)
        finally:
            self._disconnect(sio)

    def _set_error(self, message: Optional[str]) -> None:
        with self._lock:
            self._error = message

    # -- the socket.io conversation ------------------------------------------------------

    def _on_agent_push(self, event: str, *args) -> None:
        """Handle everything dockge pushes.

        Dockge does not push its events under their own names. `emitAgent()`
        (backend/dockge-server.ts) re-wraps every push as

            socket.emit("agent", event, ...args)

        so a `stackList` push actually arrives as the event named ``agent`` with
        ``"stackList"`` as its first argument. Dockge's own frontend does exactly
        this in frontend/src/mixins/socket.ts:

            socket.on("agent", (eventName, ...args) => agentSocket.call(eventName, ...args))

        Listening for a top-level "stackList" event therefore never fires, and
        the plugin stays permanently empty.
        """
        if event == "stackList":
            self._on_stacklist(args[0] if args else {})
        elif event == "autoLogin":
            self._on_auto_login(*args)
        else:
            debug(f"ignoring dockge push {event!r}")

    def _on_stacklist(self, data: Dict) -> None:
        """Handle dockge's `stackList` push - the only way the stack list arrives."""
        if not isinstance(data, dict):
            debug(f"ignoring malformed stackList push: {data!r}")
            return

        stacks = {
            str(name): dict(stack)
            for name, stack in (data.get("stackList") or {}).items()
            if isinstance(stack, dict)
        }
        if not data.get("ok", True):
            # dockge pushes stackList with ok:false when it could not build the list
            debug(f"stackList push reported failure: {data.get('msg')!r}")
            return

        with self._lock:
            self._stacks = stacks
            self._error = None
            self._generation += 1

        self._stacklist_arrived.set()

    def _on_auto_login(self, *args) -> None:
        """Handle dockge's `autoLogin` push, sent when it runs without authentication."""
        debug("dockge has authentication disabled")
        self._auto_login.set()

    def _connect(self, settings: Settings) -> socketio.Client:
        sio = socketio.Client(reconnection=False)
        self._auto_login.clear()
        # dockge wraps every push in an "agent" event; see _on_agent_push
        sio.on("agent", self._on_agent_push)
        sio.connect(settings.url, wait_timeout=CONNECT_TIMEOUT)
        debug(f"connected to {settings.url}")

        try:
            self._login(sio, settings)
        except Exception:
            self._disconnect(sio)
            raise

        return sio

    def _login(self, sio: socketio.Client, settings: Settings) -> None:
        password = resolve_password(settings.password, settings.rbw_entry)

        ack = self._call(
            sio,
            "login",
            {"username": settings.username, "password": password},
            LOGIN_TIMEOUT,
        )

        if isinstance(ack, dict) and ack.get("ok"):
            return

        # dockge can run with authentication disabled. It never accepts a login in
        # that case - it logs us in on connect instead and pushes the stack list.
        if self._auto_login.wait(DISABLED_AUTH_TIMEOUT):
            return

        msg = ack.get("msg", "no reason given") if isinstance(ack, dict) else ack
        raise DockgeError(
            f"{settings.url} refused the login ({msg}). If dockge has authentication "
            "enabled, check the username and the password in the plugin settings."
        )

    def _poll(self, sio: socketio.Client) -> None:
        """Ask for the current stacks and the state of each of their containers."""
        with self._lock:
            names = sorted(self._stacks)
            before = self._generation

        try:
            self._call(sio, "agent", (LOCAL_ENDPOINT, "requestStackList"), CALL_TIMEOUT)
        except socketio.exceptions.SocketIOError:
            # the periodic push keeps the list fresh anyway
            pass

        self._await_stacklist(after=before, timeout=STACKLIST_TIMEOUT)
        self._poll_services(sio, names)

    def _poll_services(
        self, sio: socketio.Client, names: Sequence[str]
    ) -> Dict[str, Dict[str, List[str]]]:
        """Container state per service per stack, for the *names* given."""
        services: Dict[str, Dict[str, List[str]]] = {}

        for name in names:
            try:
                ack = self._call(
                    sio, "agent", (LOCAL_ENDPOINT, "serviceStatusList", name), CALL_TIMEOUT
                )
            except socketio.exceptions.SocketIOError as e:
                debug(f"no container status for {name}: {e}")
                continue

            if not isinstance(ack, dict) or not ack.get("ok"):
                continue

            services[name] = {
                str(service): [
                    str(container.get("status", "unknown"))
                    for container in containers
                    if isinstance(container, dict)
                ]
                for service, containers in (ack.get("serviceStatusList") or {}).items()
                if isinstance(containers, list)
            }

        with self._lock:
            self._services = services

        return services

    def _run_next_task(self, sio: socketio.Client, stop: threading.Event) -> None:
        """Run one queued control action, waiting up to REFRESH_INTERVAL for one."""
        deadline = time.monotonic() + REFRESH_INTERVAL
        while not stop.is_set():
            try:
                action, name = self._tasks.get(timeout=0.5)
            except queue.Empty:
                if time.monotonic() >= deadline:
                    return
                continue

            if sio is not None and action != "refresh":
                self._control(sio, name, action)
                # dockge pushes a fresh stack list after every control action, but
                # poll right away so the new state shows up without a 10s wait
                try:
                    self._poll(sio)
                except Exception:
                    debug(traceback.format_exc())
            return

    def _control(self, sio: socketio.Client, name: str, action: str) -> None:
        try:
            ack = self._call(
                sio, "agent", (LOCAL_ENDPOINT, CONTROL_EVENTS[action], name), CALL_TIMEOUT
            )
        except Exception as e:
            notify(f"{name}: could not {action} it - {e}", "Dockge")
            return

        if isinstance(ack, dict) and ack.get("ok"):
            notify(f"{name}: {ack.get('msg', action)}")
        else:
            msg = ack.get("msg", "unknown error") if isinstance(ack, dict) else ack
            notify(f"{name}: {action} failed - {msg}", "Dockge")

    @staticmethod
    def _call(sio: socketio.Client, event: str, data, timeout: float):
        """Emit *event* and block until dockge acknowledges it."""
        return sio.call(event, data=data, timeout=timeout)

    def _await_stacklist(self, *, after: int, timeout: float) -> bool:
        """Wait for a `stackList` push newer than generation *after*."""
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                if self._generation > after:
                    return True

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False

            self._stacklist_arrived.wait(min(remaining, 0.5))
            self._stacklist_arrived.clear()

    @staticmethod
    def _disconnect(sio: Optional[socketio.Client]) -> Optional[socketio.Client]:
        """Close the connection without waiting for it.

        `socketio.Client.disconnect()` joins the read loop, and that read loop is
        parked in a long poll GET which only returns once dockge pings - a full
        ping interval (25s by default) per reconnect. We hold nothing on the
        client once we are done with it, so close the engine.io connection
        instead: it sends the CLOSE packet and skips the join. The read loop is a
        daemon thread, so it simply expires.
        """
        if sio is not None:
            try:
                sio.eio.disconnect(abort=True)
            except Exception:
                debug(traceback.format_exc())
        return None


def _friendly_error(settings: Settings, trace: str) -> str:
    """Turn the last line of a traceback into something worth showing in the UI."""
    message = [li for li in trace.strip().splitlines() if li.strip()][-1].split(": ", 1)[-1]
    return message if settings.url in message else f"{settings.url}: {message}"


class Plugin(PluginInstance, GeneratorQueryHandler):
    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)

        self.cache_path = Path(self.cacheLocation())
        self.config_path = Path(self.configLocation())
        self.data_path = Path(self.dataLocation())
        for p in (self.cache_path, self.config_path, self.data_path):
            p.mkdir(parents=True, exist_ok=True)

        # readConfig is untyped in the stub, hence the explicit str() here and on
        # the properties below: it returns whatever was stored, and a config
        # value edited by hand can be anything.
        self._url: str = str(self.readConfig(CONFIG_URL, str) or "").strip()
        self._username: str = str(self.readConfig(CONFIG_USERNAME, str) or "").strip()
        self._password: str = str(self.readConfig(CONFIG_PASSWORD, str) or "")
        self._rbw_entry: str = str(self.readConfig(CONFIG_RBW_ENTRY, str) or "").strip()

        # the query for which the user asked to see the full list again; an empty
        # string is a valid value, so this is None when nothing was asked for
        self._show_all_for: Optional[str] = None

        self.client = DockgeClient()

    def _request_show_all(self, term: str) -> None:
        """Stop filtering, for the query *term* the user is looking at."""
        self._show_all_for = term

    # -- config, bound to the settings widget below -----------------------

    @property
    def server_url(self) -> str:
        return self._url

    @server_url.setter
    def server_url(self, value: str):
        self._url = (value or "").strip()
        self.writeConfig(CONFIG_URL, self._url)
        self._apply_settings()

    @property
    def username(self) -> str:
        return self._username

    @username.setter
    def username(self, value: str):
        self._username = (value or "").strip()
        self.writeConfig(CONFIG_USERNAME, self._username)
        self._apply_settings()

    @property
    def password(self) -> str:
        return self._password

    @password.setter
    def password(self, value: str):
        self._password = value or ""
        self.writeConfig(CONFIG_PASSWORD, self._password)
        self._apply_settings()

    @property
    def password_rbw_entry(self) -> str:
        return self._rbw_entry

    @password_rbw_entry.setter
    def password_rbw_entry(self, value: str):
        self._rbw_entry = (value or "").strip()
        self.writeConfig(CONFIG_RBW_ENTRY, self._rbw_entry)
        self._apply_settings()

    def configWidget(self):
        return [
            {
                "type": "label",
                "text": (
                    "URL of your Dockge server. Docker stacks are read from and controlled "
                    "on that server - the plugin needs no access to the docker socket itself."
                ),
            },
            {
                "type": "lineedit",
                "property": "server_url",
                "label": "Dockge server URL",
                "widget_properties": {"placeholderText": "http://localhost:5001"},
            },
            {
                "type": "lineedit",
                "property": "username",
                "label": "Username",
                "widget_properties": {
                    "placeholderText": "admin - empty if dockge has no authentication"
                },
            },
            {
                "type": "label",
                "text": (
                    "Either type the password here - in which case Albert keeps it in "
                    "plaintext in its configuration - or leave that field empty and name "
                    "a Bitwarden entry below, which is then fetched with the rbw command "
                    "line tool whenever the plugin connects."
                ),
            },
            {"type": "lineedit", "property": "password", "label": "Password"},
            {
                "type": "lineedit",
                "property": "password_rbw_entry",
                "label": "Password (Bitwarden entry name)",
                "widget_properties": {"placeholderText": "dockge"},
            },
        ]

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def _makeIcon(self, state: str):
        """Return a zero-arg icon factory for the given container *state*."""
        return lambda: Icon.image(ICON_DIR / STATE_ICONS.get(state, STATE_ICONS["unknown"]))

    def defaultTrigger(self):
        return "dockge "

    def synopsis(self, query):
        return "stack name"

    def _apply_settings(self) -> None:
        """(Re)start the poller so that it picks up the current settings."""
        settings = Settings(
            self._url, self._username, self._password, self._rbw_entry
        )
        # Only the URL is required: a dockge that runs without authentication logs
        # us in on connect, so empty credentials are not an error by themselves.
        if settings.url:
            self.client.start(settings)
        else:
            self.client.stop()

    # -- items --------------------------------------------------------------------------------

    def setup(self, ctx) -> Optional[List[StandardItem]]:
        """Return the item the user has to deal with first - None if all is well."""
        # Only the URL is mandatory. A dockge that runs without authentication logs
        # us in on connect, and one with authentication complains about the missing
        # credentials itself, in terms the user can act on.
        if not self._url:
            return [
                StandardItem(
                    id=f"{self.id()}.setup",
                    icon_factory=self.makeIcon,
                    text="Please fill in the plugin settings - Dockge server URL missing",
                    subtext="Open the Dockge plugin in the Albert settings to configure it.",
                    actions=[
                        Action(
                            "open",
                            "Open the dockge website",
                            lambda: openUrl("https://github.com/louislam/dockge"),
                        ),
                    ],
                )
            ]

        if self._rbw_entry and shutil.which("rbw") is None:
            return [
                StandardItem(
                    id=f"{self.id()}.rbw-missing",
                    icon_factory=self.makeIcon,
                    text='"rbw" is not installed.',
                    subtext=(
                        f'It is needed to fetch the password of the "{self._rbw_entry}" '
                        "Bitwarden entry. Install it, or use a plaintext password instead."
                    ),
                    actions=[
                        Action(
                            "open",
                            "Open the rbw website",
                            lambda: openUrl("https://github.com/doy/rbw"),
                        ),
                    ],
                )
            ]

        return None

    def get_stack_as_item(
        self, ctx, name: str, stack: Dict, services: Dict[str, Dict[str, List[str]]]
    ) -> StandardItem:
        state = state_of(name, stack, services)

        # a stack that is not deployed yet has no container states at all, and
        # services.get() then hands back the empty dict default
        stack_services: Dict[str, List[str]] = services.get(name, {})
        detail = " | ".join(
            f"{service}: {summarize(states)}"
            for service, states in sorted(stack_services.items())
            if states
        )
        subtext = f"{state.upper()} | {detail}" if detail else state.upper()

        # make a remote stack obvious, since its name alone is ambiguous
        endpoint = endpoint_of(stack)
        if endpoint:
            subtext = f"{endpoint} | {subtext}"

        # a stack served by a remote agent has to carry that agent in its URL
        endpoint = endpoint_of(stack)
        page = stack_url(self._url, name, endpoint)

        actions = [
            Action(
                "open",
                "Open in browser" if not endpoint else f"Open {endpoint} in browser",
                lambda url=page: openUrl(url),
            ),
            Action(
                "restart",
                f"Restart {name}",
                lambda n=name: self.client.control(n, "restart"),
            ),
            Action(
                "update",
                f"Update {name}",
                lambda n=name: self.client.control(n, "update"),
            ),
            Action(
                "start",
                f"Start {name}",
                lambda n=name: self.client.control(n, "start"),
            ),
            Action(
                "stop",
                f"Stop {name}",
                lambda n=name: self.client.control(n, "stop"),
            ),
            Action(
                "refresh",
                "Refresh the stack list",
                lambda: self.client.control("", "refresh"),
            ),
        ]

        return StandardItem(
            id=f"{self.id()}.stack-{name}",
            icon_factory=self._makeIcon(state),
            text=name,
            subtext=subtext,
            input_action_text=f"{ctx.trigger}{name}",
            actions=actions,
        )

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        results: List[StandardItem] = []

        try:
            results_setup = self.setup(ctx)
            if results_setup is not None:
                yield results_setup
                return

            # starts the poller on the first query of a session, and restarts it
            # whenever the settings changed. It is a no-op while it keeps running.
            self._apply_settings()
            snapshot = self.client.snapshot(FIRST_RESULT_TIMEOUT)

            if snapshot.error:
                yield [
                    StandardItem(
                        id=f"{self.id()}.error",
                        icon_factory=self.makeIcon,
                        text=snapshot.error,
                        subtext="Press [ENTER] to retry.",
                        actions=[
                            Action("retry", "Retry", lambda: self._apply_settings()),
                            Action(
                                "copy",
                                "Copy error",
                                lambda e=snapshot.error: setClipboardText(e),
                            ),
                        ],
                    )
                ]
                return

            # everything typed after the trigger narrows the list, so `dockge bai`
            # shows just the baikal stack. An empty query keeps the full list.
            term = ctx.query.strip()
            if self._show_all_for is not None:
                if self._show_all_for == term:
                    # the user asked to see everything again for this exact query
                    term = ""
                else:
                    # they have since edited the query, so filtering resumes
                    self._show_all_for = None
            names = search_stacks(snapshot.stacks, term)

            for name in names:
                if not ctx.isValid:
                    return
                results.append(
                    self.get_stack_as_item(ctx, name, snapshot.stacks[name], snapshot.services)
                )

            if not results:
                if term:
                    # the search found nothing, which is a different problem from
                    # the server having no stacks at all
                    results.append(
                        StandardItem(
                            id=f"{self.id()}.nomatch",
                            icon_factory=self.makeIcon,
                            text=f'No stack matches "{term}"',
                            subtext=(
                                f"{len(snapshot.stacks)} stacks available - press ENTER "
                                "to clear the search"
                            ),
                            actions=[
                                Action(
                                    "showall",
                                    f"Show all {len(snapshot.stacks)} stacks",
                                    lambda t=term: self._request_show_all(t),
                                ),
                            ],
                            input_action_text=f"{ctx.trigger}",
                        )
                    )
                else:
                    results.append(
                        StandardItem(
                            id=f"{self.id()}.empty",
                            icon_factory=self.makeIcon,
                            text="No stacks found on this Dockge server",
                            actions=[
                                Action("open", "Open in browser", lambda: openUrl(self._url)),
                                Action(
                                    "refresh",
                                    "Refresh",
                                    lambda: self.client.control("", "refresh"),
                                ),
                            ],
                        )
                    )

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
