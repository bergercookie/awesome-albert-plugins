"""Harakiri mail temporary email."""

import random
import string
import subprocess
import traceback
import webbrowser
from pathlib import Path
from typing import Iterator, List

from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    PluginInstance,
    StandardItem,
    setClipboardText,
)

md_iid = "5.0"
md_version = "0.3"
md_name = "Harakiri"
md_description = "Harakiri mail - access a temporary email address"
md_license = "MIT"
md_url = "https://github.com/bergercookie/awesome-albert-plugins"
md_maintainers = ["Nikos Koukis"]
md_bin_dependencies = ["xclip"]

ICON_PATH = Path(__file__).parent / "harakiri.png"


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
    subprocess.Popen(
        f"echo {email}@harakirimail.com | xclip -selection clipboard", shell=True
    )
    webbrowser.open(url)


def get_as_item(query, email) -> StandardItem:
    """Return an item - ready to be appended to the items list and be rendered by Albert."""
    return StandardItem(
        id=f"harakiri-{email}",
        icon_factory=Plugin.makeIcon,
        text=f"Temporary email: {email}",
        subtext="",
        input_action_text=f"{query.trigger} {email}",
        actions=[
            Action(
                "open",
                "Open in browser (and copy email address)",
                lambda: copy_and_go(email),
            ),
        ],
    )


# main plugin class ------------------------------------------------------------
class Plugin(PluginInstance, GeneratorQueryHandler):
    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)

        self.cache_path = Path(self.cacheLocation())
        self.config_path = Path(self.configLocation())
        self.data_path = Path(self.dataLocation())

        for p in (self.cache_path, self.config_path, self.data_path):
            p.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "harakiri "

    def synopsis(self, query):
        return "email address to spawn"

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        """Yield the item for the current query."""
        try:
            query_str = ctx.query.strip()
            yield [get_as_item(ctx, query_str if query_str else randstr())]

        except Exception:  # user to report error
            trace = traceback.format_exc()
            print(trace)
            yield [
                StandardItem(
                    id="harakiri-error",
                    icon_factory=self.makeIcon,
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        Action(
                            "copy",
                            f"Copy error - report it to {md_url[8:]}",
                            lambda: setClipboardText(trace),
                        )
                    ],
                )
            ]
