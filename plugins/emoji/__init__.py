"""Emoji picker."""

import subprocess
import traceback
from pathlib import Path
from shutil import which

import albert as v0
import em
from fuzzywuzzy import process
from gi.repository import GdkPixbuf, Notify

import pickle

__title__ = "Emoji picker"
__version__ = "0.4.0"
__triggers__ = "em "
__authors__ = "Nikos Koukis"
__homepage__ = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/emoji"
)
__exec_deps__ = ["xclip"]
__py_deps__ = ["em", "fuzzywuzzy"]

icon_path = str(Path(__file__).parent / "emoji.png")

cache_path = Path(v0.cacheLocation()) / "emoji"
config_path = Path(v0.configLocation()) / "emoji"
data_path = Path(v0.dataLocation()) / "emoji"
dev_mode = True

stats_path = config_path / "stats"

# create plugin locations
for p in (cache_path, config_path, data_path):
    p.mkdir(parents=False, exist_ok=True)

if not stats_path.exists():
    with stats_path.open("wb") as f:
        pickle.dump({}, f)

# plugin main functions -----------------------------------------------------------------------

def parse_emojis():
    global emojis, emojis_li, label_to_emoji_tuple
    emojis = em.parse_emojis()
    emojis_li = list(emojis.items())

    # example:
    # label:  'folded_hands'
    # emoji_tuple:    ('🙏', ['folded_hands', 'please', 'hope', 'wish', 'namaste', 'highfive', 'pray'])
    for emoji_tuple in emojis.items():
        label_list = emoji_tuple[1]
        for label in label_list:
            label_to_emoji_tuple[label] = emoji_tuple


emojis_li = []
emojis = {}
label_to_emoji_tuple = {}
parse_emojis()
print("label_to_emoji_tuple: ", label_to_emoji_tuple)

def update_emojis():
    prev_len = len(emojis_li)
    parse_emojis()
    curr_len = len(emojis_li)

    if curr_len == prev_len:
        notify(msg=f"Found no new emojis - Total emojis count: {curr_len}")
    else:
        diff = curr_len - prev_len
        notify(
            msg=f'Found {diff} {"more" if diff > 0 else "less"} emojis - Total emojis count: {curr_len}'
        )


def get_stats():
    with stats_path.open("rb") as f:
        return pickle.load(f)


def update_stats(emoji: str):
    stats = get_stats()
    if emoji in stats:
        stats[emoji] += 1
    else:
        stats[emoji] = 1

    with stats_path.open("wb") as f:
        pickle.dump(stats, f)


def copy_emoji(emoji: str):
    update_stats(emoji)
    subprocess.run(f"echo {emoji} | xclip -r -selection clipboard", shell=True)


def initialize():
    """Called when the extension is loaded (ticked in the settings) - blocking."""
    pass


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

            if not query_str:
                results.append(get_reindex_item())
                recent = [
                    k
                    for k, _ in sorted(
                        get_stats().items(), key=lambda item: item[1], reverse=True
                    )[:10]
                ]
                results.extend([get_emoji_as_item((emoji, emojis[emoji])) for emoji in recent])

                if len(results) < 30:
                    results.extend(
                        get_emoji_as_item(emoji_tuple)
                        for emoji_tuple in emojis_li[: 30 - len(results)]
                    )
            else:
                matched = process.extract(
                    query_str, list(label_to_emoji_tuple.keys()), limit=30
                )
                # print("label_to_emoji_tuple.keys(): ", label_to_emoji_tuple.keys())
                # print("query_str: ", query_str)
                # print("matched: ", matched)
                # print("type(matched): ", type(matched))
                matched_emojis = list(
                    dict([label_to_emoji_tuple[label] for label, *_ in matched]).items()
                )
                results.extend(
                    [get_emoji_as_item(emoji_tuple) for emoji_tuple in matched_emojis]
                )

        except Exception:  # user to report error
            if dev_mode:  # let exceptions fly!
                v0.critical(traceback.format_exc())
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
def notify(
    msg: str,
    app_name: str = __title__,
    image=str(icon_path),
):
    Notify.init(app_name)
    n = Notify.Notification.new(app_name, msg, image)
    n.show()


def get_reindex_item():
    return get_as_item(
        text="Re-index list of emojis",
        actions=[v0.FuncAction("Re-index list of emojis", update_emojis)],
    )


def get_shell_cmd_as_item(
    *, text: str, command: str, subtext: str = None, completion: str = None
):
    """Return shell command as an item - ready to be appended to the items list and be rendered by Albert."""

    if subtext is None:
        subtext = text

    if completion is None:
        completion = f"{__triggers__}{text}"

    def run(command: str):
        proc = subprocess.run(command.split(" "), capture_output=True, check=False)
        if proc.returncode != 0:
            stdout = proc.stdout.decode("utf-8")
            stderr = proc.stderr.decode("utf-8")
            notify(f"Error when executing {command}\n\nstdout: {stdout}\n\nstderr: {stderr}")

    return v0.Item(
        id=__title__,
        icon=icon_path,
        text=text,
        subtext=subtext,
        completion=completion,
        actions=[
            v0.FuncAction(text, lambda command=command: run(command=command)),
        ],
    )


def get_as_item(*, text: str, actions: list, subtext: str = None, completion: str = None):
    if subtext is None:
        subtext = text

    if completion is None:
        completion = f"{__triggers__}{text}"

    """Return an item - ready to be appended to the items list and be rendered by Albert."""
    return v0.Item(
        id=__title__,
        icon=icon_path,
        text=text,
        subtext=subtext,
        completion=completion,
        actions=actions,
    )


def get_emoji_as_item(emoji_tuple: tuple):
    """Return an item - ready to be appended to the items list and be rendered by Albert."""
    emoji = emoji_tuple[0]
    labels = [label.replace("_", " ") for label in emoji_tuple[1]]
    main_label = labels[0]

    text = f"{emoji} {main_label}"
    subtext = " | ".join(labels[1:])
    return v0.Item(
        id=__title__,
        icon=icon_path,
        text=text,
        subtext=subtext,
        completion=f"{__triggers__}{main_label}",
        actions=[
            v0.FuncAction(f"Copy this emoji", lambda emoji=emoji: copy_emoji(emoji)),
            v0.UrlAction(
                f"Google this emoji", f"https://www.google.com/search?q={main_label} emoji"
            ),
        ],
    )


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


def load_data(data_name: str) -> str:
    """Load a piece of data from the configuration directory."""
    with open(config_path / data_name, "r") as f:
        data = f.readline().strip().split()[0]

    return data


def setup(query):
    """Setup is successful if an empty list is returned.

    Use this function if you need the user to provide you data
    """

    results = []
    if not which("em"):
        results.append(
            v0.Item(
                id=__title__,
                icon=icon_path,
                text=f'"em-keyboard" is not installed.',
                subtext='Please install and configure "em-keyboard" accordingly.',
                actions=[
                    v0.UrlAction(
                        "em-keyboard Github page", "https://github.com/hugovk/em-keyboard"
                    )
                ],
            )
        )
        return results

    return results
