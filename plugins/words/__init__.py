"""Words: meaning, synonyms, antonyms, examples."""

import concurrent.futures
import time
import traceback
from pathlib import Path

import albert as v0
from PyDictionary import PyDictionary

md_name = "Words"
md_description = "Words: meaning, synonyms, antonyms, examples"
md_iid = "0.5"
md_version = "0.2"
md_maintainers = "Nikos Koukis"
md_url = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/words"
md_lib_dependencies = "git+https://github.com/ctoth/PyDictionary@0acf69d"

icon_path = str(Path(__file__).parent / "words")
icon_path_g = str(Path(__file__).parent / "words_g")
icon_path_r = str(Path(__file__).parent / "words_r")

cache_path = Path(v0.cacheLocation()) / "words"
config_path = Path(v0.configLocation()) / "words"
data_path = Path(v0.dataLocation()) / "words"

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


def get_items_for_word(query, word: str) -> list:
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
    items = []
    if meanings:
        for k, v in meanings.items():
            for vi in v:
                items.append(
                    v0.Item(
                        id=md_name,
                        icon=[icon_path],
                        text=vi,
                        subtext=k,
                        completion=f"{query.trigger} {word}",
                        actions=[
                            ClipAction("Copy", vi),
                        ],
                    )
                )

    # synonyms
    if synonyms:
        items.append(
            v0.Item(
                id="{md_name}_g",
                icon=[icon_path_g],
                text="Synonyms",
                subtext="|".join(synonyms),
                completion=synonyms[0],
                actions=[ClipAction(a, a) for a in synonyms],
            )
        )

    # antonym
    if antonyms:
        items.append(
            v0.Item(
                id="{md_name}_r",
                icon=[icon_path_r],
                text="Antonyms",
                subtext="|".join(antonyms),
                completion=antonyms[0],
                actions=[ClipAction(a, a) for a in antonyms],
            )
        )

    return items


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
        return "word "

    def synopsis(self):
        return "some word e.g., obnoxious"

    def initialize(self):
        """Called when the extension is loaded (ticked in the settings) - blocking."""

        # create plugin locations
        for p in (cache_path, config_path, data_path):
            p.mkdir(parents=False, exist_ok=True)

    def finalize(self):
        pass

    def handleQuery(self, query) -> None:
        """Hook that is called by albert with *every new keypress*."""  # noqa
        results = []

        try:
            query_str = query.string.strip()

            # too small request - don't even send it.
            if len(query_str) < 2:
                keys_monitor.reset()
                return

            if len(query_str.split()) > 1:
                # pydictionary or synonyms.com don't seem to support this
                query.add(
                    v0.Item(
                        id=md_name,
                        icon=[icon_path],
                        text="A term must be only a single word",
                        actions=[],
                    )
                )
                return

            # determine if we can make the request --------------------------------------------
            keys_monitor.report()
            if keys_monitor.triggered():
                results.extend(get_items_for_word(query, query_str))

                if not results:
                    query.add(
                        0,
                        v0.Item(
                            id=md_name,
                            icon=[icon_path],
                            text="No results.",
                            actions=[],
                        ),
                    )

                    return
                else:
                    query.add(results)

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
