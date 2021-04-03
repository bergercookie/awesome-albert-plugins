"""Kill a process v2."""

import fnmatch
import os
import re
import shutil
import signal
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Dict, List, Optional

import psutil
from fuzzywuzzy import process
from gi.repository import GdkPixbuf, Notify
from psutil import Process

import albert as v0

__title__ = "Kill Process v2"
__version__ = "0.4.0"
__triggers__ = "kill "
__authors__ = "Nikos Koukis"
__homepage__ = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/killproc"
)

icon_path = str(Path(__file__).parent / "logo.png")

cache_path = Path(v0.cacheLocation()) / "killproc"
config_path = Path(v0.configLocation()) / "killproc"
data_path = Path(v0.dataLocation()) / "killproc"
dev_mode = True

# plugin main functions -----------------------------------------------------------------------


def initialize():
    """Called when the extension is loaded (ticked in the settings) - blocking."""

    # create plugin locations
    for p in (cache_path, config_path, data_path):
        p.mkdir(parents=False, exist_ok=True)


def finalize():
    pass


def handleQuery(query) -> list:
    """Hook that is called by albert with *every new keypress*."""  # noqa
    results = []

    if query.isTriggered:
        try:
            query.disableSort()

            results_setup = setup(query)
            if results_setup:
                return results_setup

            query_str = query.string.strip()

            cmdline_to_procs = get_cmdline_to_procs()
            matched = [
                elem[0]
                for elem in process.extract(query_str, cmdline_to_procs.keys(), limit=15)
            ]

            extra_actions = []
            if any([symbol in query_str for symbol in "*?[]"]):
                extra_actions = [
                    v0.FuncAction(
                        "Terminate by glob",
                        lambda: list(
                            map(lambda p: p.terminate(), globsearch_procs(query_str))
                        ),
                    ),
                    v0.FuncAction(
                        "Kill by glob",
                        lambda: list(map(lambda p: p.kill(), globsearch_procs(query_str))),
                    ),
                ]
            for m in matched:
                for p in cmdline_to_procs[m]:
                    results.append(get_as_item(p, *extra_actions))

            # filtering step
            results = [r for r in results if r is not None]

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


def notify(
    msg: str, app_name: str=__title__, image=str(icon_path),
):
    Notify.init(app_name)
    n = Notify.Notification.new(app_name, msg, image)
    n.show()


def cmdline(p: Process) -> str:
    """There must be a bug in psutil and sometimes `cmdline()` raises an exception. I don't
        want that, so I'll override this behavior for now.
    """
    try:
        return " ".join(p.cmdline())
    except psutil.NoSuchProcess:
        return ""


def procs() -> List[Process]:
    """Get a list of all the processes."""
    return list(psutil.process_iter())


def globsearch_procs(s: str) -> List[Process]:
    """Return a list of processes whose command line matches the given glob."""
    pat = re.compile(fnmatch.translate(s))

    procs_ = procs()
    procs_out = list(filter(lambda p: re.search(pat, cmdline(p)) is not None, procs_))
    notify(msg=f"Glob search returned {len(procs_out)} matching processes")
    return procs_out


def get_cmdline_to_procs() -> Dict[str, List[Process]]:
    """Return a Dictionary of command-line args string to all the corresponding processes with
    that."""
    procs_ = procs()
    out = {cmdline(p): [] for p in procs_}
    for p in procs_:
        out[cmdline(p)].append(p)

    return out


def kill_by_name(name: str, signal=signal.SIGTERM):
    """Kill all the processes whose name matches the given one."""
    procs_ = procs()
    for p in filter(lambda p: p.name() == name, procs_):
        p.send_signal(signal)


def get_as_item(p: Process, *extra_actions):
    """Return an item - ready to be appended to the items list and be rendered by Albert.

    if Process is not a valid object (.name or .cmdline raise an exception) then return None
    """
    name_field = cmdline(p)

    if not name_field:
        return None

    try:

        actions = [
            v0.FuncAction("Terminate", lambda: p.terminate()),
            v0.FuncAction("Kill", lambda: p.kill()),
            v0.ClipAction("Get PID", f"{p.pid}"),
            v0.FuncAction(
                "Terminate matching names",
                lambda name=p.name(): kill_by_name(name, signal=signal.SIGTERM),
            ),
            v0.FuncAction("Kill matching names", lambda name=p.name(): kill_by_name(name)),
        ]
        actions = [*extra_actions, *actions]
        return v0.Item(
            id=__title__,
            icon=icon_path,
            text=name_field,
            subtext="",
            completion=p.name(),
            actions=actions,
        )
    except psutil.NoSuchProcess:
        return None


def sanitize_string(s: str) -> str:
    return s.replace("<", "&lt;")


def get_as_subtext_field(field, field_title=None) -> str:
    """Get a certain variable as part of the subtext, along with a title for that variable."""
    s = ""
    if field:
        s = f"{field} | "
    else:
        return ""

    if field_title:
        s = f"{field_title}: " + s

    return s


def save_data(data: str, data_name: str):
    """Save a piece of data in the configuration directory."""
    with open(config_path / data_name, "w") as f:
        f.write(data)


def load_data(data_name) -> str:
    """Load a piece of data from the configuration directory."""
    with open(config_path / data_name, "r") as f:
        data = f.readline().strip().split()[0]

    return data


def setup(query):
    """Setup is successful if an empty list is returned.

    Use this function if you need the user to provide you data
    """

    results = []
    return results
