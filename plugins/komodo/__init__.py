"""Komodo - control the containers, stacks and resource syncs of a running Komodo
(https://komo.do) server.

The empty query lists everything Komodo knows about - containers, stacks and
resource syncs - and anything typed narrows that list by name. Every result
carries the actions that make sense for its kind: start/stop/restart/pause for
containers and stacks, deploy and image pulls for stacks, image pulls for
containers, and refresh/execute for resource syncs.

Everything goes through Komodo's REST API, authenticated with an API key and
secret pair, and nothing but that one server is ever contacted.
"""

import re
import subprocess
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Iterator, List, NamedTuple, Optional, Sequence, Tuple
from urllib.parse import quote, urljoin, urlparse

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
md_name = "Komodo"
md_description = "Control the containers, stacks and resource syncs of a running Komodo server"
md_license = "MIT"
md_url = (
    "https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/komodo"
)
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["requests"]
md_bin_dependencies: List[str] = []

ICON_DIR = Path(__file__).parent
ICON_PATH = ICON_DIR / "komodo.svg"

CONFIG_URL = "komodo_url"
CONFIG_API_KEY = "komodo_api_key"
CONFIG_API_KEY_COMMAND = "komodo_api_key_command"
CONFIG_API_SECRET = "komodo_api_secret"
CONFIG_API_SECRET_COMMAND = "komodo_api_secret_command"

# Where to read about the project when the plugin is not set up yet.
KOMODO_URL = "https://github.com/moghtech/komodo"

# Komodo runs on a home server, so a request slower than this is a server that
# is down, not one that is busy.
HTTP_TIMEOUT = 10
# How long a command that prints the API key or secret may take. A password
# manager that has to be unlocked can be slow, but not this slow.
KEY_COMMAND_TIMEOUT = 30
# How long the merged list of containers/stacks/syncs is reused before Komodo
# is asked again. Short enough that a change made in Komodo's own UI shows up
# here almost immediately, long enough that typing a search term does not cost
# three HTTP round trips per keystroke.
ENTRIES_TTL = 5.0
USER_AGENT = "awesome-albert-plugins/komodo"

# The icon shown for each of the five states a container, stack or sync can be
# in, as far as this plugin distinguishes them.
STATE_ICONS = {
    "running": "komodo-running.svg",
    "restarting": "komodo-restarting.svg",
    "stopped": "komodo-stopped.svg",
    "error": "komodo-error.svg",
    "unknown": "komodo-unknown.svg",
}

# ContainerListItem.state, as of Komodo's entities/docker/container.rs - a
# plain `#[serde(rename_all = "lowercase")]`, with the "no such container"
# state serialized as the empty string.
CONTAINER_STATE_CATEGORY = {
    "running": "running",
    "created": "stopped",
    "exited": "stopped",
    "restarting": "restarting",
    "stopping": "restarting",
    "paused": "restarting",
    "removing": "error",
    "dead": "error",
    "": "unknown",
}

# StackState, as of Komodo's entities/stack.rs - `#[serde(rename_all =
# "snake_case")]`.
STACK_STATE_CATEGORY = {
    "running": "running",
    "deploying": "restarting",
    "restarting": "restarting",
    "paused": "restarting",
    "stopped": "stopped",
    "created": "stopped",
    "down": "stopped",
    "dead": "error",
    "removing": "error",
    "unhealthy": "error",
    "unknown": "unknown",
}

# ResourceSyncState, as of Komodo's entities/sync.rs. Unlike the two states
# above, this one carries no `rename_all`, so it serializes as the Rust
# variant name verbatim - PascalCase.
SYNC_STATE_CATEGORY = {
    "Ok": "running",
    "Syncing": "restarting",
    "Pending": "restarting",
    "Failed": "error",
    "Unknown": "unknown",
}

SYNC_STATE_LABELS = {
    "Ok": "Up to date",
    "Syncing": "Syncing",
    "Pending": "Changes pending",
    "Failed": "Failed",
    "Unknown": "Unknown status",
}

# The order entries of equal search score are shown in - stacks first, since
# they are usually what you are looking for, then containers, then syncs.
KIND_PRIORITY = {"stack": 0, "container": 1, "sync": 2}


# plugin main functions -----------------------------------------------------------------------


class KomodoError(Exception):
    """A failure worth showing to the user as-is."""


def notify(msg: str, app_name: str = md_name) -> None:
    Notification(app_name, msg).send()


# urls ----------------------------------------------------------------------------------------


