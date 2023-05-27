"""Harakiri mail temporary email."""

import random
import string
import subprocess
import traceback
import webbrowser
from pathlib import Path

import albert as v0

md_name = "Harakiri"
md_description = "Harakiri mail - access a temporary email address"
md_iid = "0.5"
md_version = "0.2"
md_maintainers = "Nikos Koukis"
md_url = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/harakiri"

icon_path = str(Path(__file__).parent / "harakiri")

cache_path = Path(v0.cacheLocation()) / "harakiri"
config_path = Path(v0.configLocation()) / "harakiri"
data_path = Path(v0.dataLocation()) / "harakiri"

def randstr(strnum=15) -> str:
    return "".join(
        random.SystemRandom().choice(
            string.ascii_lowercase + string.ascii_uppercase + string.digits
        )
        for _ in range(strnum)
    )


# supplementary functions ---------------------------------------------------------------------
def copy_and_go(email: str):
    url = f"https://harakirimail.com/inbox/{email}"
    subprocess.Popen(f"echo {email}@harakirimail.com | xclip -selection clipboard", shell=True)
    webbrowser.open(url)

def get_as_item(query, email):
    """Return an item - ready to be appended to the items list and be rendered by Albert."""
    return v0.Item(
        id=md_name,
        icon=[icon_path],
        text=f"Temporary email: {email}",
        subtext="",
        completion=f"{query.trigger} {email}",
        actions=[
            FuncAction(
                "Open in browser (and copy email address)",
                lambda email=email: copy_and_go(email),
            ),
        ],
    )




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
        return "harakiri "

    def synopsis(self):
        return "email address to spawn"

    def initialize(self):
        """Called when the extension is loaded (ticked in the settings) - blocking."""

        # create plugin locations
        for p in (cache_path, config_path, data_path):
            p.mkdir(parents=False, exist_ok=True)


    def finalize(self):
        pass

    def handleQuery(self, query) -> None:
        """Hook that is called by albert with *every new keypress*."""  # noqa
        try:
            query_str = query.string.strip()
            query.add(get_as_item(query, query_str if query_str else randstr()))

        except Exception:  # user to report error
            if dev_mode:
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
