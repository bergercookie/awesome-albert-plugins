"""HTTP URL Lookup operations."""

import sys
import traceback
from typing import Tuple
from pathlib import Path

import requests

import albert as v0

md_name = "HTTP URL Lookup codes"
md_description = "HTTP URL Lookup codes and their description such as 404, 301, etc."
md_iid = "0.5"
md_version = "0.2"
md_maintainers = "Nikos Koukis"
md_url = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins//url_lookup"
)

icon_path = str(Path(__file__).parent / "url_lookup")

cache_path = Path(v0.cacheLocation()) / "url_lookup"
config_path = Path(v0.configLocation()) / "url_lookup"
data_path = Path(v0.dataLocation()) / "url_lookup"

codes_d = {str(k): v for k, v in requests.status_codes._codes.items()}

# plugin main functions -----------------------------------------------------------------------


# supplementary functions ---------------------------------------------------------------------


def get_as_item(t: Tuple[str, tuple]):
    return v0.Item(
        id=md_name,
        icon=[icon_path],
        text=f"{t[0]} - {t[1][0]}",
        subtext="",
        completion="",
        actions=[
            UrlAction("More info", f"https://httpstatuses.com/{t[0]}"),
        ],
    )


def save_data(data: str, data_name: str):
    """Save a piece of data in the configuration directory."""
    with open(config_path / data_name, "w") as f:
        f.write(data)


def load_data(data_name) -> str:
    """Load a piece of data from the configuration directory."""
    with open(config_path / data_name, "r") as f:
        data = f.readline().strip().split()[0]

    return data


# helpers for backwards compatibility ------------------------------------------
class UrlAction(v0.Action):
    def __init__(self, name: str, url: str):
        super().__init__(name, name, lambda: v0.openUrl(url))


class ClipAction(v0.Action):
    def __init__(self, name, copy_text):
        super().__init__(name, name, lambda: v0.setClipboardText(copy_text))


class FuncAction(v0.Action):
    def __init__(self, name, command):
        super().__init__(name, name, command)


# main plugin class ------------------------------------------------------------
class Plugin(v0.QueryHandler):
    def id(self) -> str:
        return __name__

    def name(self) -> str:
        return md_name

    def description(self):
        return md_description

    def defaultTrigger(self):
        return "url "

    def synopsis(self):
        return "some url code e.g., 404"

    def finalize(self):
        pass

    def initialize(self):
        # Called when the extension is loaded (ticked in the settings) - blocking

        # create plugin locations
        for p in (cache_path, config_path, data_path):
            p.mkdir(parents=False, exist_ok=True)

    def handleQuery(self, query) -> None:
        results = []

        try:
            query_str = query.string
            for item in codes_d.items():
                if query_str in item[0]:
                    results.append(get_as_item(item))
                else:
                    # multiple descriptions per code
                    for v in item[1]:
                        if query_str in v:
                            results.append(get_as_item(item))
                            break

        except Exception:  # user to report error
            v0.critical(traceback.format_exc())
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
