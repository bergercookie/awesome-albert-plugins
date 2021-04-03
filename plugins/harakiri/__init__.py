"""Harakiri mail temporary email."""

import random
import string
import subprocess
import traceback
import webbrowser
from pathlib import Path

import albert as v0

__title__ = "Harakiri mail temporary email"
__version__ = "0.4.0"
__triggers__ = "harakiri "
__authors__ = "Nikos Koukis"
__homepage__ = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/harakiri"

icon_path = str(Path(__file__).parent / "harakiri")

cache_path = Path(v0.cacheLocation()) / "harakiri"
config_path = Path(v0.configLocation()) / "harakiri"
data_path = Path(v0.dataLocation()) / "harakiri"
dev_mode = False

# plugin main functions -----------------------------------------------------------------------


def initialize():
    """Called when the extension is loaded (ticked in the settings) - blocking."""

    # create plugin locations
    for p in (cache_path, config_path, data_path):
        p.mkdir(parents=False, exist_ok=True)


def finalize():
    pass


def randstr(strnum=15) -> str:
    return ''.join(random.SystemRandom().choice(string.ascii_lowercase +
                                                string.ascii_uppercase +
                                                string.digits) for _ in range(strnum))

def handleQuery(query) -> list:
    """Hook that is called by albert with *every new keypress*."""  # noqa
    results = []

    if query.isTriggered:
        try:
            query.disableSort()

            query_str =query.string.strip()
            results.append(get_as_item(query_str if query_str else randstr()))

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
def copy_and_go(email: str):
    url = f"https://harakirimail.com/inbox/{email}"
    subprocess.Popen(f"echo {email}@harakirimail.com | xclip -selection clipboard", shell=True)
    webbrowser.open(url)


def get_as_item(email):
    """Return an item - ready to be appended to the items list and be rendered by Albert."""
    return v0.Item(
        id=__title__,
        icon=icon_path,
        text=f"Temporary email: <u>{email}</u>",
        subtext="",
        completion=f"{__triggers__} {email}",
        actions=[
            v0.FuncAction("Open in browser (and copy email address)", lambda email=email:
                          copy_and_go(email)),
        ],
    )