def join_url(base_url: str, path: str) -> str:
    """Join *path* onto the Komodo base URL.

    >>> join_url("http://localhost:9120", "read/ListStacks")
    'http://localhost:9120/read/ListStacks'
    >>> join_url("http://localhost:9120/", "/read/ListStacks")
    'http://localhost:9120/read/ListStacks'
    >>> join_url("https://komodo.example.com/komodo", "stacks/abc")
    'https://komodo.example.com/komodo/stacks/abc'
    """
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def stack_page_url(base_url: str, stack_id: str) -> str:
    """Deep link to a stack's page in the Komodo web UI.

    >>> stack_page_url("http://localhost:9120", "673e1f2b9c1d4a0012ab34cd")
    'http://localhost:9120/stacks/673e1f2b9c1d4a0012ab34cd'
    """
    return join_url(base_url, f"stacks/{quote(stack_id, safe='')}")


def sync_page_url(base_url: str, sync_id: str) -> str:
    """Deep link to a resource sync's page in the Komodo web UI.

    >>> sync_page_url("http://localhost:9120", "673e1f2b9c1d4a0012ab34cd")
    'http://localhost:9120/resource-syncs/673e1f2b9c1d4a0012ab34cd'
    """
    return join_url(base_url, f"resource-syncs/{quote(sync_id, safe='')}")


def container_page_url(base_url: str, server_id: str, container: str) -> str:
    """Deep link to a container's page in the Komodo web UI.

    A container is shown on the page of the server hosting it. One with no
    known server has nowhere to link to, so this falls back to the Komodo home
    page instead.

    >>> container_page_url("http://localhost:9120", "673e1f2b9c1d4a0012ab34cd", "nginx")
    'http://localhost:9120/servers/673e1f2b9c1d4a0012ab34cd/container/nginx'
    >>> container_page_url("http://localhost:9120", "", "nginx")
    'http://localhost:9120'
    """
    if not server_id:
        return base_url.rstrip("/")
    return join_url(
        base_url, f"servers/{quote(server_id, safe='')}/container/{quote(container, safe='')}"
    )


# the api key and secret -------------------------------------------------------------------


def resolve_secret(value: str, command: str, label: str) -> str:
    """The *label* to send, from the plaintext *value* or from *command*.

    A *command* wins over the plaintext value, so the latter can be left out of
    Albert's config entirely. The command is run through the shell and is
    expected to print the secret on stdout, e.g. ``pass show komodo-api-key``
    or ``rbw get komodo-api-key``; everything around it is ignored. Whatever it
    prints is held in memory only - it is never written back to the config.

    >>> resolve_secret("  plain  ", "", "API key")
    'plain'

    .. raises:: KomodoError
    """
    command = (command or "").strip()
    if not command:
        return (value or "").strip()

    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=KEY_COMMAND_TIMEOUT,
        )
    except subprocess.TimeoutExpired as e:
        raise KomodoError(
            f'"{command}" took longer than {KEY_COMMAND_TIMEOUT}s to print the {label}.'
        ) from e
    except OSError as e:
        raise KomodoError(f'Could not run "{command}": {e}') from e

    if proc.returncode != 0:
        detail = " ".join((proc.stderr or "").split())
        message = f'"{command}" failed to print the {label}'
        raise KomodoError(f"{message}: {detail}" if detail else f"{message}.")

    secret = (proc.stdout or "").strip()
    if not secret:
        raise KomodoError(f'"{command}" printed nothing; it must print the {label} on stdout.')
    return secret


# talking to the server ---------------------------------------------------------------------


def call(
    method: str,
    base_url: str,
    api_key: str,
    api_secret: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    timeout: float = HTTP_TIMEOUT,
) -> Any:
    """One round trip to Komodo's `/{read,write,execute}/{RequestName}` API.

    Komodo authenticates with `X-Api-Key`/`X-Api-Secret` headers and acts as
    the user (or service user) those belong to.

    .. raises:: KomodoError
    """
    if not base_url:
        raise KomodoError("No Komodo URL is configured. Add one in the plugin settings.")

    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise KomodoError(
            f'"{base_url}" is not a full URL. The plugin setting should look like '
            "http://localhost:9120."
        )

    kwargs: Dict[str, Any] = {
        "headers": {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "X-Api-Key": api_key,
            "X-Api-Secret": api_secret,
        },
        "json": body if body is not None else {},
        "timeout": timeout,
    }

    url = join_url(base_url, path)
    try:
        response = requests.request(method, url, **kwargs)
    except requests.Timeout as e:
        raise KomodoError(f"{base_url} did not answer within {timeout:g}s.") from e
    except requests.RequestException as e:
        raise KomodoError(f"Cannot reach {base_url}: {e}") from e

    return _payload(response, base_url)


def _payload(response: Any, base_url: str) -> Any:
    """Decode *response*, turning an error status into a KomodoError.

    .. raises:: KomodoError
    """
    if response.status_code == 204:
        return None

    if response.status_code >= 400:
        raise KomodoError(_error_message(response, base_url))

    try:
        return response.json()
    except ValueError as e:
        raise KomodoError(
            f"{base_url} did not answer with JSON (HTTP {response.status_code})."
        ) from e


