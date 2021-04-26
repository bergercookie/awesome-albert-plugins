# -*- coding: utf-8 -*-
"""Translate text using Google Translate.

Usage: tr <src lang> <dest lang> <text>
Example: tr en fr hello

Check available languages here: https://cloud.google.com/translate/docs/languages

20191229 - bergercookie: Send a request only when the user has "slowed-down" typing (0.3s diff
between two consecutive chars) so that we send less requests to google. This way the IP is not
blocked.
"""

import ast
import json
import subprocess
import time
import traceback
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path
from typing import Deque, Dict

import albert as v0

__title__ = "Google Translate"
__version__ = "0.4.0"
__triggers__ = "tr "
__authors__ = "Manuel Schneider"
__homepage__ = "https://github.com/bergercookie/awesome-albert-plugins"
__simplename__ = "google_translate"

__exec_deps__ = ["xclip"]
__py_deps__ = []

dev_mode = True

ua = "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.62 Safari/537.36"
url_template = (
    "https://translate.googleapis.com/translate_a/single?client=gtx&sl=%s&tl=%s&dt=t&q=%s"
)

icon_path = str(Path(__file__).parent / "google_translate")
icon_path_hist = str(Path(__file__).parent / "google_translate_gray")
cache_path = Path(v0.cacheLocation()) / "google_translate"
data_path = Path(v0.dataLocation()) / "google_translate"

# have a history of the previous results ------------------------------------------------------
history_path = cache_path / "history.dat"
history_deque: Deque[Dict[str, str]] = deque(maxlen=30)
if history_path.exists and not history_path.is_file():
    raise RuntimeError(f"History path [{history_path}] must be a file, can't handle its type!")
if history_path.is_file():
    with open(history_path, "r") as f:
        lines = f.readlines()
        history_deque.extend([ast.literal_eval(li) for li in lines])


def flush_history():
    v0.info(f"Flushing google_translate history -> {history_path}...")
    # TODO this kind of usage is theoretically unsafe, but most likely wont affect. The timer
    # fires every ~1hr and traversing the deque takes so little time.
    with open(history_path, "w") as f:
        for di in history_deque:
            f.write(f"{di}\n")


# plugin main functions -----------------------------------------------------------------------


def initialize():
    # Called when the extension is loaded (ticked in the settings) - blocking

    # create plugin locations
    for p in (cache_path, data_path):
        p.mkdir(parents=False, exist_ok=True)


def finalize():
    flush_history()


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


keys_monitor = KeystrokeMonitor()


def select_item(lang_config: Dict[str, str], result: str):
    save_search_result(**lang_config, dst_txt=result)
    subprocess.Popen(f"echo {result}| xclip -selection clipboard", shell=True)


def handleQuery(query):
    results = []
    if query.isTriggered:
        try:
            query.disableSort()

            fields = query.string.split()
            item = v0.Item(
                id=__title__,
                text=__title__,
                subtext='Enter a query in the form of "&lt;srclang&gt; &lt;dstlang&gt; &lt;text&gt;"',
                icon=icon_path,
                completion=query.rawString,
            )

            results.append(item)
            if len(fields) < 3:
                keys_monitor.reset()
                return results

            def completion():
                return f"{__triggers__}{dst} {src} {txt}"

            src = fields[0]
            dst = fields[1]
            txt = " ".join(fields[2:])
            results[-1].completion = completion()

            # determine if we can make the request --------------------------------------------
            keys_monitor.report()
            if keys_monitor.triggered():
                url = url_template % (src, dst, urllib.parse.quote_plus(txt))
                req = urllib.request.Request(url, headers={"User-Agent": ua})
                with urllib.request.urlopen(req) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    result = data[0][0][0]
                    item.text = result
                    item.subtext = "%s -> %s: %s" % (
                        src.upper(),
                        dst.upper(),
                        txt,
                    )
                    item.addAction(
                        v0.FuncAction(
                            "Copy translation to clipboard",
                            lambda lang_config={
                                "src": src,
                                "dst": dst,
                                "src_txt": txt,
                            }, result=result: select_item(
                                lang_config=lang_config, result=result
                            ),
                        )
                    )
                    item.addAction(
                        v0.UrlAction(
                            "Open in browser",
                            f"https://translate.google.com/#view=home&op=translate&sl={src.lower()}&tl={dst.lower()}&text={txt}",
                        )
                    )

            # Show previous results
            iterator = reversed(history_deque)
            try:
                next(iterator)
                for di in iterator:  # last is the most recent
                    results.append(
                        get_history_item(
                            src=di["src"],
                            dst=di["dst"],
                            src_txt=di["src_txt"],
                            dst_txt=di["dst_txt"],
                        )
                    )
            except StopIteration:
                pass

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


def save_search_result(*, src: str, dst: str, src_txt: str, dst_txt: str):
    # sanity checks
    if len(src_txt) <= 2 or len(dst_txt) <= 2:
        return

    history_deque.append(
        {
            "src": src,
            "dst": dst,
            "src_txt": src_txt,
            "dst_txt": dst_txt,
        }
    )

    # write it to file as well
    flush_history()


def get_history_item(*, src: str, dst: str, src_txt: str, dst_txt) -> v0.Item:
    return v0.Item(
        id=__title__,
        text=dst_txt,
        subtext=src_txt,
        icon=icon_path_hist,
        completion=f"{__triggers__}{src} {dst} {src_txt}",
    )
