"""{{ cookiecutter.plugin_short_description }}."""

from pathlib import Path
from typing import List, Dict
import os
import shutil
import subprocess
import sys
import time
import traceback

from fuzzywuzzy import process
{%- if cookiecutter.use_notifications == 'y' %}
from gi.repository import GdkPixbuf, Notify
{%- endif %}

import albert as v0

__title__ = "{{ cookiecutter.plugin_short_description }}"
__version__ = "0.4.0"
__triggers__ = "{{ cookiecutter.trigger }} "
__authors__ = "{{ cookiecutter.author }}"
__homepage__ = "{{ cookiecutter.repo_base_url }}/{{ cookiecutter.plugin_name }}"
__exec_deps__ = []
__py_deps__ = []

icon_path = str(Path(__file__).parent / "{{ cookiecutter.plugin_name }}")

cache_path = Path(v0.cacheLocation()) / "{{ cookiecutter.plugin_name }}"
config_path = Path(v0.configLocation()) / "{{ cookiecutter.plugin_name }}"
data_path = Path(v0.dataLocation()) / "{{ cookiecutter.plugin_name }}"
dev_mode = True

{%- if cookiecutter.include_keystroke_monitor == 'y' %}
# KeystrokeMonitor clss -----------------------------------------------------------------------
class KeystrokeMonitor:
    def __init__(self):
        super(KeystrokeMonitor, self)
        self.thres = 0.3  # s
        self.prev_time = time.time()
        self.curr_time = time.time()

    def report(self):
        self.prev_time = time.time()
        self.curr_time = time.time()
        self.report = self.report_after_first

    def report_after_first(self):
        # update prev, curr time
        self.prev_time = self.curr_time
        self.curr_time = time.time()

    def triggered(self) -> bool:
        return self.curr_time - self.prev_time > self.thres

    def reset(self) -> None:
        self.report = self.report_after_first
{%- endif %}

# Do not flood the web server with queries, otherwise it may block your IP.
keys_monitor = KeystrokeMonitor()

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
            # be backwards compatible with v0.2
            if "disableSort" in dir(query):
                query.disableSort()

            results_setup = setup(query)
            if results_setup:
                return results_setup

            query_str = query.string

{%- if cookiecutter.include_keystroke_monitor == 'y' %}
            if len(query_str) < 2:
                keys_monitor.reset()
                return results

            keys_monitor.report()
            if keys_monitor.triggered():
                # modify this...
                results.append(get_as_item())
{%- else %}
            # modify this...
            results.append(get_as_item())
{%- endif %}

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

{%- if cookiecutter.use_notifications == 'y' %}
def notify(
     msg: str, app_name: str=__title__, image=str(icon_path),
):
    Notify.init(app_name)
    n = Notify.Notification.new(app_name, msg, image)
    n.show()
{%- endif %}

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