def _error_message(response: Any, base_url: str) -> str:
    """A sentence about what Komodo refused and why.

    Komodo's own error responses are `{"error": "...", "trace": [...]}`; a
    reverse proxy in front of it may answer with a page of HTML instead, so
    this falls back to the raw body when there is no such field.
    """
    detail = ""
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        value = payload.get("error")
        if isinstance(value, str) and value.strip():
            detail = " ".join(value.split())

    if not detail:
        detail = " ".join(str(response.text or "").split())[:200]

    message = f"{base_url} answered HTTP {response.status_code}"
    if detail:
        message += f": {detail}"
    if response.status_code in (401, 403):
        message += ". Check the API key and secret in the plugin settings."
    return message


def fetch_stacks(base_url: str, api_key: str, api_secret: str) -> List[Dict]:
    """Every stack Komodo knows about.

    .. raises:: KomodoError
    """
    payload = call("POST", base_url, api_key, api_secret, "read/ListStacks", {"limit": 0})
    if not isinstance(payload, list):
        raise KomodoError(f"{base_url} answered the stack list with something unexpected.")
    return [stack for stack in payload if isinstance(stack, dict)]


def fetch_containers(base_url: str, api_key: str, api_secret: str) -> List[Dict]:
    """Every container on every server Komodo manages.

    .. raises:: KomodoError
    """
    payload = call(
        "POST", base_url, api_key, api_secret, "read/ListAllContainers", {"limit": 0}
    )
    if not isinstance(payload, list):
        raise KomodoError(f"{base_url} answered the container list with something unexpected.")
    return [container for container in payload if isinstance(container, dict)]


def fetch_syncs(base_url: str, api_key: str, api_secret: str) -> List[Dict]:
    """Every resource sync Komodo knows about.

    .. raises:: KomodoError
    """
    payload = call(
        "POST", base_url, api_key, api_secret, "read/ListResourceSyncs", {"limit": 0}
    )
    if not isinstance(payload, list):
        raise KomodoError(f"{base_url} answered the sync list with something unexpected.")
    return [sync for sync in payload if isinstance(sync, dict)]


def fetch_container_resource(
    base_url: str, api_key: str, api_secret: str, server_id: str, container: str
) -> Dict:
    """The stack or deployment *container* belongs to.

    An empty dict when the container belongs to neither of them.

    .. raises:: KomodoError
    """
    payload = call(
        "POST",
        base_url,
        api_key,
        api_secret,
        "read/GetResourceMatchingContainer",
        {"server": server_id, "container": container},
    )
    if not isinstance(payload, dict):
        raise KomodoError(
            f"{base_url} answered the container lookup with something unexpected."
        )
    resource = payload.get("resource")
    return resource if isinstance(resource, dict) else {}


def fetch_stack_services(
    base_url: str, api_key: str, api_secret: str, stack_id: str
) -> List[Dict]:
    """The services of a stack, each with the container it runs.

    .. raises:: KomodoError
    """
    payload = call(
        "POST",
        base_url,
        api_key,
        api_secret,
        "read/ListStackServices",
        {"stack": stack_id},
    )
    if not isinstance(payload, list):
        raise KomodoError(
            f"{base_url} answered the stack services with something unexpected."
        )
    return [service for service in payload if isinstance(service, dict)]


def update_error(update: Dict) -> str:
    """Why a Komodo `Update` (the response to an execute call) reports failure.

    The last log whose own `success` is false is the one that actually broke;
    its stderr (or stdout, for a command that only ever writes there) is the
    detail worth showing.
    """
    logs = update.get("logs")
    if isinstance(logs, list):
        for log in reversed(logs):
            if isinstance(log, dict) and log.get("success") is False:
                detail = " ".join(str(log.get("stderr") or log.get("stdout") or "").split())
                if detail:
                    return detail[:300]
    return "the operation failed - see its update log in Komodo for details"


def run_action(
    base_url: str, api_key: str, api_secret: str, path: str, body: Dict[str, Any]
) -> None:
    """One `execute` or `write` call, raising KomodoError if Komodo reports failure.

    An `execute` call answers with an `Update` carrying a `success` flag; a
    `write` call (just `RefreshResourceSyncPending` here) answers with the
    resource itself and has no such flag - for that one, a non-2xx status is
    the only failure mode, and `call` already raises for that.

    .. raises:: KomodoError
    """
    payload = call("POST", base_url, api_key, api_secret, path, body)
    if isinstance(payload, dict) and payload.get("success") is False:
        raise KomodoError(update_error(payload))


# pulling images ----------------------------------------------------------------------


