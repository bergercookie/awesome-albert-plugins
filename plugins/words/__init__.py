"""Words: meaning, synonyms, antonyms, examples."""

import concurrent.futures
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Dict, List

from PyDictionary import PyDictionary

import albert as v0

__title__ = "Words: meaning, synonyms, antonyms, examples"
__version__ = "0.4.0"
__triggers__ = "word "
__authors__ = "Nikos Koukis"
__homepage__ = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/words"
)

icon_path = str(Path(__file__).parent / "words")
icon_path_g = str(Path(__file__).parent / "words_g")
icon_path_r = str(Path(__file__).parent / "words_r")

cache_path = Path(v0.cacheLocation()) / "words"
config_path = Path(v0.configLocation()) / "words"
data_path = Path(v0.dataLocation()) / "words"
dev_mode = True

pd = PyDictionary()


# plugin main functions -----------------------------------------------------------------------


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

    if query.isTriggered:
        try:
            query.disableSort()

            results_setup = setup(query)
            if results_setup:
                return results_setup

            query_str = query.string.strip()

            # too small request - don't even send it.
            if len(query_str) < 2:
                keys_monitor.reset()
                return results

            if len(query_str.split()) > 1:
                # pydictionary or synonyms.com don't seem to support this
                results.append(
                    v0.Item(
                        id=__title__,
                        icon=icon_path,
                        text="A term must be only a single word",
                        actions=[],
                    )
                )

                return results

            # determine if we can make the request --------------------------------------------
            keys_monitor.report()
            if keys_monitor.triggered():
                results.extend(get_items_for_word(query_str))

                if not results:
                    results.insert(
                        0,
                        v0.Item(
                            id=__title__, icon=icon_path, text="No results.", actions=[],
                        ),
                    )

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


def get_items_for_word(word: str) -> list:
    """Return an item - ready to be appended to the items list and be rendered by Albert."""
    # TODO Do these in parallel
    outputs = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(pd.meaning, word): "meanings",
            executor.submit(pd.synonym, word): "synonyms",
            executor.submit(pd.antonym, word): "antonyms",
        }
        for future in concurrent.futures.as_completed(futures):
            key = futures[future]
            try:
                outputs[key] = future.result()
            except Exception as exc:
                print(f"[W] Getting the word {key} generated an exception: {exc}")

    meanings = outputs["meanings"]
    synonyms = outputs["synonyms"]
    antonyms = outputs["antonyms"]

    # meaning
    items = []
    if meanings:
        for k, v in meanings.items():
            for vi in v:
                items.append(
                    v0.Item(
                        id=__title__,
                        icon=icon_path,
                        text=vi,
                        subtext=k,
                        completion=f"{__triggers__} {word}",
                        actions=[v0.ClipAction("Copy", vi),],
                    )
                )

    # synonyms
    if synonyms:
        items.append(
            v0.Item(
                id=__title__,
                icon=icon_path_g,
                text="Synonyms",
                subtext="|".join(synonyms),
                completion=synonyms[0],
                actions=[v0.ClipAction(a, a) for a in synonyms],
            )
        )

    # antonym
    if antonyms:
        items.append(
            v0.Item(
                id=__title__,
                icon=icon_path_r,
                text="Antonyms",
                subtext="|".join(antonyms),
                completion=antonyms[0],
                actions=[v0.ClipAction(a, a) for a in antonyms],
            )
        )

    return items


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


def setup(query):
    """Setup is successful if an empty list is returned.

    Use this function if you need the user to provide you data
    """

    results = []
    return results
