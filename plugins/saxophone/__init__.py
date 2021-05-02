"""Saxophone - Play internet radio streams from albert."""

import select
import socket
import json
import operator
import random
import traceback
from enum import Enum
from pathlib import Path
from typing import List, Optional

import albert as v0
import subprocess

import gi  # isort:skip

gi.require_version("Notify", "0.7")  # isort:skip
gi.require_version("GdkPixbuf", "2.0")  # isort:skip
from gi.repository import GdkPixbuf, Notify  # isort:skip

__title__ = "Saxophone - Play internet radio streams from albert"
__version__ = "0.4.0"
__triggers__ = "sax"
__authors__ = "Nikos Koukis"
__homepage__ = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins//saxophone"
)
__exec_deps__ = ["vlc"]

icons_path = Path(__file__).parent / "images"


def get_icon(icon: str):
    return str(icons_path / icon)


def notify(
    app_name: str,
    msg: str,
    image=None,
):
    Notify.init(app_name)
    n = Notify.Notification.new(app_name, msg, image)
    n.show()


def sort_random(streams):
    random.shuffle(streams)


def sort_favorite(streams):
    streams.sort(key=operator.attrgetter("favorite"), reverse=True)


icon_path = get_icon("saxophone")
stop_icon_path = get_icon("stop_icon")
repeat_icon_path = get_icon("repeat_icon")

cache_path = Path(v0.cacheLocation()) / "saxophone"
pids_path = cache_path / "streams_on"
data_path = Path(v0.dataLocation()) / "saxophone"

json_config = str(Path(__file__).parent / "config" / "saxophone.json")

sort_fn = sort_random
# sort_fn = sort_favorite

vlc_socket = Path("/tmp/cvlc.unix")
socket_timeout = 0.2
dev_mode = False

# Classes & supplementary functions -----------------------------------------------------------


class UrlType(Enum):
    PLAYLIST = 0
    RAW_STREAM = 1
    COUNT = 2
    INVALID = 3


def issue_cmd(cmd: str) -> str:
    if not cmd.endswith("\n"):
        cmd += "\n"
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
    if vlc_socket.exists():
        if not vlc_socket.is_socket():
            raise RuntimeError(f'Exected socket file "{vlc_socket}" is not a socket')
        else:
            v0.info("VLC RC Interface is already up.")
    else:
        # communicate over UNIX socket with vlc
        subprocess.Popen(["vlc", "-I", "oldrc", "--rc-unix", vlc_socket])


def is_radio_on() -> bool:
    res = issue_cmd("is_playing")
    return int(res) == 1


def stop_radio():
    """Turn off the radio."""
    res = issue_cmd("stop")
    v0.debug(f"Stopping radio,\n{res}")


def start_stream(stream: Stream):
    res = issue_cmd(f"add {stream.url}")
    v0.debug(f"Starting stream,\n{res}")


# calls ---------------------------------------------------------------------------------------

# initialise all available streams
init_streams()

# launch VLC
launch_vlc()


# albert functions ----------------------------------------------------------------------------


def initialize():
    # Called when the extension is loaded (ticked in the settings) - blocking

    # create plugin locations
    for p in (cache_path, data_path, pids_path):
        p.mkdir(parents=False, exist_ok=True)


def finalize():
    issue_cmd("logout")


def handleQuery(query) -> list:  # noqa
    results = []

    if len(query.rawString.strip()) <= 1 and is_radio_on():
        results.insert(
            0,
            v0.Item(
                id=__title__,
                icon=stop_icon_path,
                text="Stop Radio",
                actions=[v0.FuncAction("Stop Radio", lambda: stop_radio())],
            ),
        )

    reindex_item = v0.Item(
        id=__title__,
        icon=repeat_icon_path,
        text="Reindex stations",
        actions=[v0.FuncAction("Reindex", lambda: init_streams())],
    )

    if query.isTriggered:
        try:
            query.disableSort()

            results_setup = setup(query)
            if results_setup:
                return results_setup

            query_str = query.string.strip().lower()

            if not query_str:
                results.append(reindex_item)
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

        except Exception:  # user to report error
            if dev_mode:  # let exceptions fly!
                print(traceback.format_exc())
                raise

            results.insert(
                0,
                v0.Item(
                    id=__title__,
                    icon=icon_path,
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        v0.ClipAction(
                            f"Copy error - report it to {__homepage__[8:]}",
                            f"{traceback.format_exc()}",
                        )
                    ],
                ),
            )

    return results


# supplementary functions ---------------------------------------------------------------------


def get_as_item(stream: Stream):
    icon = stream.icon() or icon_path
    actions = [v0.FuncAction("Play", lambda stream=stream: start_stream(stream))]
    if stream.homepage:
        actions.append(v0.UrlAction("Go to radio homepage", stream.homepage))

    return v0.Item(
        id=__title__,
        icon=icon,
        text=stream.name,
        subtext=stream.description if stream.description else "",
        completion="",
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


def setup(query):
    """setup is successful if an empty list is returned.

    Use this function if you need the user to provide you data
    """

    results = []
    return results
