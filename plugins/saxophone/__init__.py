"""Saxophone - Play internet radio streams from albert."""

# TODO - Enable using dbus-send for wm widget integration
import json
import operator
import os
import random
import traceback
from enum import Enum
from pathlib import Path
from typing import List, Optional

import albert as v0
import mpv

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

dev_mode = False

# Stream class --------------------------------------------------------------------------------


def enum(*sequential, **named) -> Enum:
    """
    Return a Python Enum with automatic enumeration.

    Usage::

    >>> Numbers = enum('ZERO', 'ONE', 'TWO')
    >>> Numbers.ZERO
    0
    >>> Numbers.ONE
    1
    >>> Numbers.TWO
    2
    """
    enums = dict(zip(sequential, range(len(sequential))), **named)
    return type("Enum", (), enums)


UrlType = enum("PLAYLIST", "RAW_STREAM", "COUNT", "INVALID")


class Stream:
    def __init__(self, url: str, name: str, **kargs):
        super(Stream, self).__init__()

        self.url: str = url
        self.name: str = name
        self.description: str = kargs.get("description")
        self.homepage: str = kargs.get("homepage")
        self._icon: str = kargs.get("icon")
        self.favorite: bool = kargs.get("favorite", False)

        self._process: subprocess.Popen = None

        self._url_type: UrlType = None
        if self.url.endswith(".pls") or self.url.endswith(".m3u"):
            self._url_type = UrlType.PLAYLIST
        else:
            self._url_type = UrlType.RAW_STREAM

        self.player = mpv.MPV(config=False, log_handler=self.debug_print)
        # TODO `on_metadata_change callback crashes the app -> SIGSEGV
        # self.player.observe_property("metadata", self.on_metadata_change)

    def on_metadata_change(self, name, value):
        if value:
            notify("Saxophone", value.get("icy-title", ""), self.icon())

        # Send to dbus

    def debug_print(self, loglevel, component, message):
        print(f"[{loglevel}] {component}: {message}")

    def url_type(self) -> UrlType:  # type: ignore
        return self._url_type

    def is_on(self) -> bool:
        return self.player.idle_active == False

    def icon(self) -> Optional[str]:
        """Cache the icon."""
        if self._icon is None:
            return None

        return get_icon(self._icon)

    def play(self):
        self.player.play(self.url)

    def stop(self):
        self.player.stop()


streams: List[Stream] = []


def init_streams():
    global streams
    streams.clear()

    with open(json_config) as f:
        conts = json.load(f)

        for item in conts["all"]:
            streams.append(Stream(**item))
    sort_fn(streams)


# initialise all available streams
init_streams()


# plugin main functions -----------------------------------------------------------------------


def check_pid(pid: int) -> bool:
    """Check For the existence of a unix pid."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True


def is_radio_on() -> bool:
    """Check if any of the streams are on."""
    return any([s.is_on() for s in streams])


def stop_radio():
    """Turn off the radio."""
    for s in streams:
        s.stop()


def start_stream(stream: Stream):
    """Stop any running stream, then start the indicated one."""

    if stream.is_on():
        return

    stop_radio()
    stream.play()


# albert functions ----------------------------------------------------------------------------


def initialize():
    # Called when the extension is loaded (ticked in the settings) - blocking

    # create plugin locations
    for p in (cache_path, data_path, pids_path):
        p.mkdir(parents=False, exist_ok=True)


def finalize():
    pass


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
