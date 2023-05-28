"""Image Search and Preview."""

import concurrent.futures
import importlib.util
import subprocess
import time
import traceback
from pathlib import Path
from typing import Iterator, List

import albert as v0
from gi.repository import GdkPixbuf, Notify

# load bing module - from the same directory as this file
dir_ = Path(__file__).absolute().parent
spec = importlib.util.spec_from_file_location("bing", dir_ / "bing.py")
if spec == None:
    raise RuntimeError("Couldn't find bing.py in current dir.")
bing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bing)  # type: ignore
BingImage = bing.BingImage  # type: ignore
bing_search = bing.bing_search  # type: ignore

md_name = "Image Search and Preview"
md_description = "TODO"
md_iid = "0.5"
md_version = "0.2"
md_maintainers = "Nikos Koukis"
md_url = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/image_search"
)

icon_path = str(Path(__file__).parent / "image_search")

cache_path = Path(v0.cacheLocation()) / "image_search"
config_path = Path(v0.configLocation()) / "image_search"
data_path = Path(v0.dataLocation()) / "image_search"

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


# supplementary functions ---------------------------------------------------------------------
def bing_search_set_download(query, limit) -> Iterator[BingImage]:
    for img in bing_search(query=query, limit=limit):
        img.download_dir = cache_path
        yield img


def notify(
    msg: str,
    app_name: str = md_name,
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
        return "img "

    def synopsis(self):
        return "search text"

    def initialize(self):
        """Called when the extension is loaded (ticked in the settings) - blocking."""

        # create plugin locations
        for p in (cache_path, config_path, data_path):
            p.mkdir(parents=False, exist_ok=True)

    def finalize(self):
        pass

    def get_as_item(self, query, result: BingImage):
        """Return an item.

        Will return None if the link to the image is not reachable (e.g., on 404)
        """
        try:
            img = str(result.image.absolute())
        except subprocess.CalledProcessError:
            v0.debug(f"Could not fetch item -> {result.url}")
            return None

        actions = [
            ClipAction("Copy url", result.url),
            ClipAction("Copy local path to image", img),
            UrlAction("Open in browser", result.url),
        ]

        if result.type != "gif":
            actions.insert(
                0, FuncAction("Copy image", lambda result=result: copy_image(result))
            )

        item = v0.Item(
            id=f"{md_name}_{hash(result)}",
            icon=[str(result.thumbnail)],
            text=result.url[-20:],
            subtext=result.type,
            completion=f"{query.trigger}",
            actions=actions,
        )

        return item

    def handleQuery(self, query) -> None:
        """Hook that is called by albert with *every new keypress*."""  # noqa
        try:
            query_str = query.string

            if len(query_str) < 2:
                keys_monitor.reset()

            keys_monitor.report()
            if not keys_monitor.triggered():
                return

            bing_images = list(bing_search_set_download(query=query_str, limit=3))
            if not bing_images:
                query.add(
                    v0.Item(
                        id=md_name,
                        icon=[icon_path],
                        text="No images found",
                        subtext=f"Query: {query_str}",
                    ),
                )
                return

            query.add(self.get_bing_results_as_items(query, bing_images))

        except Exception:  # user to report error
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

    def get_bing_results_as_items(self, query, bing_results: List[BingImage]):
        """Get bing results as Albert items ready to be rendered in the UI."""
        # TODO Seems to only run in a single thread?!
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(self.get_as_item, query, result): "meanings"
                for result in bing_results
            }

            items = []
            for future in concurrent.futures.as_completed(futures):
                future_res = future.result()
                if future_res is not None:
                    items.append(future_res)

            return items
