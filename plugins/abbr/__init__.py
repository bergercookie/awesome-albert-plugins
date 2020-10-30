"""User-defined abbreviations read/written a file."""

# TODO Demo photos

import os
import shutil
import hashlib
import subprocess
import sys
import traceback
from pathlib import Path
from typing import List, Dict, Tuple

from fuzzywuzzy import process
from gi.repository import GdkPixbuf, Notify

import albertv0 as v0

__iid__ = "PythonInterface/v0.2"
__prettyname__ = "User-defined abbreviations read/written a file"
__version__ = "0.1.0"
__trigger__ = "ab "
__author__ = "Nikos Koukis"
__dependencies__ = []
__homepage__ = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/abbr"
)

icon_path = str(Path(__file__).parent / "abbr")

cache_path = Path(v0.cacheLocation()) / "abbr"
config_path = Path(v0.configLocation()) / "abbr"
data_path = Path(v0.dataLocation()) / "abbr"
dev_mode = True

abbr_store_fname = config_path / "fname"
abbr_store_sep = config_path / "separator"
abbreviations_path = Path()
abbr_latest_hash = ""
abbr_latest_d: Dict[str, str] = {}
abbr_latest_d_bi: Dict[str, str] = {}
split_at = ":"

# plugin main functions -----------------------------------------------------------------------

if abbr_store_fname.is_file():
    with open(abbr_store_fname, "r") as f:
        p = Path(f.readline().strip()).expanduser()
        if not p.is_file():
            raise FileNotFoundError(p)

        abbreviations_path = p

if abbr_store_sep.is_file():
    with open(abbr_store_sep, "r") as f:
        sep = f.read(1)
        if not sep:
            raise RuntimeError(f"Invalid separator: {sep}")

        split_at = sep


def initialize():
    """Called when the extension is loaded (ticked in the settings) - blocking."""

    # create plugin locations
    for p in (cache_path, config_path, data_path):
        p.mkdir(parents=False, exist_ok=True)


def finalize():
    pass


def save_abbr(name: str, desc: str):
    with open(abbreviations_path, "a") as f:
        li = f"\n* {name}: {desc}"
        f.write(li)


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

            # new behavior
            tokens = query_str.split()
            if len(tokens) >= 1 and tokens[0] == "new":
                if len(tokens) > 1:
                    name = tokens[1]
                else:
                    name = ""
                if len(tokens) > 2:
                    desc = " ".join(tokens[2:])
                else:
                    desc = ""

                results.append(
                    v0.Item(
                        id=__prettyname__,
                        icon=icon_path,
                        text=f"New abbreviation: {name}",
                        subtext=f"Description: {desc}",
                        actions=[
                            v0.FuncAction(
                                f"Save abbreviation to file",
                                lambda name=name, desc=desc: save_abbr(name, desc),
                            )
                        ],
                    )
                )

                return results

            curr_hash = hash_file(abbreviations_path)
            global abbr_latest_hash, abbr_latest_d, abbr_latest_d_bi
            if abbr_latest_hash != curr_hash:
                abbr_latest_hash = curr_hash
                with open(abbreviations_path) as f:
                    conts = f.readlines()
                    abbr_latest_d = make_latest_dict(conts)
                    abbr_latest_d_bi = abbr_latest_d.copy()
                    abbr_latest_d_bi.update({v: k for k, v in abbr_latest_d.items()})

            if not abbr_latest_d:
                results.append(
                    v0.Item(
                        id=__prettyname__,
                        icon=icon_path,
                        text=f'No lines split by "{split_at}" in the file provided',
                        actions=[
                            v0.ClipAction(f"Copy provided filename", str(abbreviations_path),)
                        ],
                    )
                )

                return results

            # do fuzzy search on both the abbreviations and their description
            matched = process.extract(query_str, abbr_latest_d_bi.keys(), limit=10)
            for m in [elem[0] for elem in matched]:
                if m in abbr_latest_d.keys():
                    results.append(get_abbr_as_item((m, abbr_latest_d[m])))
                else:
                    results.append(get_abbr_as_item((abbr_latest_d_bi[m], m)))

        except Exception:  # user to report error
            if dev_mode:  # let exceptions fly!
                print(traceback.format_exc())
                raise

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
def notify(
    msg: str, app_name: str = __prettyname__, image=str(icon_path),
):
    Notify.init(app_name)
    n = Notify.Notification.new(app_name, msg, image)
    n.show()


def get_abbr_as_item(abbr: Tuple[str, str]):
    """Return the abbreviation pair as an item - ready to be appended to the items list and be rendered by Albert."""
    text = abbr[0].strip()
    subtext = abbr[1].strip()

    return v0.Item(
        id=__prettyname__,
        icon=icon_path,
        text=f"{text}",
        subtext=f"{subtext}",
        completion=f"{__trigger__}{text.strip()}",
        actions=[
            v0.UrlAction("Open in Google", f"https://www.google.com/search?&q={text}"),
            v0.ClipAction("Copy abbreviation", text),
            v0.ClipAction("Copy description", subtext),
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


def submit_fname(p: Path):
    p = p.expanduser().resolve()
    if p.is_file():
        with open(abbr_store_fname, "w") as f:
            f.write(str(p))

        global abbreviations_path
        abbreviations_path = p
    else:
        notify(f"Given file path does not exist -> {p}")


def submit_sep(c: str):
    if len(c) > 1:
        notify(f"Separator must be a single character!")
        return

    with open(abbr_store_sep, "w") as f:
        f.write(c)

    global split_at
    split_at = c


def setup(query) -> list:
    """Setup is successful if an empty list is returned.

    Use this function if you need the user to provide you data
    """

    results = []

    query_str = query.string

    # abbreviations file
    if not abbr_store_fname.is_file():
        results.append(
            v0.Item(
                id=__prettyname__,
                icon=icon_path,
                text=f"Specify file to read/write abbreviations to/from",
                subtext="Paste the path to the file, then press <ENTER>",
                actions=[
                    v0.FuncAction("Submit path", lambda p=query_str: submit_fname(Path(p))),
                ],
            )
        )
        return results

    if not abbr_store_sep.is_file():
        results.append(
            v0.Item(
                id=__prettyname__,
                icon=icon_path,
                text=f"Specify separator *character* for abbreviations",
                subtext=f"Separator: {query_str}",
                actions=[
                    v0.FuncAction("Submit separator", lambda c=query_str: submit_sep(c)),
                ],
            )
        )
        return results

    return results


def make_latest_dict(conts: list):
    d = {}
    for li in conts:
        tokens = li.split(split_at, maxsplit=1)
        if len(tokens) == 2:
            # avoid cases where one of the two sides is essentially empty
            if any([not t for t in tokens]):
                continue

            tokens = [t.strip().strip("*") for t in tokens]
            d[tokens[0]] = tokens[1]

    return d


def hash_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p) as f:
        h.update(f.read().encode("utf-8"))
        return h.hexdigest()
