"""Errno operations."""

import subprocess
import sys
import traceback
from pathlib import Path
from typing import Dict, Tuple

import albert as v0

__title__ = "Errno lookup operations"
__version__ = "0.4.0"
__triggers__ = "err "
__authors__ = "Nikos Koukis"
__homepage__ = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins//errno_lookup"
)

icon_path = str(Path(__file__).parent / "errno_lookup")

cache_path = Path(v0.cacheLocation()) / "errno_lookup"
config_path = Path(v0.configLocation()) / "errno_lookup"
data_path = Path(v0.dataLocation()) / "errno_lookup"

lines = [
    li.split(maxsplit=2)
    for li in subprocess.check_output(["errno", "--list"]).decode("utf-8").splitlines()
]
codes_d: Dict[str, Tuple[str, str]] = {li[1]: (li[0], li[2]) for li in lines}
dev_mode = False

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
            query.disableSort()

            results_setup = setup(query)
            if results_setup:
                return results_setup

            query_str: str = query.string
            for item in codes_d.items():
                if query_str in item[0]:
                    results.append(get_as_item(item))
                else:
                    for v in item[1]:
                        if query_str.lower() in v.lower():
                            results.append(get_as_item(item))
                            break

        except Exception:  # user to report error
            if dev_mode:
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


def get_as_item(t: Tuple[str, Tuple[str, str]]):
    return v0.Item(
        id=__title__,
        icon=icon_path,
        text=f"{t[0]} - {t[1][0]}",
        subtext=f"{t[1][1]}",
        completion="",
        actions=[],
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
