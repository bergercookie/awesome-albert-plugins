"""Errno operations."""

import subprocess
import traceback
from pathlib import Path
from typing import Dict, Tuple

import albert as v0

md_name = "Errno lookup operations"
md_description = "Lookup error codes alongside their full name and description"
md_iid = "0.5"
md_version = "0.2"
md_maintainers = "Nikos Koukis"
md_url = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins//errno_lookup"
)
md_bin_dependencies = ["errno"]

icon_path = str(Path(__file__).parent / "errno_lookup")

cache_path = Path(v0.cacheLocation()) / "errno_lookup"
config_path = Path(v0.configLocation()) / "errno_lookup"
data_path = Path(v0.dataLocation()) / "errno_lookup"

lines = [
    li.split(maxsplit=2)
    for li in subprocess.check_output(["errno", "--list"]).decode("utf-8").splitlines()
]
codes_d: Dict[str, Tuple[str, str]] = {li[1]: (li[0], li[2]) for li in lines}


# supplementary functions ---------------------------------------------------------------------
def get_as_item(t: Tuple[str, Tuple[str, str]]):
    return v0.Item(
        id=md_name,
        icon=[icon_path],
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
        return "err "

    def synopsis(self):
        return "error number or description ..."

    def initialize(self):
        # create plugin locations
        for p in (cache_path, config_path, data_path):
            p.mkdir(parents=False, exist_ok=True)

    def finalize(self):
        pass

    def handleQuery(self, query) -> None:
        try:
            query_str: str = query.string
            for item in codes_d.items():
                if query_str in item[0]:
                    query.add(get_as_item(item))
                else:
                    for v in item[1]:
                        if query_str.lower() in v.lower():
                            query.add(get_as_item(item))
                            break

        except Exception:  # user to report error
            print(traceback.format_exc())

            query.add(
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
