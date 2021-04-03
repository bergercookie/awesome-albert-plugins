"""
Current file was autogeneratd by the search_template and the `create_googler_plugins.py`
script. In case you find a bug please submit a patch to the aforementioned directories and file
instead.
"""

"""{{ cookiecutter.plugin_short_description }}."""

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

import albert as v0

__title__ = "{{ cookiecutter.plugin_short_description }}"
__version__ = "0.4.0"
__triggers__ = "{{ cookiecutter.trigger }} "
__authors__ = "Nikos Koukis"
__homepage__ = "https://github.com/bergercookie/awesome-albert-plugins"
__exec_deps__ = []
__py_deps__ = []

icon_path = str(Path(__file__).parent / "{{ cookiecutter.plugin_name }}")
cache_path = Path(v0.cacheLocation()) / "{{ cookiecutter.plugin_name }}"
config_path = Path(v0.configLocation()) / "{{ cookiecutter.plugin_name }}"
data_path = Path(v0.dataLocation()) / "{{ cookiecutter.plugin_name }}"

# set it to the corresponding site for the search at hand
# see: https://github.com/jarun/googler/blob/master/auto-completion/googler_at/googler_at
googler_at = "{{ cookiecutter.googler_at }}"

# special way to handle the url? --------------------------------------------------------------
url_handler = "{{ cookiecutter.url_handler }}"

url_handler_check_cmd = "{{ cookiecutter.url_handler_check_cmd }}"
if url_handler_check_cmd:
    p = subprocess.Popen(url_handler_check_cmd, shell=True)
    p.communicate()
    if p.returncode != 0:
        print(
            f'[W] Disabling the url handler "{url_handler}"... - Condition {url_handler_check_cmd} not met'
        )
        url_handler = None


url_handler_desc = "{{ cookiecutter.url_handler_description }}"
if not url_handler_desc:
    url_handler_desc = "Run special action"

# browser -------------------------------------------------------------------------------------
# look for google-chrome first
inco_browser = shutil.which("google-chrome")
if not inco_browser:
    inco_browser = shutil.which("chromium-browser")

if inco_browser:
    inco_cmd = lambda url: subprocess.Popen([inco_browser, "--incognito", url])
else:
    inco_cmd = None


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
        if {{ cookiecutter.show_on_top_no_trigger }}:
            if not query.string:
                results.append(
                    v0.Item(
                        id=__title__,
                        icon=icon_path,
                        text=f'Search {"_".join("{{ cookiecutter.plugin_name }}".split("_")[1:])}',
                        completion=__triggers__,
                    )
                )
    else:
        try:
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

                if not results:
                    results.insert(
                        0,
                        v0.Item(
                            id=__title__, icon=icon_path, text="No results.", actions=[],
                        ),
                    )

        except Exception:  # user to report error
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

    # incognito search
    if inco_cmd:
        actions.insert(
            1,
            v0.FuncAction(
                "Open in browser [incognito mode]",
                lambda url=googler_item["url"]: inco_cmd(url),
            ),
        )

    # special url handler
    if url_handler:
        # check that the handler is actually there
        actions.insert(
            0,
            v0.FuncAction(
                url_handler_desc,
                lambda url_handler=url_handler: subprocess.Popen(
                    f'{url_handler} {googler_item["url"]}', shell=True
                ),
            ),
        )

    return v0.Item(
        id=__title__,
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
                id=__title__,
                icon=icon_path,
                text=f'"googler" is not installed.',
                subtext='Please install and configure "googler" accordingly.',
                actions=[
                    v0.UrlAction('Open "googler" website', "https://github.com/jarun/googler")
                ],
            )
        )
        return results
