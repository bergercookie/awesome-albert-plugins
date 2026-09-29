"""Image Search and Preview."""

import concurrent.futures
import importlib.util
import subprocess
import time
import traceback
from pathlib import Path
from typing import Iterator, List


from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    Notification,
    PluginInstance,
    StandardItem,
    openUrl,
    setClipboardText,
)

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
md_description = "Search the web for images, download them and copy them to the clipboard"
md_license = "MIT"
md_iid = "5.0"
md_version = "0.3"
md_url = "https://github.com/bergercookie/awesome-albert-plugins"
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["beautifulsoup4", "requests"]

md_bin_dependencies = ["convert", "wget", "xclip"]
ICON_PATH = Path(__file__).parent / "image_search"


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
def bing_search_set_download(query, limit, download_dir: Path) -> Iterator[BingImage]:
    for img in bing_search(query=query, limit=limit):
        img.download_dir = download_dir
        yield img


def notify(
    msg: str,
    app_name: str = md_name,
):
    Notification(app_name, msg).send()


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

        # clean up cached images on every startup
        for img in self.cache_path.glob("*"):
            if img.is_file():
                img.unlink()

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "img "

    def synopsis(self, query):
        return "search text"

    def get_as_item(self, query, result: BingImage):
        """Return an item.

        Will return None if the link to the image is not reachable (e.g., on 404)
        """
        try:
            img = str(result.image.absolute())
        except subprocess.CalledProcessError:
            debug(f"Could not fetch item -> {result.url}")
            return None

        actions = [
            Action("copy", "Copy url", lambda: setClipboardText(result.url)),
            Action("copy", "Copy local path to image", lambda: setClipboardText(img)),
            Action("open", "Open in browser", lambda: openUrl(result.url)),
        ]

        if result.type != "gif":
            actions.insert(
                0, Action("copy", "Copy image", lambda result=result: copy_image(result))
            )

        item = StandardItem(
            id=f"image-search-{hash(result)}",
            icon_factory=lambda: Icon.image(str(result.thumbnail)),
            text=result.url[-20:],
            subtext=result.type,
            input_action_text=f"{query.trigger}",
            actions=actions,
        )

        return item

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        """Yield the images matching the current query."""
        try:
            query_str = ctx.query

            if len(query_str) < 2:
                keys_monitor.reset()

            keys_monitor.report()
            if not keys_monitor.triggered():
                return

            bing_images = list(
                bing_search_set_download(
                    query=query_str, limit=3, download_dir=self.cache_path
                )
            )
            if not bing_images:
                yield [
                    StandardItem(
                        id="image-search-empty",
                        icon_factory=self.makeIcon,
                        text="No images found",
                        subtext=f"Query: {query_str}",
                    )
                ]
                return

            yield self.get_bing_results_as_items(ctx, bing_images)

        except Exception:  # user to report error
            trace = traceback.format_exc()
            print(trace)
            yield [
                StandardItem(
                    id="image-search-error",
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
