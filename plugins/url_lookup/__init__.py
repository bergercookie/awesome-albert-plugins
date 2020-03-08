"""HTTP URL Lookup operations."""

import sys
import traceback
from typing import Tuple
from pathlib import Path

import requests

import albertv0 as v0

__iid__ = "PythonInterface/v0.2"
__prettyname__ = "HTTP URL Lookup operations"
__version__ = "0.1.0"
__trigger__ = "url "
__author__ = "Nikos Koukis"
__dependencies__ = []
__homepage__ = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins//url_lookup"
)

icon_path = str(Path(__file__).parent / "url_lookup")

cache_path = Path(v0.cacheLocation()) / "url_lookup"
config_path = Path(v0.configLocation()) / "url_lookup"
data_path = Path(v0.dataLocation()) / "url_lookup"

codes_d = {str(k): v for k, v in requests.status_codes._codes.items()}

# plugin main functions -----------------------------------------------------------------------


def initialize():
    # Called when the extension is loaded (ticked in the settings) - blocking

    # create plugin locations
    for p in (cache_path, config_path, data_path):
        p.mkdir(parents=False, exist_ok=True)


def finalize():
    pass


def handleQuery(query) -> list:
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


def get_as_item(t: Tuple[str, tuple]):
    return v0.Item(
        id=__prettyname__,
        icon=icon_path,
        text=f"{t[0]} - {t[1][0]}",
        subtext="",
        completion="",
        actions=[
            v0.UrlAction("More info", f"https://httpstatuses.com/{t[0]}"),
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


def setup(query):
    """setup is successful if an empty list is returned.

    Use this function if you need the user to provide you data
    """

    results = []
    return results
