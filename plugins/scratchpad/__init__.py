"""Scratchpad - Dump all your thoughts into a single textfile."""

import subprocess
import sys
import textwrap
import time
import traceback
from pathlib import Path
from typing import Dict, List

import albert as v0
from fuzzywuzzy import process

__title__ = "Scratchpad - Dump all your thoughts into a single textfile"
__version__ = "0.4.0"
__triggers__ = "s "
__authors__ = "Nikos Koukis"
__homepage__ = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/scratchpad"
)
__exec_deps__ = []
__py_deps__ = ["textwrap"]

icon_path = str(Path(__file__).parent / "scratchpad")

cache_path = Path(v0.cacheLocation()) / "scratchpad"
config_path = Path(v0.configLocation()) / "scratchpad"
data_path = Path(v0.dataLocation()) / "scratchpad"

s_store_fname = config_path / "fname"

# break long lines at the specified width
split_at_textwidth = 80

# plugin main functions -----------------------------------------------------------------------
if s_store_fname.is_file():
    with open(s_store_fname, "r") as f:
        p = Path(f.readline().strip()).expanduser()
        s_path = p if p.is_file() else Path()


def save_to_scratchpad(line: str, sep=False):
    with open(s_path, "a+") as f:
        if split_at_textwidth is not None:
            towrite = textwrap.fill(line, split_at_textwidth)
        else:
            towrite = line

        towrite = f"\n{towrite}"

        s = ""
        if sep:
            s = "\n\n" + "-" * 10 + "\n"
            towrite = f"{s}{towrite}\n"

        towrite = f"{towrite}\n"
        f.write(towrite)


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

    # trigger if the user has either explicitly called the plugin or when we have detected many
    # words in the query. The latter is just a heuristic; I haven't decided whether it's worth
    # keeping
    if query.isTriggered or len(query.rawString.split()) >= 4:
        try:
            query.disableSort()

            results_setup = setup(query)
            if results_setup:
                return results_setup

            query_str = query.string
            # modify this...
            results.append(get_as_item(query_str))

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
def notify(
    msg: str,
    app_name: str = __title__,
    image=str(icon_path),
):
    Notify.init(app_name)
    n = Notify.Notification.new(app_name, msg, image)
    n.show()


def get_as_item(query_str: str):
    """Return an item - ready to be appended to the items list and be rendered by Albert."""
    query_str = query_str.strip()
    return v0.Item(
        id=__title__,
        icon=icon_path,
        text="Save to scratchpad",
        subtext=query_str,
        completion=f"{__triggers__}{query_str}",
        actions=[
            v0.FuncAction(
                f"Save to scratchpad ➡️ {s_path}",
                lambda line=query_str: save_to_scratchpad(line),
            ),
            v0.FuncAction(
                f"Save to scratchpad - New Section ➡️ {s_path}",
                lambda line=query_str: save_to_scratchpad(line, sep=True),
            ),
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


def submit_fname(p: Path):
    p = p.expanduser().resolve()
    with open(s_store_fname, "w") as f:
        f.write(str(p))

    global s_path
    s_path = p

    # also create it
    s_path.touch()


def setup(query):
    """Setup is successful if an empty list is returned."""

    results = []

    query_str = query.string

    # abbreviations file
    if not s_path.is_file():
        results.append(
            v0.Item(
                id=__title__,
                icon=icon_path,
                text=f"Specify the location of the scratchpad file",
                subtext="Paste the path to the file, then press ENTER",
                actions=[
                    v0.FuncAction("Submit path", lambda p=query_str: submit_fname(Path(p))),
                ],
            )
        )
        return results

    return results
