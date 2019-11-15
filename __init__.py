""" Zoopla > Search Property to Buy, Rent, House Prices """

from pathlib import Path
import sys
import os

import albertv0 as v0

__iid__ = "PythonInterface/v0.2"
__prettyname__ = "Zoopla > Search Property to Buy, Rent, House Prices"
__version__ = "0.1.0"
__trigger__ = "Zoopla - Search Properties "
__author__ = "Nikos Koukis"
__dependencies__ = []
__homepage__ = "https://github.com/bergercookie/zoopla-albert-plugin"

iconPath = v0.iconLookup("Zoopla - Search Properties")
if not iconPath:
    iconPath = os.path.join(os.path.dirname(__file__), "Zoopla - Search Properties")
SETTINGS_PATH = Path(v0.cacheLocation()) / " Zoopla - Search Properties"


def initialize():
    # Called when the extension is loaded (ticked in the settings) - blocking

    # create cache location
    SETTINGS_PATH.mkdir(parents=False, exist_ok=True)


def finalize():
    pass


def handleQuery(query):
    results = []

    if query.isTriggered:
        try:
            # modify this...
            results.append(get_as_item())

        except Exception:  # user to report error
            results.insert(
                0,
                v0.Item(
                    id=__prettyname__,
                    icon=iconPath,
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        v0.ClipAction(
                            f"Copy error - report it to {__homepage__[8:]}",
                            f"{sys.exc_info()}",
                        )
                    ],
                ),
            )

    return results


def get_as_item():
    return v0.Item(
        id=__prettyname__,
        icon=iconPath,
        text=f"{sys.version}",
        subtext="Python version",
        completion="",
        actions=[
            v0.UrlAction("Open in xkcd.com", "https://www.xkcd.com/"),
            v0.ClipAction("Copy URL", f"https://www.xkcd.com/"),
        ],
    )
