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

import albert as v0

__title__ = "Google Translate"
__version__ = "0.4.0"
__triggers__ = "tr "
__authors__ = "Manuel Schneider"
__homepage__ = "https://github.com/bergercookie/awesome-albert-plugins"
__simplename__ = "google_translate"

ua = "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.62 Safari/537.36"
urltmpl = (
    "https://translate.googleapis.com/translate_a/single?client=gtx&sl=%s&tl=%s&dt=t&q=%s"
)

icon_path = os.path.join(os.path.dirname(__file__), "google_translate")

# TODO Use these to provide autocompletion
langs = [
    {"Afrikaans": "af"},
    {"Albanian": "sq"},
    {"Amharic": "am"},
    {"Arabic": "ar"},
    {"Armenian": "hy"},
    {"Azerbaijani": "az"},
    {"Basque": "eu"},
    {"Belarusian": "be"},
    {"Bengali": "bn"},
    {"Bosnian": "bs"},
    {"Bulgarian": "bg"},
    {"Catalan": "ca"},
    {"Cebuano": "ceb"},
    {"Chinese (Simplified)": "zh"},
    {"Chinese (Traditional)": "zh-TW"},
    {"Corsican": "co"},
    {"Croatian": "hr"},
    {"Czech": "cs"},
    {"Danish": "da"},
    {"Dutch": "nl"},
    {"English": "en"},
    {"Esperanto": "eo"},
    {"Estonian": "et"},
    {"Finnish": "fi"},
    {"French": "fr"},
    {"Frisian": "fy"},
    {"Galician": "gl"},
    {"Georgian": "ka"},
    {"German": "de"},
    {"Greek": "el"},
    {"Gujarati": "gu"},
    {"Haitian Creole": "ht"},
    {"Hausa": "ha"},
    {"Hawaiian": "haw"},
    {"Hebrew": "he"},
    {"Hindi": "hi"},
    {"Hmong": "hmn"},
    {"Hungarian": "hu"},
    {"Icelandic": "is"},
    {"Igbo": "ig"},
    {"Indonesian": "id"},
    {"Irish": "ga"},
    {"Italian": "it"},
    {"Japanese": "ja"},
    {"Javanese": "jv"},
    {"Kannada": "kn"},
    {"Kazakh": "kk"},
    {"Khmer": "km"},
    {"Kinyarwanda": "rw"},
    {"Korean": "ko"},
    {"Kurdish": "ku"},
    {"Kyrgyz": "ky"},
    {"Lao": "lo"},
    {"Latin": "la"},
    {"Latvian": "lv"},
    {"Lithuanian": "lt"},
    {"Luxembourgish": "lb"},
    {"Macedonian": "mk"},
    {"Malagasy": "mg"},
    {"Malay": "ms"},
    {"Malayalam": "ml"},
    {"Maltese": "mt"},
    {"Maori": "mi"},
    {"Marathi": "mr"},
    {"Mongolian": "mn"},
    {"Myanmar (Burmese)": "my"},
    {"Nepali": "ne"},
    {"Norwegian": "no"},
    {"Nyanja (Chichewa)": "ny"},
    {"Odia (Oriya)": "or"},
    {"Pashto": "ps"},
    {"Persian": "fa"},
    {"Polish": "pl"},
    {"Portuguese (Portugal, Brazil)": "pt"},
    {"Punjabi": "pa"},
    {"Romanian": "ro"},
    {"Russian": "ru"},
    {"Samoan": "sm"},
    {"Scots Gaelic": "gd"},
    {"Serbian": "sr"},
    {"Sesotho": "st"},
    {"Shona": "sn"},
    {"Sindhi": "sd"},
    {"Sinhala (Sinhalese)": "si"},
    {"Slovak": "sk"},
    {"Slovenian": "sl"},
    {"Somali": "so"},
    {"Spanish": "es"},
    {"Sundanese": "su"},
    {"Swahili": "sw"},
    {"Swedish": "sv"},
    {"Tagalog (Filipino)": "tl"},
    {"Tajik": "tg"},
    {"Tamil": "ta"},
    {"Tatar": "tt"},
    {"Telugu": "te"},
    {"Thai": "th"},
    {"Turkish": "tr"},
    {"Turkmen": "tk"},
    {"Ukrainian": "uk"},
    {"Urdu": "ur"},
    {"Uyghur": "ug"},
    {"Uzbek": "uz"},
    {"Vietnamese": "vi"},
    {"Welsh": "cy"},
    {"Xhosa": "xh"},
    {"Yiddish": "yi"},
    {"Yoruba": "yo"},
    {"Zulu": "zu"},
]

# plugin main functions -----------------------------------------------------------------------


class KeystrokeMonitor:
    def __init__(self):
        super(KeystrokeMonitor, self)
        self.thres = 0.4  # s
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
            query.disableSort()

            fields = query.string.split()
            item = v0.Item(id=__title__, icon=icon_path, completion=query.rawString)

            if len(fields) < 3:
                keys_monitor.reset()

                item.text = __title__
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
                    item.subtext = "%s -> %s: %s" % (src.upper(), dst.upper(), txt,)
                    item.completion = f"{__triggers__}{src} {dst} "
                    item.addAction(v0.ClipAction("Copy translation to clipboard", result))
                    item.addAction(
                        v0.UrlAction(
                            "Open in browser",
                            f"https://translate.google.com/#view=home&op=translate&sl={src.lower()}&tl={dst.lower()}&text={txt}",
                        )
                    )
                    results.append(item)

        except Exception:  # user to report error
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
