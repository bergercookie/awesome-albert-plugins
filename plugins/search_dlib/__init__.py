"""
Current file was autogeneratd by the search_template and the `create_googler_plugins.py`
script. In case you find a bug please submit a patch to the aforementioned directories and file
instead.
"""

"""Dlib: Search suggestions for Dlib."""

import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from io import StringIO
from pathlib import Path

from fuzzywuzzy import process

import albertv0 as v0

__iid__ = "PythonInterface/v0.2"
__prettyname__ = "Dlib: Search suggestions for Dlib"
__version__ = "0.1.0"
__trigger__ = "dlib "
__author__ = "Nikos Koukis"
__dependencies__ = []
__homepage__ = "https://github.com/bergercookie/awesome-albert-plugins"

icon_path = str(Path(__file__).parent / "search_dlib")
cache_path = Path(v0.cacheLocation()) / "search_dlib"
config_path = Path(v0.configLocation()) / "search_dlib"
data_path = Path(v0.dataLocation()) / "search_dlib"

# set it to the corresponding site for the search at hand
# see: https://github.com/jarun/googler/blob/master/auto-completion/googler_at/googler_at
googler_at = "dlib.net"

# plugin main functions -----------------------------------------------------------------------


def initialize():
    # Called when the extension is loaded (ticked in the settings) - blocking

    # create plugin locations
    for p in (cache_path, config_path, data_path):
        p.mkdir(parents=False, exist_ok=True)


def finalize():
    pass


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


# I 'm only sending a request to Google once the user has stopped typing, otherwise Google
# blocks my IP.
keys_monitor = KeystrokeMonitor()


def handleQuery(query) -> list:
    results = []

    if not query.isTriggered:
        if not query.string:
            results.append(
                v0.Item(
                    id=__prettyname__,
                    icon=icon_path,
                    text=f'Search {"_".join("search_dlib".split("_")[1:])}',
                    completion=__trigger__,
                )
            )
    else:
        try:
            # be backwards compatible with v0.2
            if "disableSort" in dir(query):
                query.disableSort()

            # setup stage ---------------------------------------------------------------------
            results_setup = setup(query)
            if results_setup:
                return results_setup

            query_str = query.string.strip()

            # too small request - don't even send it.
            if len(query_str) < 2:
                keys_monitor.reset()
                return results

            # determine if we can make the request --------------------------------------------
            keys_monitor.report()
            if keys_monitor.triggered():
                json_results = query_googler(query_str)
                googler_results = [
                    get_googler_result_as_item(googler_result)
                    for googler_result in json_results
                ]

                results.extend(googler_results)

        except Exception:  # user to report error
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


def query_googler(query_str) -> dict:
    """Make a query to googler and return the results in json."""

    li = ["googler", "--unfilter", "--json", query_str]
    if googler_at:
        li = li[:2] + ["-w", googler_at] + li[2:]

    p = subprocess.Popen(li, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    stdout, stder = p.communicate()
    if not stdout:
        return {}
    json_ret = json.load(StringIO(stdout.decode("utf-8")))

    return json_ret


def get_googler_result_as_item(googler_item: dict):
    actions = [
        v0.UrlAction("Open in browser", googler_item["url"]),
        v0.ClipAction("Copy URL", googler_item["url"]),
    ]

    return v0.Item(
        id=__prettyname__,
        icon=icon_path,
        text=googler_item["title"],
        subtext=googler_item["abstract"],
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
    """setup is successful if an empty list is returned.

    Use this function if you need the user to provide you data
    """

    results = []

    if not shutil.which("googler"):
        results.append(
            v0.Item(
                id=__prettyname__,
                icon=icon_path,
                text=f'"googler" is not installed.',
                subtext='Please install and configure "googler" accordingly.',
                actions=[
                    v0.UrlAction('Open "googler" website', "https://github.com/jarun/googler")
                ],
            )
        )
        return results
