"""Launch the GMaps route planner."""

import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Tuple

from fuzzywuzzy import process

import albertv0 as v0

__iid__ = "PythonInterface/v0.2"
__prettyname__ = "GMaps - Launch route planner"
__version__ = "0.1.0"
__trigger__ = "gmaps "
__author__ = "Nikos Koukis"
__dependencies__ = []
__homepage__ = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins//gmaps"
)

icon_path = v0.iconLookup("gmaps")
if not icon_path:
    icon_path = os.path.join(os.path.dirname(__file__), "gmaps")

cache_path = Path(v0.cacheLocation()) / "gmaps"
config_path = Path(v0.configLocation()) / "gmaps"
data_path = Path(v0.dataLocation()) / "gmaps"
gmaps_exe = Path(__file__).parent / "gmaps-cli" / "gmaps-cli.py"

available_means = ["walk", "drive", "bicycle", "fly", "transit"]
default_means = "transit"

# plugin main functions -----------------------------------------------------------------------


def initialize():
    # Called when the extension is loaded (ticked in the settings) - blocking

    # create plugin locations
    for p in (cache_path, config_path, data_path):
        p.mkdir(parents=False, exist_ok=True)


def finalize():
    pass


def handleQuery(query):
    results = []

    if query.isTriggered:
        # try:
        # be backwards compatible with v0.2
        if "disableSort" in dir(query):
            query.disableSort()

        results_setup = setup(query)
        if results_setup:
            return results_setup

        query_str = query.string
        src, dst = extract_src_dst(query_str)
        if src and dst:
            actions = []
            import pdb; pdb.set_trace()
            for m in available_means:
                actions.append(
                    v0.FuncAction(
                        m.capitalize(),
                        lambda src=src, dst=dst, m=m: spawn_and_launch_route(src, dst, means=m)
                    )
                )

            results.append(
                v0.Item(
                    id=__prettyname__,
                    icon=icon_path,
                    text=f"Open route (takes ~5s)",
                    subtext=f"{src} -> {dst}",
                    actions=actions,
                )
            )

        # except Exception:  # user to report error
        #     results.insert(
        #         0,
        #         v0.Item(
        #             id=__prettyname__,
        #             icon=icon_path,
        #             text="Something went wrong! Press [ENTER] to copy error and report it",
        #             actions=[
        #                 v0.ClipAction(
        #                     f"Copy error - report it to {__homepage__[8:]}",
        #                     f"{sys.exc_info()}",
        #                 )
        #             ],
        #         ),
        #     )

    return results


# supplementary functions ---------------------------------------------------------------------


def extract_src_dst(query_str) -> Tuple[str, str]:
    """.. raises:: RuntimeError on invalid query."""
    src_str = "from"
    dst_str = "to"

    src = ""
    dst = ""

    def get_string_between(str1, str2):
        after_str1 = query_str.split(str1)
        if len(after_str1) == 1:
            return ""  # str1 not detected
        elif len(after_str1) > 2:
            raise RuntimeError(f'Invalid query - multiple "{str1}" specified')
        else:
            after_str1 = after_str1[1]
            return after_str1.split(str2)[0].strip()

    src = get_string_between(src_str, dst_str)
    dst = get_string_between(dst_str, src_str)

    return src, dst


def spawn_and_launch_route(src: str = "", dst: str = "", means: str = default_means) -> None:
    t = threading.Thread(target=launch_route, kwargs={"src": src, "dst": dst, "means": means})
    t.start()


def launch_route(src, dst, means):
    """Launch Google Maps for the specified route."""

    p = subprocess.Popen(
        [gmaps_exe, "route", "--source", src, "--destination", dst, "-o", "-t", default_means],
        stdout=subprocess.PIPE,
    )
    stdout, stderr = p.communicate()
    url = stdout.decode("utf-8").split(": ")[-1].strip()
    print("p.returncode: ", p.returncode)
    print("url: ", url)


def get_as_item():
    pass


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
    return results
