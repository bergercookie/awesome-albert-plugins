"""Fetch xkcd comics like a boss."""

from datetime import datetime, timedelta
from pathlib import Path
import json
import subprocess
import sys
import traceback

import albert as v0
from fuzzywuzzy import process

md_name = "Xkcd"
md_description = "Xkcd Comics Fetcher"
md_iid = "0.5"
md_version = "0.2"
md_maintainers = "Nikos Koukis"
md_url = "https://github.com/bergercookie/xkcd-albert-plugin"
md_bin_dependencies = ["xkcd-dl"]
md_lib_dependencies = ["fuzzywuzzy"]

icon_path = str(Path(__file__).parent / "image.png")
settings_path = Path(v0.cacheLocation()) / "xkcd"
last_update_path = settings_path / "last_update"
xkcd_dict = Path.home() / ".xkcd_dict.json"


def get_as_item(k: str, v: dict):
    return v0.Item(
        id=md_name,
        icon=[icon_path],
        text=v["description"],
        subtext=v["date-published"],
        completion="",
        actions=[
            UrlAction("Open in xkcd.com", f"https://www.xkcd.com/{k}"),
            ClipAction("Copy URL", f"https://www.xkcd.com/{k}"),
        ],
    )


def update_date_file():
    now = (datetime.now() - datetime(1970, 1, 1)).total_seconds()
    with open(last_update_path, "w") as f:
        f.write(str(now))


def update_xkcd_db():
    return subprocess.call(["xkcd-dl", "-u"])


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
        return "xkcd "

    def synopsis(self):
        return "xkcd title term"

    def finalize(self):
        pass

    def initialize(self):
        # Called when the extension is loaded (ticked in the settings) - blocking

        # create cache location
        settings_path.mkdir(parents=False, exist_ok=True)
        if not last_update_path.is_file():
            update_date_file()
            update_xkcd_db()

    def handleQuery(self, query) -> None:
        results = []

        # check whether I have downloaded the latest metadata
        with open(last_update_path, "r") as f:
            date_str = float(f.readline().strip())

        last_date = datetime.fromtimestamp(date_str)
        if datetime.now() - last_date > timedelta(days=1):  # run an update daily
            update_date_file()
            update_xkcd_db()

        try:
            with open(xkcd_dict, "r", encoding="utf-8") as f:
                d = json.load(f)

            if len(query.string) in [0, 1]:  # Display all items
                for k, v in d.items():
                    results.append(get_as_item(k, v))
            else:  # fuzzy search
                desc_to_item = {item[1]["description"]: item for item in d.items()}
                matched = process.extract(
                    query.string.strip(), list(desc_to_item.keys()), limit=20
                )
                for m in [elem[0] for elem in matched]:
                    # bypass a unicode issue - use .get
                    item = desc_to_item.get(m)
                    if item:
                        results.append(get_as_item(*item))

        except Exception:  # user to report error
            v0.critical(traceback.format_exc())
            results.insert(
                0,
                v0.Item(
                    id=md_name,
                    icon=[icon_path],
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        ClipAction(
                            f"Copy error - report it to {md_url[8:]}",
                            f"{sys.exc_info()}",
                        )
                    ],
                ),
            )

        query.add(results)



