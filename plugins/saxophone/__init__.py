"""Saxophone - Play internet radio streams from albert."""

import json
import operator
import os
import random
import select
import signal
import socket
import subprocess
import time
import traceback
from enum import Enum
from pathlib import Path
from typing import Iterator, List, Optional

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

md_name = "Saxophone"
md_description = "Play internet radio streams from albert"
md_iid = "5.0"
md_version = "0.4"
md_license = "MIT"
md_url = "https://github.com/bergercookie/awesome-albert-plugins"
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["requests"]
md_bin_dependencies = ["vlc", "pgrep"]

icons_path = Path(__file__).parent / "images"


def get_icon(icon: str) -> str:
    return str(icons_path / icon)


def notify(
    app_name: str,
    msg: str,
):
    Notification(app_name, msg).send()


def sort_random(streams):
    random.shuffle(streams)


def sort_favorite(streams):
    streams.sort(key=operator.attrgetter("favorite"), reverse=True)


ICON_PATH = get_icon("saxophone.png")
STOP_ICON_PATH = get_icon("stop_icon.png")
REPEAT_ICON_PATH = get_icon("repeat_icon.png")

json_config = str(Path(__file__).parent / "config" / "saxophone.json")

sort_fn = sort_random
# sort_fn = sort_favorite

vlc_socket = Path("/tmp/cvlc.unix")
socket_timeout = 0.2
vlc_stop_timeout = 1.0
vlc_process: Optional[subprocess.Popen] = None

# Classes & supplementary functions -----------------------------------------------------------


class UrlType(Enum):
    PLAYLIST = 0
    RAW_STREAM = 1
    COUNT = 2
    INVALID = 3


def issue_cmd(cmd: str) -> str:
    """Send a command to the VLC RC interface. Returns "" if VLC isn't up."""
    if not cmd.endswith("\n"):
        cmd += "\n"
    try:
        return _issue_cmd(cmd)
    except OSError as e:
        print(f"saxophone: VLC is not available - {e}")
        return ""


def _issue_cmd(cmd: str) -> str:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(socket_timeout)
        s.connect(str(vlc_socket))

        to_send = str.encode(cmd)
        s.sendall(to_send)

        # we don't want to block
        res = ""
        try:
            ready = select.select([s], [], [], socket_timeout)
            if ready[0]:
                while True:
                    b = s.recv(4096)
                    if b:
                        res += b.decode("utf-8")
                    else:
                        break
        except socket.timeout:
            pass

        return res


class Stream:
    def __init__(self, url: str, name: str, **kargs):
        super(Stream, self).__init__()

        self.url: str = url
        self.name: str = name
        self.description: Optional[str] = kargs.get("description")
        self.homepage: Optional[str] = kargs.get("homepage")
        self._icon: Optional[str] = kargs.get("icon")
        self.favorite: bool = kargs.get("favorite", False)

        self._url_type: Optional[UrlType] = None
        if self.url.endswith(".pls") or self.url.endswith(".m3u"):
            self._url_type = UrlType.PLAYLIST
        else:
            self._url_type = UrlType.RAW_STREAM

    def url_type(self) -> Optional[UrlType]:  # type: ignore
        return self._url_type

    def icon(self) -> Optional[str]:
        """Cache the icon."""
        if self._icon is None:
            return None

        return get_icon(self._icon)


streams: List[Stream] = []


def init_streams():
    global streams
    streams.clear()

    with open(json_config) as f:
        conts = json.load(f)

        for item in conts["all"]:
            streams.append(Stream(**item))
    sort_fn(streams)


def launch_vlc():
    global vlc_process
    if vlc_socket.exists():
        if not vlc_socket.is_socket():
            raise RuntimeError(f'Exected socket file "{vlc_socket}" is not a socket')
        else:
            info("VLC RC Interface is already up.")
    else:
        # communicate over UNIX socket with vlc
        try:
            vlc_process = subprocess.Popen(
                ["vlc", "-I", "oldrc", "--rc-unix", str(vlc_socket)]
            )
        except OSError as e:
            print(f"saxophone: could not launch vlc - {e}")


