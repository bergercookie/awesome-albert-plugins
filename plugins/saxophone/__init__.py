"""Saxophone - Play internet radio streams from albert."""

import json
import operator
import os
import subprocess
import time
import traceback
from enum import Enum
from pathlib import Path
from typing import List, Optional

from loguru import logger

import albertv0 as v0

__iid__ = "PythonInterface/v0.2"
__prettyname__ = "Saxophone - Play internet radio streams from albert"
__version__ = "0.1.0"
__trigger__ = "sax"
__author__ = "Nikos Koukis"
__dependencies__ = ["cvlc"]
__homepage__ = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins//saxophone"
)

icons_path = Path(__file__).parent / "images"


def get_icon(icon: str):
    return str(icons_path / icon)


icon_path = get_icon("saxophone")
stop_icon_path = get_icon("stop_icon")

cache_path = Path(v0.cacheLocation()) / "saxophone"
data_path = Path(v0.dataLocation()) / "saxophone"

json_config = str(Path(__file__).parent / "config" / "saxophone.json")
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
        print("self.favorite: ", self.favorite)

        self._process: subprocess.Popen = None

        self._url_type: UrlType = None
        if self.url.endswith(".pls") or self.url.endswith(".m3u"):
            self._url_type = UrlType.PLAYLIST
        else:
            self._url_type = UrlType.RAW_STREAM

    def url_type(self) -> UrlType:
        return self._url_type

    def is_on(self) -> bool:
        if self._process is None:
            return False

        # if poll() is None then it's running!
        return self._process.poll() is None

    def icon(self) -> Optional[Path]:
        """Cache the icon."""
        if self._icon is None:
            return None

        return get_icon(self._icon)

    def play(self):
        self._process = subprocess.Popen(["cvlc", self.url])

    def stop(self) -> None:
        logger.warning(f'Stopping Stream "{self.name}"')

        if not self._process:
            logger.warning(f'Stream "{self.name}" does not seem to be active.')
            return

        self._process.terminate()
        self._process.communicate()


# initialise all available streams
streams: List[Stream] = []
with open(json_config) as f:
    conts = json.load(f)

    for item in conts["all"]:
        streams.append(Stream(**item))
streams.sort(key=operator.attrgetter("favorite"), reverse=True)


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
    return any([stream.is_on() for stream in streams])


def stop_radio():
    """Turn of the radio."""
    for stream in streams:
        if stream.is_on():
            stream.stop()
            return

    return  # no radio was active


def start_stream(stream: Stream):
    """Stop any running stream, then start the indicated one."""

    if stream.is_on():
        logger.info(f'Stream "{stream.name}" is already on')
        return

    stop_radio()
    stream.play()


# TODO  - Move json file inside the repo
# TODO  - Icons - configure properly - move them to misc directory
# TODO  - Add to enums - handle m3u, pls, raw
# TODO  - System notification
# TODO  - System tray notification
# TODO  - Check the links as part of CI

# albert functions ----------------------------------------------------------------------------


def initialize():
    # Called when the extension is loaded (ticked in the settings) - blocking

    # create plugin locations
    for p in (cache_path, data_path):
        p.mkdir(parents=False, exist_ok=True)


def finalize():
    pass


def handleQuery(query) -> list:  # noqa
    results = []

    if len(query.rawString.strip()) <= 1 and is_radio_on():
        results.insert(
            0,
            v0.Item(
                id=__prettyname__,
                icon=stop_icon_path,
                text="Stop Radio",
                actions=[v0.FuncAction("Stop Radio", lambda: stop_radio())],
            ),
        )

    if query.isTriggered:
        try:
            # be backwards compatible with v0.2
            if "disableSort" in dir(query):
                query.disableSort()

            results_setup = setup(query)
            if results_setup:
                return results_setup

            query_str = query.string.strip().lower()

            if not query_str:
                for stream in streams:
                    results.append(get_as_item(stream))
            else:
                for stream in streams:
                    if query_str in stream.name.lower() or (
                        stream.description and stream.description.lower()
                    ):
                        results.append(get_as_item(stream))

        except Exception:  # user to report error
            if dev_mode:  # let exceptions fly!
                print(traceback.format_exc())
                raise

            results.insert(
                0,
                v0.Item(
                    id=__prettyname__,
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
        id=__prettyname__,
        icon=icon,
        text=stream.name,
        subtext=stream.description if stream.description else "",
        completion="",
        actions=actions,
    )


def get_as_subtext_field(field, field_title=None) -> str:
    """Get a certain variable as part of the subtext, along with a title for that variable.

    """
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
