"""Contact VCF Viewer."""

from pathlib import Path
from typing import List, Dict
import os
import shutil
import subprocess
import sys
import time
import traceback

from fuzzywuzzy import process

import albert as v0

__title__ = "Contact VCF Viewer"
__version__ = "0.4.0"
__triggers__ = "c "
__authors__ = "Nikos Koukis"
__homepage__ = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/contacts"
__exec_deps__ = []
__py_deps__ = []

icon_path = str(Path(__file__).parent / "contacts")

cache_path = Path(v0.cacheLocation()) / "contacts"
config_path = Path(v0.configLocation()) / "contacts"
data_path = Path(v0.dataLocation()) / "contacts"
dev_mode = True

# create plugin locations
for p in (cache_path, config_path, data_path):
    p.mkdir(parents=False, exist_ok=True)
# FileBackedVar class -------------------------------------------------------------------------
class FileBackedVar:
    def __init__(self, varname, convert_fn=str, init_val=None):
        self._fpath = config_path / varname
        self._convert_fn = convert_fn

        if init_val:
            with open(self._fpath, "w") as f:
                f.write(str(init_val))
        else:
            self._fpath.touch()

    def get(self):
        with open(self._fpath, "r") as f:
            return self._convert_fn(f.read().strip())

    def set(self, val):
        with open(self._fpath, "w") as f:
            return f.write(str(val))

# plugin main functions -----------------------------------------------------------------------


def initialize():
    """Called when the extension is loaded (ticked in the settings) - blocking."""
    pass



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

            query_str = query.string
            # modify this...
            results.append(get_as_item())

        except Exception:  # user to report error
            v0.critical(traceback.format_exc())
            if dev_mode:  # let exceptions fly!
                raise
            else:
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

def get_shell_cmd_as_item(
    *, text: str, command: str, subtext: str = None, completion: str = None
):
    """Return shell command as an item - ready to be appended to the items list and be rendered by Albert."""

    if subtext is None:
        subtext = text

    if completion is None:
        completion = f"{__triggers__}{text}"

    def run(command: str):
        proc = subprocess.run(command.split(" "), capture_output=True, check=False)
        if proc.returncode != 0:
            stdout = proc.stdout.decode("utf-8")
            stderr = proc.stderr.decode("utf-8")
            notify(f"Error when executing {command}\n\nstdout: {stdout}\n\nstderr: {stderr}")

    return v0.Item(
        id=__title__,
        icon=icon_path,
        text=text,
        subtext=subtext,
        completion=completion,
        actions=[
            v0.FuncAction(text, lambda command=command: run(command=command)),
        ],
    )

def get_as_item():
    """Return an item - ready to be appended to the items list and be rendered by Albert."""
    return v0.Item(
        id=__title__,
        icon=icon_path,
        text=f"{sys.version}",
        subtext="Python version",
        completion="",
        actions=[
            v0.UrlAction("Open in xkcd.com", "https://www.xkcd.com/"),
            v0.ClipAction("Copy URL", f"https://www.xkcd.com/"),
        ],
    )


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


def load_data(data_name: str) -> str:
    """Load a piece of data from the configuration directory."""
    with open(config_path / data_name, "r") as f:
        data = f.readline().strip().split()[0]

    return data

def data_exists(data_name: str) -> bool:
    """Check whwether a piece of data exists in the configuration directory."""
    return (config_path / data_name).is_file()


def setup(query):
    """Setup is successful if an empty list is returned.

    Use this function if you need the user to provide you data
    """

    results = []
    return results
