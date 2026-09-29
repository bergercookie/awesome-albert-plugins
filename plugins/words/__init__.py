"""Words: meaning, synonyms, antonyms, examples."""

import concurrent.futures
import time
import traceback
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
from PyDictionary import PyDictionary

md_iid = "5.0"
md_version = "0.3"
md_name = "Words"
md_description = "Words: meaning, synonyms, antonyms, examples"
md_url = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/words"
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["PyDictionary"]
ICON_PATH = Path(__file__).parent / "words.png"
ICON_PATH_G = Path(__file__).parent / "words_g.png"
ICON_PATH_R = Path(__file__).parent / "words_r.png"

pd = PyDictionary()


# plugin main functions -----------------------------------------------------------------------


class KeystrokeMonitor:
    def __init__(self):
        super(KeystrokeMonitor, self)
        self.thres = 0.5  # s
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


# I 'm only sending a request to Google once the user has stopped typing, otherwise Google
# blocks my IP.
keys_monitor = KeystrokeMonitor()

# supplementary functions ---------------------------------------------------------------------


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


# main plugin class ------------------------------------------------------------
class Plugin(PluginInstance, GeneratorQueryHandler):
    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)

        self.cache_path = Path(self.cacheLocation()) / "words"
        self.config_path = Path(self.configLocation()) / "words"
        self.data_path = Path(self.dataLocation()) / "words"

        for p in (self.cache_path, self.config_path, self.data_path):
            p.mkdir(parents=True, exist_ok=True)

    def defaultTrigger(self):
        return "word "

    def synopsis(self, query):
        return "some word e.g., obnoxious"

    def save_data(self, data: str, data_name: str):
        """Save a piece of data in the configuration directory."""
        with open(self.config_path / data_name, "w") as f:
            f.write(data)

    def load_data(self, data_name) -> str:
        """Load a piece of data from the configuration directory."""
        with open(self.config_path / data_name, "r") as f:
            data = f.readline().strip().split()[0]

        return data

    # -- items --------------------------------------------------------------------------------

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def get_items_for_word(self, ctx, word: str) -> List[StandardItem]:
        """Return an item - ready to be appended to the items list and be rendered by Albert."""
        # TODO Do these in parallel
        outputs = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(pd.meaning, word): "meanings",
                executor.submit(pd.synonym, word): "synonyms",
                executor.submit(pd.antonym, word): "antonyms",
            }
            for future in concurrent.futures.as_completed(futures):
                key = futures[future]
                try:
                    outputs[key] = future.result()
                except Exception as exc:
                    print(f"[W] Getting the word {key} generated an exception: {exc}")

        meanings = outputs["meanings"]
        synonyms = outputs["synonyms"]
        antonyms = outputs["antonyms"]

        # meaning
        items: List[StandardItem] = []
        if meanings:
            for k, v in meanings.items():
                for idx, vi in enumerate(v):
                    items.append(
                        StandardItem(
                            id=f"{self.id()}.meaning-{word}-{k}-{idx}",
                            icon_factory=self.makeIcon,
                            text=vi,
                            subtext=k,
                            input_action_text=f"{ctx.trigger} {word}",
                            actions=[
                                Action("copy", "Copy", lambda vi=vi: setClipboardText(vi)),
                            ],
                        )
                    )

        # synonyms
        if synonyms:
            items.append(
                StandardItem(
                    id=f"{self.id()}.synonyms-{word}",
                    icon_factory=lambda: Icon.image(ICON_PATH_G),
                    text="Synonyms",
                    subtext="|".join(synonyms),
                    input_action_text=synonyms[0],
                    actions=[
                        Action("copy", a, lambda a=a: setClipboardText(a)) for a in synonyms
                    ],
                )
            )

        # antonym
        if antonyms:
            items.append(
                StandardItem(
                    id=f"{self.id()}.antonyms-{word}",
                    icon_factory=lambda: Icon.image(ICON_PATH_R),
                    text="Antonyms",
                    subtext="|".join(antonyms),
                    input_action_text=antonyms[0],
                    actions=[
                        Action("copy", a, lambda a=a: setClipboardText(a)) for a in antonyms
                    ],
                )
            )

        return items

    def get_error_item(self, trace: str) -> StandardItem:
        return StandardItem(
            id=f"{self.id()}.error",
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

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        """Hook that is called by albert with *every new keypress*."""
        results = []

        try:
            query_str = ctx.query.strip()

            # too small request - don't even send it.
            if len(query_str) < 2:
                keys_monitor.reset()
                return

            if len(query_str.split()) > 1:
                # pydictionary or synonyms.com don't seem to support this
                yield [
                    StandardItem(
                        id=f"{self.id()}.single-word",
                        icon_factory=self.makeIcon,
                        text="A term must be only a single word",
                        actions=[],
                    )
                ]
                return

            # determine if we can make the request --------------------------------------------
            keys_monitor.report()
            if keys_monitor.triggered():
                results.extend(self.get_items_for_word(ctx, query_str))

                if not results:
                    yield [
                        StandardItem(
                            id=f"{self.id()}.no-results",
                            icon_factory=self.makeIcon,
                            text="No results.",
                            actions=[],
                        ),
                    ]

                    return
                else:
                    yield results

        except Exception:  # user to report error
            trace = traceback.format_exc()
            print(trace)

            yield [self.get_error_item(trace)]
