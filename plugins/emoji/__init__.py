"""Emoji picker."""

import subprocess
import traceback
from pathlib import Path

from albert import *
import em
from fuzzywuzzy import process

import pickle

md_iid = "0.5"
md_version = "0.5"
md_name = "Emoji picker"
md_description = "Lookup and copy various emojis to your clipboard"
md_url = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/emoji"
md_maintainers = "Nikos Koukis"
md_bin_dependencies = ["xclip"]
md_lib_dependencies = ["em", "fuzzywuzzy"]

# Let Exceptions fly
dev_mode = True

if "parse_emojis" not in dir(em):
    raise RuntimeError(
        "Was able  to import the em module but no parse_emojis method in it. "
        "Are you sure you have pip-installed the em-keyboard module and not the empy module?"
    )


class Plugin(QueryHandler):
    def id(self):
        return __name__

    def name(self):
        return md_name

    def description(self):
        return md_description

    def defaultTrigger(self):
        return "em "

    def synopsis(self):
        return "<emoji name>"

    def initialize(self):
        self.parse_emojis()

        self.icon_path = [str(Path(__file__).parent / "emoji.png")]
        self.cache_path = Path(cacheLocation()) / "emoji"
        self.config_path = Path(configLocation()) / "emoji"
        self.data_path = Path(dataLocation()) / "emoji"
        self.stats_path = self.config_path / "stats"

        # create plugin locations
        for p in (self.cache_path, self.config_path, self.data_path):
            p.mkdir(parents=False, exist_ok=True)

        if not self.stats_path.exists():
            with self.stats_path.open("wb") as f:
                pickle.dump({}, f)

    def parse_emojis(self):
        self.emojis = em.parse_emojis()
        self.emojis_li = list(self.emojis.items())

        # example:
        # label:  'folded_hands'
        # emoji_tuple:    ('🙏', ['folded_hands', 'please', 'hope', 'wish', 'namaste', 'highfive', 'pray'])
        self.label_to_emoji_tuple = {}
        for emoji_tuple in self.emojis.items():
            label_list = emoji_tuple[1]
            for label in label_list:
                self.label_to_emoji_tuple[label] = emoji_tuple
        # debug(f"label_to_emoji_tuple: {self.label_to_emoji_tuple}")

    def update_emojis(self):
        prev_len = len(self.emojis_li)
        self.parse_emojis()
        curr_len = len(self.emojis_li)

        if curr_len == prev_len:
            self.notify(msg=f"Found no new emojis - Total emojis count: {curr_len}")
        else:
            diff = curr_len - prev_len
            self.notify(
                msg=f'Found {diff} {"more" if diff > 0 else "less"} emojis - Total emojis count: {curr_len}'
            )

    def get_stats(self):
        with self.stats_path.open("rb") as f:
            return pickle.load(f)

    def update_stats(self, emoji: str):
        stats = self.get_stats()
        if emoji in stats:
            stats[emoji] += 1
        else:
            stats[emoji] = 1

        with self.stats_path.open("wb") as f:
            pickle.dump(stats, f)

    def copy_emoji(self, emoji: str):
        self.update_stats(emoji)
        subprocess.run(f"echo {emoji} | xclip -r -selection clipboard", shell=True)

    def handleQuery(self, query):
        """Hook that is called by albert with *every new keypress*."""  # noqa
        results = []

        try:
            query_str = query.string.strip()

            if query_str == "":
                results.append(self.get_reindex_item())
                recent = [
                    k
                    for k, _ in sorted(
                        self.get_stats().items(), key=lambda item: item[1], reverse=True
                    )[:10]
                ]
                results.extend(
                    [self.get_emoji_as_item((emoji, self.emojis[emoji])) for emoji in recent]
                )

                if len(results) < 30:
                    results.extend(
                        self.get_emoji_as_item(emoji_tuple)
                        for emoji_tuple in self.emojis_li[: 30 - len(results)]
                    )
            else:
                matched = process.extract(
                    query_str, list(self.label_to_emoji_tuple.keys()), limit=30
                )
                matched_emojis = list(
                    dict([self.label_to_emoji_tuple[label] for label, *_ in matched]).items()
                )
                results.extend(
                    [self.get_emoji_as_item(emoji_tuple) for emoji_tuple in matched_emojis]
                )

        except Exception:  # user to report error
            if dev_mode:  # let exceptions fly!
                critical(traceback.format_exc())
                raise

            results.insert(
                0,
                Item(
                    id=md_name,
                    icon=self.icon_path,
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        Action(
                            "copy_error",
                            f"Copy error - report it to {md_url[8:]}",
                            lambda t=traceback.format_exc(): setClipboardText(t),
                        )
                    ],
                ),
            )

        query.add(results)

    def notify(self, msg: str, app_name: str = md_name):
        sendTrayNotification(title=app_name, msg=msg, ms=2000)

    def get_reindex_item(self):
        return self.get_as_item(
            text="Re-index list of emojis",
            actions=[Action("reindex", "Re-index list of emojis", self.update_emojis)],
        )

    def get_as_item(
        self, *, text: str, actions: list, subtext: str = None, completion: str = None
    ):
        if subtext is None:
            subtext = text

        if completion is None:
            completion = f"{self.defaultTrigger()}{text}"

        """Return an item - ready to be appended to the items list and be rendered by Albert."""
        return Item(
            id=md_name,
            icon=self.icon_path,
            text=text,
            subtext=subtext,
            completion=completion,
            actions=actions,
        )

    def get_emoji_as_item(self, emoji_tuple: tuple):
        """Return an item - ready to be appended to the items list and be rendered by Albert."""
        emoji = emoji_tuple[0]
        labels = [label.replace("_", " ") for label in emoji_tuple[1]]
        main_label = labels[0]

        text = f"{emoji} {main_label}"
        subtext = " | ".join(labels[1:])
        return Item(
            id=md_name,
            icon=self.icon_path,
            text=text,
            subtext=subtext,
            completion=f"{self.defaultTrigger()}{main_label}",
            actions=[
                Action("copy", f"Copy this emoji", lambda emoji=emoji: self.copy_emoji(emoji)),
                Action(
                    "google",
                    f"Google this emoji",
                    lambda u=f"https://www.google.com/search?q={main_label} emoji": openUrl(u),
                ),
            ],
        )

    def save_data(self, data: str, data_name: str):
        """Save a piece of data in the configuration directory."""
        with open(self.config_path / data_name, "w") as f:
            f.write(data)

    def load_data(self, data_name: str) -> str:
        """Load a piece of data from the configuration directory."""
        with open(self.config_path / data_name, "r") as f:
            data = f.readline().strip().split()[0]

        return data


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