def stack_pull_body(stack_id: str, services: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """The body of a `PullStack` call.

    Without *services* the images of all the stack's services are pulled.

    >>> stack_pull_body("673e1f2b9c1d4a0012ab34cd")
    {'stack': '673e1f2b9c1d4a0012ab34cd', 'services': []}
    >>> stack_pull_body("673e1f2b9c1d4a0012ab34cd", ["web"])
    {'stack': '673e1f2b9c1d4a0012ab34cd', 'services': ['web']}
    """
    return {"stack": stack_id, "services": list(services or [])}


def replica_stripped(name: str) -> str:
    """The container *name* without its replica number.

    Compose names the containers of a service `<project>-<service>-<replica>`,
    and Komodo lists only the first container of a service that runs more than
    one replica.

    >>> replica_stripped("media-web-1")
    'media-web'
    >>> replica_stripped("media-web")
    'media-web'
    """
    return re.sub(r"-\d+$", "", name)


def service_of_container(services: Sequence[Dict], container: str) -> str:
    """The name of the stack service *container* is the container of.

    Komodo lists a stack's services together with the container each of them
    runs, so the container is what the service is looked up by. An empty string
    when no service of the list runs that container.

    A service running more than one replica only lists its first container, so
    the other replicas are matched by their name without the replica number.

    >>> service_of_container(
    ...     [{"service": "web", "container": {"name": "media-web-1"}}], "media-web-1"
    ... )
    'web'
    >>> service_of_container(
    ...     [{"service": "web", "container": {"name": "media-web-1"}}], "media-web-2"
    ... )
    'web'
    >>> service_of_container(
    ...     [{"service": "web", "container": {"name": "media-web-1"}}], "media-db-1"
    ... )
    ''
    """
    for service in services:
        item = service.get("container")
        if isinstance(item, dict) and str(item.get("name") or "") == container:
            return str(service.get("service") or "")

    for service in services:
        item = service.get("container")
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if name and replica_stripped(name) == replica_stripped(container):
            return str(service.get("service") or "")
    return ""


def pull_container_image(
    base_url: str, api_key: str, api_secret: str, server_id: str, container: str
) -> None:
    """Pull the latest image of *container*.

    Komodo pulls images per compose service, so the stack the container
    belongs to is looked up first and only the service that container runs is
    pulled. The container of a deployment has its image pulled as a whole
    deployment.

    .. raises:: KomodoError
    """
    if not server_id:
        raise KomodoError(
            f"Komodo does not know the server of the container {container}, so its "
            "image cannot be pulled."
        )

    resource = fetch_container_resource(base_url, api_key, api_secret, server_id, container)
    kind = str(resource.get("type") or "")
    resource_id = str(resource.get("id") or "")

    if kind == "deployment":
        run_action(
            base_url,
            api_key,
            api_secret,
            "execute/PullDeployment",
            {"deployment": resource_id},
        )
        return

    if kind != "stack":
        raise KomodoError(
            f"Komodo cannot pull the image of {container}: it is not part of a stack "
            "or a deployment."
        )

    services = fetch_stack_services(base_url, api_key, api_secret, resource_id)
    service = service_of_container(services, container)
    if not service:
        raise KomodoError(
            f"Komodo does not know which service of the stack the container "
            f"{container} belongs to."
        )

    run_action(
        base_url,
        api_key,
        api_secret,
        "execute/PullStack",
        stack_pull_body(resource_id, [service]),
    )


# searching -------------------------------------------------------------------------------


def fuzzy_score(needle: str, haystack: str) -> float:
    """How well *needle* matches *haystack*, 0.0 when it does not match at all.

    A plain subsequence test plus a similarity ratio, so both `media` and `md`
    find `media`, and a typo still finds the entry you meant. Deliberately not
    `difflib.get_close_matches` on its own: that insists on roughly the same
    length in both strings, so typing the first two letters of a long name
    would match nothing.

    >>> fuzzy_score("med", "media") > 0.9
    True
    >>> fuzzy_score("ma", "media") > 0      # skipped letters still match
    True
    >>> fuzzy_score("media", "nginx")       # nothing in common
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

    # every character of the needle present, in order: `md` -> `media`
    it = iter(haystack)
    if not all(char in it for char in needle):
        # last resort, so a typo narrows the list instead of emptying it
        from difflib import SequenceMatcher

        ratio = SequenceMatcher(None, needle, haystack).ratio()
        return ratio * 0.7 if ratio >= 0.6 else 0.0

    # reward tight, early subsequences over scattered ones
    positions = [haystack.index(char) for char in needle]
    span = positions[-1] - positions[0] + 1
    return 0.6 + 0.25 * (len(needle) / span)


class Entry(NamedTuple):
    """One row of the merged container/stack/sync list."""

    kind: str  # "stack", "container" or "sync"
    key: str  # unique within its kind, used to build the StandardItem id
    search_text: str  # what a query is matched against
    data: Dict


def build_entries(
    stacks: Sequence[Dict], containers: Sequence[Dict], syncs: Sequence[Dict]
) -> List[Entry]:
    """Turn three raw API responses into one flat, uniform list."""
    entries: List[Entry] = []

    for stack in stacks:
        info = stack_info(stack)
        name = str(stack.get("name") or "")
        server = str(info.get("server_name") or "")
        entries.append(
            Entry("stack", str(stack.get("id") or ""), f"{name} {server}".strip(), stack)
        )

    for container in containers:
        name = str(container.get("name") or "")
        server = str(container.get("server_name") or "")
        key = f"{container.get('server_id') or ''}:{name}"
        entries.append(Entry("container", key, f"{name} {server}".strip(), container))

    for sync in syncs:
        name = str(sync.get("name") or "")
        entries.append(Entry("sync", str(sync.get("id") or ""), name, sync))

    return entries


def search_entries(entries: Sequence[Entry], term: str) -> List[Entry]:
    """The *entries* matching *term*, best first.

    An empty *term* keeps every entry, grouped by kind (stacks, then
    containers, then syncs) and alphabetical within each group.
    """
    term = term.strip()

    scored: List[Tuple[float, int, str, Entry]] = []
    for entry in entries:
        score = 1.0 if not term else fuzzy_score(term, entry.search_text)
        if score > 0.0:
            scored.append(
                (score, KIND_PRIORITY.get(entry.kind, 9), entry.search_text.lower(), entry)
            )

    scored.sort(key=lambda row: (-row[0], row[1], row[2]))
    return [row[3] for row in scored]


# reading the payloads ------------------------------------------------------------------------


def stack_info(stack: Dict) -> Dict:
    info = stack.get("info")
    return info if isinstance(info, dict) else {}


def stack_state_category(stack: Dict) -> str:
    return STACK_STATE_CATEGORY.get(str(stack_info(stack).get("state") or ""), "unknown")


def stack_services_summary(stack: Dict) -> str:
    """Which compose services *stack* has - names if there are few, a count otherwise."""
    services = stack_info(stack).get("services")
    if not isinstance(services, list):
        return ""

    names = [
        str(service.get("service"))
        for service in services
        if isinstance(service, dict) and service.get("service")
    ]
    if not names:
        return ""
    if len(names) <= 4:
        return ", ".join(names)
    return f"{len(names)} services"


def stack_subtext(stack: Dict) -> str:
    info = stack_info(stack)
    parts = ["Stack"]

    server = info.get("server_name")
    if server:
        parts.append(str(server))

    state = str(info.get("state") or "")
    parts.append(state.upper() if state else "UNKNOWN")

    summary = stack_services_summary(stack)
    if summary:
        parts.append(summary)

    return " | ".join(parts)


def container_state_category(container: Dict) -> str:
    return CONTAINER_STATE_CATEGORY.get(str(container.get("state") or ""), "unknown")


def container_subtext(container: Dict) -> str:
    parts = ["Container"]

    server = container.get("server_name")
    if server:
        parts.append(str(server))

    state = str(container.get("state") or "")
    parts.append(state.upper() if state else "UNKNOWN")

    image = container.get("image")
    if image:
        parts.append(str(image))

    return " | ".join(parts)


def sync_info(sync: Dict) -> Dict:
    info = sync.get("info")
    return info if isinstance(info, dict) else {}


def sync_state_category(sync: Dict) -> str:
    return SYNC_STATE_CATEGORY.get(str(sync_info(sync).get("state") or ""), "unknown")


def sync_subtext(sync: Dict) -> str:
    info = sync_info(sync)
    parts = [
        "Resource Sync",
        SYNC_STATE_LABELS.get(str(info.get("state") or ""), "Unknown status"),
    ]

    message = info.get("last_sync_message")
    if isinstance(message, str) and message.strip():
        parts.append(message.strip())
    elif info.get("last_sync_hash"):
        parts.append(f"last sync {info['last_sync_hash']}")

    return " | ".join(parts)


# main plugin class --------------------------------------------------------------------------


class Plugin(PluginInstance, GeneratorQueryHandler):
    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)

        # readConfig is untyped in the stub and hands back whatever was stored,
        # so a value edited by hand can be anything
        self._url: str = str(self.readConfig(CONFIG_URL, str) or "").strip()
        self._api_key_value: str = str(self.readConfig(CONFIG_API_KEY, str) or "").strip()
        self._api_key_command: str = str(
            self.readConfig(CONFIG_API_KEY_COMMAND, str) or ""
        ).strip()
        self._api_secret_value: str = str(
            self.readConfig(CONFIG_API_SECRET, str) or ""
        ).strip()
        self._api_secret_command: str = str(
            self.readConfig(CONFIG_API_SECRET_COMMAND, str) or ""
        ).strip()

        # Guards the cache below and the two resolved secrets. In memory only:
        # a restart of albert is a good enough reason to ask Komodo again.
        self._lock = threading.Lock()
        self._entries: Optional[Tuple[float, List[Entry]]] = None
        self._resolved_key: Optional[str] = None
        self._resolved_secret: Optional[str] = None

    # -- config, bound to the settings widget below ---------------------------------------

    @property
    def komodo_url(self) -> str:
        return self._url

    @komodo_url.setter
    def komodo_url(self, value: str):
        self._url = (value or "").strip()
        self.writeConfig(CONFIG_URL, self._url)
        self._forget()

    @property
    def api_key(self) -> str:
        return self._api_key_value

    @api_key.setter
    def api_key(self, value: str):
        self._api_key_value = (value or "").strip()
        self.writeConfig(CONFIG_API_KEY, self._api_key_value)
        self._resolved_key = None
        self._forget()

    @property
    def api_key_command(self) -> str:
        return self._api_key_command

    @api_key_command.setter
    def api_key_command(self, value: str):
        self._api_key_command = (value or "").strip()
        self.writeConfig(CONFIG_API_KEY_COMMAND, self._api_key_command)
        self._resolved_key = None
        self._forget()

    @property
    def api_secret(self) -> str:
        return self._api_secret_value

    @api_secret.setter
    def api_secret(self, value: str):
        self._api_secret_value = (value or "").strip()
        self.writeConfig(CONFIG_API_SECRET, self._api_secret_value)
        self._resolved_secret = None
        self._forget()

    @property
    def api_secret_command(self) -> str:
        return self._api_secret_command

    @api_secret_command.setter
    def api_secret_command(self, value: str):
        self._api_secret_command = (value or "").strip()
        self.writeConfig(CONFIG_API_SECRET_COMMAND, self._api_secret_command)
        self._resolved_secret = None
        self._forget()

    def configWidget(self):
        return [
            {
                "type": "label",
                "text": (
                    "Point this at your Komodo server and give it an API key and secret. "
                    "The plugin only ever talks to that one server."
                ),
            },
            {
                "type": "lineedit",
                "property": "komodo_url",
                "label": "Komodo URL",
                "widget_properties": {"placeholderText": "http://localhost:9120"},
            },
            {
                "type": "lineedit",
                "property": "api_key",
                "label": "API key",
                "widget_properties": {"echoMode": 2, "placeholderText": "API key"},
            },
            {
                "type": "lineedit",
                "property": "api_secret",
                "label": "API secret",
                "widget_properties": {"echoMode": 2, "placeholderText": "API secret"},
            },
            {
                "type": "label",
                "text": (
                    "A key or secret typed above is kept by Albert in plaintext. To keep "
                    "either off the disk entirely, leave the field empty and put a command "
                    "here instead: it is run through the shell and must print the value on "
                    "stdout, e.g. 'pass show komodo/key' or 'rbw get komodo-key'. A command "
                    "wins over the plaintext field next to it, and the value it prints is "
                    "held in memory only."
                ),
            },
            {
                "type": "lineedit",
                "property": "api_key_command",
                "label": "API key command",
                "widget_properties": {"placeholderText": "pass show komodo/key"},
            },
            {
                "type": "lineedit",
                "property": "api_secret_command",
                "label": "API secret command",
                "widget_properties": {"placeholderText": "pass show komodo/secret"},
            },
            {
                "type": "label",
                "text": (
                    "Create an API key for your user, or for a Service User with limited "
                    "permissions, from the Komodo UI settings page. Komodo hands out the key "
                    "and the secret together, once, when the key is created."
                ),
            },
        ]

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def _make_icon(self, category: str):
        """Return a zero-arg icon factory for the given state *category*."""
        path = ICON_DIR / STATE_ICONS.get(category, STATE_ICONS["unknown"])
        return lambda: Icon.image(path)

    def defaultTrigger(self):
        return "komo "

    def synopsis(self, query):
        return "a container, stack or sync name, or nothing for everything"

    # -- secrets and cache ------------------------------------------------------------------

    def _forget(self) -> None:
        """Drop the cached list, so the next query asks Komodo again."""
        with self._lock:
            self._entries = None

    def _api_key(self) -> str:
        """The API key to send, running the configured command at most once.

        .. raises:: KomodoError
        """
        if not self._api_key_command:
            return self._api_key_value

        with self._lock:
            cached = self._resolved_key
        if cached is not None:
            return cached

        # run the command outside the lock: it is a subprocess, not a lookup
        key = resolve_secret(self._api_key_value, self._api_key_command, "API key")
        with self._lock:
            self._resolved_key = key
        return key

    def _api_secret(self) -> str:
        """The API secret to send, running the configured command at most once.

        .. raises:: KomodoError
        """
        if not self._api_secret_command:
            return self._api_secret_value

        with self._lock:
            cached = self._resolved_secret
        if cached is not None:
            return cached

        secret = resolve_secret(self._api_secret_value, self._api_secret_command, "API secret")
        with self._lock:
            self._resolved_secret = secret
        return secret

    def _entries_list(self) -> List[Entry]:
        """The merged container/stack/sync list, refetched at most every ENTRIES_TTL seconds.

        .. raises:: KomodoError
        """
        with self._lock:
            cached = self._entries
        if cached is not None and time.monotonic() - cached[0] < ENTRIES_TTL:
            return cached[1]

        api_key = self._api_key()
        api_secret = self._api_secret()
        entries = build_entries(
            fetch_stacks(self._url, api_key, api_secret),
            fetch_containers(self._url, api_key, api_secret),
            fetch_syncs(self._url, api_key, api_secret),
        )

        with self._lock:
            self._entries = (time.monotonic(), entries)
        return entries

    # -- items --------------------------------------------------------------------------------

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        try:
            setup = self._setup_item()
            if setup is not None:
                yield [setup]
                return

            term = ctx.query.strip()
            entries = self._entries_list()
            if not ctx.isValid:
                return

            matches = search_entries(entries, term)
            results = [self._entry_item(ctx, entry) for entry in matches]

            if not results:
                results = [self._no_match_item(term) if term else self._empty_item()]

            yield results

        except KomodoError as e:
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
                text="Please fill in the plugin settings - Komodo URL missing",
                subtext="Open the Komodo plugin in the Albert settings to configure it.",
                input_action_text="",
                actions=[
                    Action("open", "Open the Komodo website", lambda: openUrl(KOMODO_URL))
                ],
            )

        missing_key = not self._api_key_value and not self._api_key_command
        missing_secret = not self._api_secret_value and not self._api_secret_command
        if missing_key or missing_secret:
            what = "API key and secret" if missing_key and missing_secret else (
                "API key" if missing_key else "API secret"
            )
            return StandardItem(
                id=f"{self.id()}.setup-key",
                icon_factory=self.makeIcon,
                text=f"Please fill in the plugin settings - Komodo {what} missing",
                subtext=(
                    f"Create one in Komodo at {self._url} under its settings page, then paste "
                    "it (or a command that prints it) in the plugin settings."
                ),
                input_action_text="",
                actions=[Action("open", "Open Komodo", lambda: openUrl(self._url))],
            )

        return None

    def _entry_item(self, ctx, entry: Entry) -> StandardItem:
        if entry.kind == "stack":
            return self._stack_item(ctx, entry.data)
        if entry.kind == "container":
            return self._container_item(ctx, entry.data)
        return self._sync_item(ctx, entry.data)

    def _stack_item(self, ctx, stack: Dict) -> StandardItem:
        stack_id = str(stack.get("id") or "")
        name = str(stack.get("name") or stack_id)
        page = stack_page_url(self._url, stack_id)

        def run(path: str, verb: str, i=stack_id, n=name):
            self._run_stack(i, n, path, verb)

        actions = [
            Action("open", "Open in browser", lambda url=page: openUrl(url)),
            Action("deploy", f"Deploy {name}", lambda: run("execute/DeployStack", "Deployed")),
            Action(
                "pull",
                f"Pull images for {name}",
                lambda i=stack_id, n=name: self._pull_stack(i, n),
            ),
            Action("start", f"Start {name}", lambda: run("execute/StartStack", "Started")),
            Action("stop", f"Stop {name}", lambda: run("execute/StopStack", "Stopped")),
            Action(
                "restart", f"Restart {name}", lambda: run("execute/RestartStack", "Restarted")
            ),
            Action("pause", f"Pause {name}", lambda: run("execute/PauseStack", "Paused")),
            Action(
                "unpause", f"Unpause {name}", lambda: run("execute/UnpauseStack", "Unpaused")
            ),
            Action("reload", "Reload the list", self._forget),
        ]

        return StandardItem(
            id=f"{self.id()}.stack-{stack_id}",
            icon_factory=self._make_icon(stack_state_category(stack)),
            text=name,
            subtext=stack_subtext(stack),
            input_action_text=f"{ctx.trigger}{name}",
            actions=actions,
        )

    def _container_item(self, ctx, container: Dict) -> StandardItem:
        server_id = str(container.get("server_id") or "")
        name = str(container.get("name") or "")
        page = container_page_url(self._url, server_id, name)

        def run(path: str, verb: str, s=server_id, c=name):
            self._run_container(s, c, path, verb)

        actions = [
            Action("open", "Open in browser", lambda url=page: openUrl(url)),
            Action(
                "start", f"Start {name}", lambda: run("execute/StartContainer", "Started")
            ),
            Action("stop", f"Stop {name}", lambda: run("execute/StopContainer", "Stopped")),
            Action(
                "restart",
                f"Restart {name}",
                lambda: run("execute/RestartContainer", "Restarted"),
            ),
            Action(
                "pull",
                f"Pull image for {name}",
                lambda s=server_id, c=name: self._pull_container(s, c),
            ),
            Action(
                "pause", f"Pause {name}", lambda: run("execute/PauseContainer", "Paused")
            ),
            Action(
                "unpause",
                f"Unpause {name}",
                lambda: run("execute/UnpauseContainer", "Unpaused"),
            ),
            Action("reload", "Reload the list", self._forget),
        ]

        return StandardItem(
            id=f"{self.id()}.container-{server_id}-{name}",
            icon_factory=self._make_icon(container_state_category(container)),
            text=name,
            subtext=container_subtext(container),
            input_action_text=f"{ctx.trigger}{name}",
            actions=actions,
        )

    def _sync_item(self, ctx, sync: Dict) -> StandardItem:
        sync_id = str(sync.get("id") or "")
        name = str(sync.get("name") or sync_id)
        page = sync_page_url(self._url, sync_id)

        actions = [
            Action("open", "Open in browser", lambda url=page: openUrl(url)),
            Action(
                "refresh",
                f"Refresh {name}",
                lambda i=sync_id, n=name: self._refresh_sync(i, n),
            ),
            Action(
                "run", f"Execute {name}", lambda i=sync_id, n=name: self._run_sync(i, n)
            ),
            Action("reload", "Reload the list", self._forget),
        ]

        return StandardItem(
            id=f"{self.id()}.sync-{sync_id}",
            icon_factory=self._make_icon(sync_state_category(sync)),
            text=name,
            subtext=sync_subtext(sync),
            input_action_text=f"{ctx.trigger}{name}",
            actions=actions,
        )

    def _no_match_item(self, term: str) -> StandardItem:
        return StandardItem(
            id=f"{self.id()}.no-match",
            icon_factory=self.makeIcon,
            text=f'Nothing on Komodo matches "{term}"',
            subtext="Searches containers, stacks and resource syncs by name",
            input_action_text="",
            actions=[
                Action("open", "Open Komodo", lambda: openUrl(self._url)),
                Action("reload", "Reload the list", self._forget),
            ],
        )

    def _empty_item(self) -> StandardItem:
        return StandardItem(
            id=f"{self.id()}.empty",
            icon_factory=self.makeIcon,
            text="Komodo has no containers, stacks or resource syncs yet",
            input_action_text="",
            actions=[
                Action("open", "Open Komodo", lambda: openUrl(self._url)),
                Action("reload", "Reload the list", self._forget),
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

    def _run_stack(self, stack_id: str, name: str, path: str, verb: str) -> None:
        self._async(
            lambda: run_action(
                self._url, self._api_key(), self._api_secret(), path, {"stack": stack_id}
            ),
            f"{verb} {name}",
        )

    def _run_container(self, server_id: str, container: str, path: str, verb: str) -> None:
        self._async(
            lambda: run_action(
                self._url,
                self._api_key(),
                self._api_secret(),
                path,
                {"server": server_id, "container": container},
            ),
            f"{verb} {container}",
        )

    def _pull_stack(self, stack_id: str, name: str) -> None:
        self._async(
            lambda: run_action(
                self._url,
                self._api_key(),
                self._api_secret(),
                "execute/PullStack",
                stack_pull_body(stack_id),
            ),
            f"Pulled the images of {name}",
        )

    def _pull_container(self, server_id: str, container: str) -> None:
        self._async(
            lambda: pull_container_image(
                self._url, self._api_key(), self._api_secret(), server_id, container
            ),
            f"Pulled the image of {container}",
        )

    def _refresh_sync(self, sync_id: str, name: str) -> None:
        self._async(
            lambda: run_action(
                self._url,
                self._api_key(),
                self._api_secret(),
                "write/RefreshResourceSyncPending",
                {"sync": sync_id},
            ),
            f"Refreshed {name}",
        )

    def _run_sync(self, sync_id: str, name: str) -> None:
        self._async(
            lambda: run_action(
                self._url,
                self._api_key(),
                self._api_secret(),
                "execute/RunSync",
                {"sync": sync_id},
            ),
            f"Ran sync {name}",
        )

    def _async(self, work, note: str) -> None:
        """Drop the cache, then run *work* off the UI thread and report it.

        The cache goes first so that a query arriving while the action is
        still in flight does not rebuild the list as it was before the change.
        """
        self._forget()
        threading.Thread(
            target=self._mutate, args=(work, note), name="komodo-action", daemon=True
        ).start()

    @staticmethod
    def _mutate(work, note: str) -> None:
        try:
            work()
        except KomodoError as e:
            debug(traceback.format_exc())
            notify(str(e))
        except Exception:
            trace = traceback.format_exc()
            critical(trace)
            notify(trace.strip().splitlines()[-1] if trace.strip() else "unknown error")
        else:
            notify(note)
