"""
Current file was autogeneratd by the search_template and the `create_ddgr_plugins.py`
script. In case you find a bug please submit a patch to the aforementioned directories and file
instead.
"""

"""{{ cookiecutter.plugin_short_description }}."""

import json
import shutil
import subprocess
import traceback
from io import StringIO
from pathlib import Path
from typing import Dict, Sequence, Tuple

import albert as v0

md_iid = "0.5"
md_version = "0.2"
md_name = "Search - {{ cookiecutter.plugin_name }}"
md_description = "{{ cookiecutter.plugin_short_description }}"
md_maintainers = "Nikos Koukis"
md_url = "https://github.com/bergercookie/awesome-albert-plugins"
md_bin_dependencies = ["ddgr"]
md_lib_dependencies = []

icon_path = str(Path(__file__).parent / "{{ cookiecutter.plugin_name }}")
cache_path = Path(v0.cacheLocation()) / "{{ cookiecutter.plugin_name }}"
config_path = Path(v0.configLocation()) / "{{ cookiecutter.plugin_name }}"
data_path = Path(v0.dataLocation()) / "{{ cookiecutter.plugin_name }}"

# set it to the corresponding site for the search at hand
# e.g.,: https://github.com/jarun/googler/blob/master/auto-completion/googler_at/googler_at
ddgr_at = "{{ cookiecutter.ddgr_at }}"

# special way to handle the url? --------------------------------------------------------------
url_handler = "{{ cookiecutter.url_handler }}"

url_handler_check_cmd = "{{ cookiecutter.url_handler_check_cmd }}"
if url_handler_check_cmd:
    p = subprocess.Popen(url_handler_check_cmd, shell=True)
    p.communicate()
    if p.returncode != 0:
        print(
            f'[W] Disabling the url handler "{url_handler}"... - Condition'
            f" {url_handler_check_cmd} not met"
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


# supplementary functions ---------------------------------------------------------------------
def query_ddgr(query_str) -> Tuple[Sequence[Dict[str, str]], str]:
    """Make a query to ddgr and return the results in json."""

    li = ["ddgr", "--noprompt", "--unsafe", "--json", query_str]
    if ddgr_at:
        li = li[:2] + ["-w", ddgr_at] + li[2:]

    p = subprocess.Popen(li, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    stdout, stderr = p.communicate()
    if stdout:
        json_ret = json.load(StringIO(stdout.decode("utf-8")))
    else:
        json_ret = [dict()]

    stderr = stderr.decode("utf-8")
    return json_ret, stderr


def get_ddgr_result_as_item(ddgr_item: dict):
    actions = [
        UrlAction("Open in browser", ddgr_item["url"]),
        ClipAction("Copy URL", ddgr_item["url"]),
    ]

    # incognito search
    if inco_cmd:
        actions.insert(
            1,
            FuncAction(
                "Open in browser [incognito mode]",
                lambda url=ddgr_item["url"]: inco_cmd(url),  # type: ignore
            ),
        )

    # special url handler
    if url_handler:
        # check that the handler is actually there
        actions.insert(
            0,
            FuncAction(
                url_handler_desc,
                lambda url_handler=url_handler: subprocess.Popen(
                    f'{url_handler} {ddgr_item["url"]}', shell=True
                ),
            ),
        )

    return v0.Item(
        id=md_name,
        icon=[icon_path],
        text=ddgr_item["title"],
        subtext=ddgr_item["abstract"],
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


def save_data(data: str, data_name: str):
    """Save a piece of data in the configuration directory."""
    with open(config_path / data_name, "w") as f:
        f.write(data)


def load_data(data_name) -> str:
    """Load a piece of data from the configuration directory."""
    with open(config_path / data_name, "r") as f:
        data = f.readline().strip().split()[0]

    return data


def setup(query) -> bool:
    """setup is successful if an empty list is returned.

    Use this function if you need the user to provide you data
    """

    results = []

    if not shutil.which("ddgr"):
        results.append(
            v0.Item(
                id=md_name,
                icon=icon_path,
                text='"ddgr" is not installed.',
                subtext='Please install and configure "ddgr" accordingly.',
                actions=[
                    UrlAction(
                        'Open "ddgr" installation instructions',
                        "https://github.com/jarun/ddgr#installation=",
                    )
                ],
            )
        )

        query.add(results)
        return True

    return False


# helpers for backwards compatibility ---------------------------------------------------------
class UrlAction(v0.Action):
    def __init__(self, name: str, url: str):
        super().__init__(name, name, lambda: v0.openUrl(url))


class ClipAction(v0.Action):
    def __init__(self, name: str, copy_text: str):
        super().__init__(name, name, lambda: v0.setClipboardText(copy_text))


class FuncAction(v0.Action):
    def __init__(self, name: str, command):
        super().__init__(name, name, command)


# main plugin class ---------------------------------------------------------------------------
class Plugin(v0.QueryHandler):
    def id(self) -> str:
        return __name__

    def name(self) -> str:
        return md_name

    def description(self):
        return md_description

    def defaultTrigger(self):
        return "{{ cookiecutter.trigger }} "

    def synopsis(self):
        return "query text."

    def initialize(self):
        # Called when the extension is loaded (ticked in the settings) - blocking

        # create plugin locations
        for p in (cache_path, config_path, data_path):
            p.mkdir(parents=False, exist_ok=True)

    def finalize(self):
        pass

    def handleQuery(self, query) -> None:
        results = []

        try:
            # setup stage ---------------------------------------------------------------------
            did_setup = setup(query)
            if did_setup:
                return

            query_str = query.string.strip()

            # too small request - don't even send it.
            if len(query_str) < 2:
                return

            # determine if we can make the request --------------------------------------------
            if not query_str.endswith("."):
                query.add(
                    v0.Item(
                        id=md_name,
                        icon=[icon_path],
                        text="typing...",
                        subtext='Add a dot to the end of the query "." to trigger the search',
                        actions=[],
                    ),
                )
                return

            query_str = query_str[:-1].strip()

            # proceed, fill the results then query.add that only at the end -------------------

            # send request
            json_results, stderr = query_ddgr(query_str)

            ddgr_results = [
                get_ddgr_result_as_item(ddgr_result) for ddgr_result in json_results
            ]

            results.extend(ddgr_results)

            if not results:
                results.insert(
                    0,
                    v0.Item(
                        id=md_name,
                        icon=[icon_path],
                        text="No results.",
                        subtext=stderr if stderr else "",
                        actions=[],
                    ),
                )

        except Exception:  # user to report error
            print(traceback.format_exc())

            results.insert(
                0,
                v0.Item(
                    id=md_name,
                    icon=[icon_path],
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        ClipAction(
                            f"Copy error - report it to {md_url[8:]}",
                            f"{traceback.format_exc()}",
                        )
                    ],
                ),
            )

        query.add(results)
