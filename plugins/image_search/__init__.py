"""Image Search and Preview."""

from requests.exceptions import RequestException
import concurrent.futures
import importlib.util
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Dict, Iterator, List

from gi.repository import GdkPixbuf, Notify

import albert as v0

# load bing module - from the same directory as this file
dir_ = Path(__file__).absolute().parent
spec = importlib.util.spec_from_file_location("bing", dir_ / "bing.py")
bing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bing)  # type: ignore
BingImage = bing.BingImage  # type: ignore
bing_search = bing.bing_search  # type: ignore

__title__ = "Image Search and Preview"
__version__ = "0.4.0"
__triggers__ = "img "
__authors__ = "Nikos Koukis"
__homepage__ = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/image_search"
)

icon_path = str(Path(__file__).parent / "image_search")

cache_path = Path(v0.cacheLocation()) / "image_search"
config_path = Path(v0.configLocation()) / "image_search"
data_path = Path(v0.dataLocation()) / "image_search"
dev_mode = True

# clean up cached images on every startup
if cache_path.exists():
    for img in cache_path.glob("*"):
        img.unlink()

# Keystroke Monitor ---------------------------------------------------------------------------
class KeystrokeMonitor:
    def __init__(self):
        super(KeystrokeMonitor, self)
        self.thres = 0.4  # s
        self.prev_time = time.time()
        self.curr_time = time.time()

    def report(self):
        self.prev_time = time.time()
        self.curr_time = time.time()
        self.report = self.report_after_first  # type: ignore

    def report_after_first(self):
        # update prev, curr time
        self.prev_time = self.curr_time
        self.curr_time = time.time()

    def triggered(self) -> bool:
        return self.curr_time - self.prev_time > self.thres

    def reset(self) -> None:
        self.report = self.report_after_first  # type: ignore


# Do not flood the web server with queries, otherwise it may block your IP.
keys_monitor = KeystrokeMonitor()

# plugin main functions -----------------------------------------------------------------------


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

            query_str = query.string

            if len(query_str) < 2:
                keys_monitor.reset()
                return results

            keys_monitor.report()
            if keys_monitor.triggered():
                bing_images = list(bing_search_save_to_cache(query=query_str, limit=3))
                if not bing_images:
                    results.insert(
                        0,
                        v0.Item(
                            id=__title__,
                            icon=icon_path,
                            text="No images found",
                            subtext=f"Query: {query_str}",
                        ),
                    )
                    return results

                results.extend(get_bing_results_as_items(bing_images))

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


def bing_search_save_to_cache(query, limit) -> Iterator[BingImage]:
    for img in bing_search(query=query, limit=limit):
        img.download_dir = cache_path
        yield img


def notify(
    msg: str,
    app_name: str = __title__,
    image=str(icon_path),
):
    Notify.init(app_name)
    n = Notify.Notification.new(app_name, msg, image)
    n.show()


def copy_image(result: BingImage):
    fname_in = result.image.absolute()
    if result.type == "png":
        fname_out = fname_in
    else:
        fname_out = f"{result.image.absolute()}.png"
        subprocess.check_call(["convert", "-format", "png", fname_in, fname_out])

    subprocess.check_call(["xclip", "-selection", "clipboard", "-t", "image/png", fname_out])


def get_bing_results_as_items(bing_results: List[BingImage]):
    """Get bing results as Albert items ready to be rendered in the UI"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(get_as_item, result): "meanings" for result in bing_results}

    items = []
    for future in concurrent.futures.as_completed(futures):
        future_res = future.result()
        if future_res is not None:
            items.append(future_res)

    return items


def get_as_item(result: BingImage):
    """Return an item.

    Will return None if the link to the image is not reachable (e.g., on 404)
    """
    try:
        img = str(result.image.absolute())
    except RequestException:
        return None

    actions = [
        v0.ClipAction("Copy url", result.url),
        v0.ClipAction("Copy local path to image", img),
        v0.UrlAction("Open in browser", result.url),
    ]

    if result.type != "gif":
        actions.insert(
            0, v0.FuncAction("Copy image", lambda result=result: copy_image(result))
        )

    item = v0.Item(
        id=__title__,
        icon=str(result.image),
        text=result.url[-20:],
        subtext=result.type,
        completion=f"{__triggers__}",
        actions=actions,
    )

    return item


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