def _vlc_pids() -> List[int]:
    """The PIDs of the VLC processes that serve this plugin's RC socket."""
    global vlc_process
    pids = []
    if vlc_process is not None:
        if vlc_process.poll() is None:
            pids.append(vlc_process.pid)
        else:
            vlc_process = None

    # VLC outlives the module when the plugin is unloaded, and an old instance
    # may still be around, so look beyond the process handle. Only our own VLC
    # has the socket on its command line.
    try:
        result = subprocess.run(
            ["pgrep", "-f", f"[v]lc .*--rc-unix {vlc_socket}"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as e:
        print(f"saxophone: could not look for the vlc process - {e}")
        return pids
    pids.extend(int(pid) for pid in result.stdout.split() if pid.isdigit())
    return sorted(set(pids))


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _kill_vlc(pids: List[int]) -> None:
    """Ask *pids* to quit, killing them if they do not within the timeout."""
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass

    deadline = time.monotonic() + vlc_stop_timeout
    while time.monotonic() < deadline and any(_pid_alive(pid) for pid in pids):
        time.sleep(0.05)

    for pid in pids:
        if _pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass


def restart_vlc():
    """Restart VLC, killing it first if it has become unresponsive."""
    global vlc_process

    issue_cmd("quit")
    pids = _vlc_pids()
    if pids:
        _kill_vlc(pids)
    vlc_process = None

    # A killed VLC does not always remove its socket file, and launch_vlc()
    # would then mistake it for a running instance.
    if vlc_socket.exists():
        try:
            vlc_socket.unlink()
        except OSError as e:
            print(f"saxophone: could not remove {vlc_socket} - {e}")

    launch_vlc()
    info("Restarted VLC.")


def is_radio_on() -> bool:
    res = issue_cmd("is_playing")
    try:
        return int(res) == 1
    except (TypeError, ValueError):
        return False


def stop_radio():
    """Turn off the radio."""
    res = issue_cmd("stop")
    debug(f"Stopping radio,\n{res}")


def start_stream(stream: Stream):
    res = issue_cmd(f"add {stream.url}")
    debug(f"Starting stream,\n{res}")


# supplementary functions ---------------------------------------------------------------------
def get_as_item(stream: Stream) -> StandardItem:
    icon = stream.icon() or ICON_PATH
    actions = [Action("play", "Play", lambda stream=stream: start_stream(stream))]
    if stream.homepage:
        actions.append(
            Action("open", "Go to radio homepage", lambda u=stream.homepage: openUrl(u))
        )

    return StandardItem(
        id=f"{md_name}_{stream.name}",
        icon_factory=lambda: Icon.image(icon),
        text=stream.name,
        subtext=stream.description if stream.description else "",
        input_action_text="",
        actions=actions,
    )


def get_as_subtext_field(field, field_title=None) -> str:
    """Get a certain variable as part of the subtext, along with a title for that variable."""
    s = ""
    if field:
        s = f"{field} | "
    else:
        return ""

    if field_title:
        s = f"{field_title} :" + s

    return s

# main plugin class ------------------------------------------------------------
class Plugin(PluginInstance, GeneratorQueryHandler):
    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)

        self.cache_path = Path(self.cacheLocation())
        self.pids_path = self.cache_path / "streams_on"
        self.data_path = Path(self.dataLocation())

        for p in (self.cache_path, self.data_path, self.pids_path):
            p.mkdir(parents=True, exist_ok=True)

        # initialise all available streams and bring up VLC
        init_streams()
        launch_vlc()

    def __del__(self):
        issue_cmd("logout")

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "sax"

    def synopsis(self, query):
        return "some radio"

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        """Yield the radio streams matching the current query."""
        results: List = []

        if len(ctx.query.strip()) <= 1 and is_radio_on():
            results.insert(
                0,
                StandardItem(
                    id=f"{md_name}_stop",
                    icon_factory=lambda: Icon.image(STOP_ICON_PATH),
                    text="Stop Radio",
                    actions=[Action("stop", "Stop Radio", lambda: stop_radio())],
                ),
            )

        reindex_item = StandardItem(
            id=f"{md_name}_repeat",
            icon_factory=lambda: Icon.image(REPEAT_ICON_PATH),
            text="Reindex stations",
            actions=[Action("reindex", "Reindex", lambda: init_streams())],
        )

        restart_item = StandardItem(
            id=f"{md_name}_restart",
            icon_factory=lambda: Icon.image(REPEAT_ICON_PATH),
            text="Restart VLC",
            subtext="Use this when VLC stops responding and no station plays",
            actions=[Action("restart", "Restart VLC", lambda: restart_vlc())],
        )

        try:
            query_str = ctx.query.strip().lower()

            if not query_str:
                results.append(reindex_item)
                results.append(restart_item)
                for stream in streams:
                    results.append(get_as_item(stream))
            else:
                for stream in streams:
                    if query_str in stream.name.lower() or (
                        stream.description and query_str.lower() in stream.description.lower()
                    ):
                        results.append(get_as_item(stream))

                # reindex goes at the end of the list if we are searching for a stream
                results.append(reindex_item)
                results.append(restart_item)

        except Exception:  # user to report error
            trace = traceback.format_exc()
            print(trace)

            results.insert(
                0,
                StandardItem(
                    id="saxophone-error",
                    icon_factory=self.makeIcon,
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        Action(
                            "copy",
                            f"Copy error - report it to {md_url[8:]}",
                            lambda: setClipboardText(trace),
                        )
                    ],
                ),
            )

        yield results


