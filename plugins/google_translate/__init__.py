# -*- coding: utf-8 -*-

"""Translate text using Google Translate.

Usage: tr <src lang> <dest lang> <text>
Example: tr en fr hello

Check available languages here: https://cloud.google.com/translate/docs/languages

20191229 - bergercookie: Send a request only when the user has "slowed-down" typing (0.3s diff
between two consecutive chars) so that we send less requests to google. This way the IP is not
blocked.
"""

import json
import os
import time
import traceback
import urllib.parse
import urllib.request

import albertv0 as v0

__iid__ = "PythonInterface/v0.1"
__prettyname__ = "Google Translate"
__version__ = "1.0"
__trigger__ = "tr "
__author__ = "Manuel Schneider"
__dependencies__ = []
__homepage__ = "https://github.com/bergercookie/awesome-albert-plugins"
__simplename__ = "google_translate"

ua = "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.62 Safari/537.36"
urltmpl = (
    "https://translate.googleapis.com/translate_a/single?client=gtx&sl=%s&tl=%s&dt=t&q=%s"
)

icon_path = os.path.join(os.path.dirname(__file__), "google_translate")

# plugin main functions -----------------------------------------------------------------------


class KeystrokeMonitor:
    def __init__(self):
        super(KeystrokeMonitor, self)
        self.thres = 0.3  # s
        self.prev_time = time.time()
        self.curr_time = time.time()

    def report(self):
        self.prev_time = time.time()
        self.curr_time = time.time()
        self.report = self.report_after_first

    def report_after_first(self):
        # update prev, curr time
        self.prev_time = self.curr_time
        self.curr_time = time.time()

    def triggered(self) -> bool:
        return self.curr_time - self.prev_time > self.thres

    def reset(self) -> None:
        self.report = self.report_after_first


keys_monitor = KeystrokeMonitor()


def handleQuery(query):
    results = []
    if query.isTriggered:
        try:
            # be backwards compatible with v0.2
            if "disableSort" in dir(query):
                query.disableSort()

            fields = query.string.split()
            item = v0.Item(id=__prettyname__, icon=icon_path, completion=query.rawString)

            if len(fields) < 3:
                keys_monitor.reset()

                item.text = __prettyname__
                item.subtext = 'Enter a query in the form of "&lt;srclang&gt; &lt;dstlang&gt; &lt;text&gt;"'
                results.append(item)
                return results

            # determine if we can make the request --------------------------------------------
            keys_monitor.report()
            if keys_monitor.triggered():
                src = fields[0]
                dst = fields[1]
                txt = " ".join(fields[2:])
                url = urltmpl % (src, dst, urllib.parse.quote_plus(txt))
                req = urllib.request.Request(url, headers={"User-Agent": ua})
                with urllib.request.urlopen(req) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    result = data[0][0][0]
                    item.text = result
                    item.subtext = '%s -> %s: %s' % (
                        src.upper(),
                        dst.upper(),
                        txt,
                    )
                    item.addAction(v0.ClipAction("Copy translation to clipboard", result))
                    item.addAction(v0.UrlAction("Open in browser",
                                                f"https://translate.google.com/#view=home&op=translate&sl={src.lower()}&tl={dst.lower()}&text={txt}"))
                    results.append(item)

        except Exception:  # user to report error
            results.insert(
                0,
                v0.Item(
                    id=__prettyname__,
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
