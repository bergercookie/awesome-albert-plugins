"""TL;DR pages from albert."""

import os
import re
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Dict, List, Tuple

from fuzzywuzzy import process

import albert as v0

__title__ = "TL;DR pages from albert."
__version__ = "0.4.0"
__triggers__ = "tldr "
__authors__ = "Nikos Koukis"
__homepage__ = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins//tldr_pages"
)

icon_path = str(Path(__file__).parent / "tldr_pages")

cache_path = Path(v0.cacheLocation()) / "tldr_pages"
config_path = Path(v0.configLocation()) / "tldr_pages"
data_path = Path(v0.dataLocation()) / "tldr_pages"

tldr_root = cache_path / "tldr"
pages_root = tldr_root / "pages"

page_paths: Dict[str, Path] = None

# Is the plugin run in development mode?
in_development = False

# plugin main functions -----------------------------------------------------------------------


def initialize():
    # Called when the extension is loaded (ticked in the settings) - blocking
    global page_paths

    # create plugin locations
    for p in (cache_path, config_path, data_path):
        p.mkdir(parents=False, exist_ok=True)

    if not pages_root.is_dir():
        subprocess.check_call(
            f"git clone https://github.com/tldr-pages/tldr {tldr_root}".split()
        )

    reindex_tldr_pages()


def reindex_tldr_pages():
    global page_paths
    page_paths = get_page_paths()


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

            query_text = query.string.strip()

            if not len(query_text):
                results = [
                    v0.Item(
                        id=__title__,
                        icon=icon_path,
                        text="Update tldr database",
                        actions=[v0.FuncAction("Update", lambda: update_tldr_db())],
                    ),
                    v0.Item(
                        id=__title__,
                        icon=icon_path,
                        text="Reindex tldr pages",
                        actions=[v0.FuncAction("Reindex", lambda: reindex_tldr_pages())],
                    ),
                    v0.Item(
                        id=__title__,
                        icon=icon_path,
                        text="Need at least 1 letter to offer suggestions",
                        actions=[],
                    ),
                ] + results
                return results

            if query_text in page_paths.keys():
                # exact match - show examples
                results.extend(get_cmd_items((query_text, page_paths[query_text])))
            else:
                # fuzzy search based on word
                matched = process.extract(query_text, page_paths.keys(), limit=20)

                for m in [elem[0] for elem in matched]:
                    results.append(get_cmd_as_item((m, page_paths[m])))

        except Exception:  # user to report error
            if in_development:
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


def update_tldr_db():
    subprocess.check_call(f"git -C {tldr_root} pull --rebase origin master".split())
    reindex_tldr_pages()


def get_page_paths() -> Dict[str, Path]:
    global page_paths
    paths = list(pages_root.rglob("*.md"))

    return {p.stem: p for p in paths}


def get_cmd_as_item(pair: Tuple[str, Path]):
    with open(pair[-1], "r") as f:
        all_lines = f.readlines()
        description_lines = [
            li.lstrip("> ").rstrip().rstrip(".") for li in all_lines if li.startswith("> ")
        ]

        # see if there's a line with more information and a URL
        more_info_url = None
        try:
            more_info = [li for li in all_lines if "more information" in li.lower()][0]
            more_info_url = re.search("<(.*)>", more_info)
            if more_info_url is not None and more_info_url.groups():
                more_info_url = more_info_url.groups()[0]
        except IndexError:
            pass

    actions = [
        v0.ClipAction("Copy command", pair[0]),
        v0.UrlAction(
            "Do a google search", f'https://www.google.com/search?q="{pair[0]}" command'
        ),
    ]
    if more_info_url:
        actions.append(v0.UrlAction("More information", more_info_url))

    return v0.Item(
        id=__title__,
        icon=icon_path,
        text=pair[0],
        completion=" ".join([__triggers__, pair[0]]),
        subtext=" ".join(description_lines),
        actions=actions,
    )


def get_cmd_items(pair: Tuple[str, Path]):
    """Return a list of Albert items - one per example."""

    with open(pair[-1], "r") as f:
        lines = [li.strip() for li in f.readlines()]

    items = []
    for i, li in enumerate(lines):
        if not li.startswith("- "):
            continue

        desc = li.lstrip("- ")[:-1]
        example_cmd = sanitize_string(
            lines[i + 2].strip("`").replace("{{", "").replace("}}", "")
        )

        items.append(
            v0.Item(
                id=__title__,
                icon=icon_path,
                text=example_cmd,
                subtext=desc,
                actions=[
                    v0.ClipAction("Copy command", example_cmd),
                    v0.UrlAction(
                        "Do a google search",
                        f'https://www.google.com/search?q="{pair[0]}" command',
                    ),
                ],
            )
        )

    return items


def sanitize_string(s: str) -> str:
    return s.replace("<", "&lt;")


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
