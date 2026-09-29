"""Fetch xkcd comics like a boss."""

import json
import subprocess
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator, List

from fuzzywuzzy import process

from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    PluginInstance,
    StandardItem,
    openUrl,
    setClipboardText,
)

md_iid = "5.0"
md_version = "0.3"
md_name = "Xkcd"
md_description = "Xkcd Comics Fetcher"
md_license = "MIT"
md_url = "https://github.com/bergercookie/xkcd-albert-plugin"
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["fuzzywuzzy"]
md_bin_dependencies = ["xkcd-dl"]
ICON_PATH = Path(__file__).parent / "image.png"
XKCD_DICT = Path.home() / ".xkcd_dict.json"


def get_as_item(k: str, v: dict) -> StandardItem:
    url = f"https://www.xkcd.com/{k}"
    return StandardItem(
        id=f"xkcd-{k}",
        icon_factory=Plugin.makeIcon,
        text=v["description"],
        subtext=v["date-published"],
        input_action_text="",
        actions=[
            Action("open", "Open in xkcd.com", lambda: openUrl(url)),
            Action("copy", "Copy URL", lambda: setClipboardText(url)),
        ],
    )


def update_date_file(last_update_path: Path) -> None:
    now = (datetime.now() - datetime(1970, 1, 1)).total_seconds()
    with open(last_update_path, "w") as f:
        f.write(str(now))


def update_xkcd_db():
    try:
        return subprocess.call(["xkcd-dl", "-u"])
    except OSError as e:
        print(f"xkcd: could not run xkcd-dl - {e}")
        return None


# main plugin class ------------------------------------------------------------
class Plugin(PluginInstance, GeneratorQueryHandler):
    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)

        self.settings_path = Path(self.cacheLocation())
        self.last_update_path = self.settings_path / "last_update"

        self.settings_path.mkdir(parents=True, exist_ok=True)
        if not self.last_update_path.is_file():
            update_date_file(self.last_update_path)
            update_xkcd_db()

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "xkcd "

    def synopsis(self, query):
        return "xkcd title term"

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        results = []

        # check whether I have downloaded the latest metadata
        with open(self.last_update_path, "r") as f:
            date_str = float(f.readline().strip())

        last_date = datetime.fromtimestamp(date_str)
        if datetime.now() - last_date > timedelta(days=1):  # run an update daily
            update_date_file(self.last_update_path)
            update_xkcd_db()

        try:
            with open(XKCD_DICT, "r", encoding="utf-8") as f:
                d = json.load(f)

            if len(ctx.query) in [0, 1]:  # Display all items
                for k, v in d.items():
                    results.append(get_as_item(k, v))
            else:  # fuzzy search
                desc_to_item = {item[1]["description"]: item for item in d.items()}
                matched = process.extract(
                    ctx.query.strip(), list(desc_to_item.keys()), limit=20
                )
                for m in [elem[0] for elem in matched]:
                    # bypass a unicode issue - use .get
                    item = desc_to_item.get(m)
                    if item:
                        results.append(get_as_item(*item))

        except Exception:  # user to report error
            trace = traceback.format_exc()
            print(trace)
            results.insert(
                0,
                StandardItem(
                    id="xkcd-error",
                    icon_factory=self.makeIcon,
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        Action(
                            "copy",
                            f"Copy error - report it to {md_url[8:]}",
                            lambda: setClipboardText(str(sys.exc_info())),
                        )
                    ],
                ),
            )

        yield results
