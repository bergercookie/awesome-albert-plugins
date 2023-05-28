"""Create new anki cards fast."""

import json
import re
import traceback
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

import albert as v0
import httpx
from gi.repository import GdkPixbuf, Notify

md_name = "Anki"
md_description = "Anki Interaction - Create new anki cards fast"
md_iid = "0.5"
md_version = "0.2"
md_maintainers = "Nikos Koukis"
md_url = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/anki"
md_bin_dependencies = ["anki"]
md_lib_dependencies = ["httpx", "fuzzywuzzy"]

notif_title = "Anki Interaction"  # Custom metadata

icon_path = str(Path(__file__).parent / "anki")

cache_path = Path(v0.cacheLocation()) / "anki"
config_path = Path(v0.configLocation()) / "anki"
data_path = Path(v0.dataLocation()) / "anki"

# create plugin locations
for p in (cache_path, config_path, data_path):
    p.mkdir(parents=False, exist_ok=True)

AVAIL_NOTE_TYPES = {
    "basic": "Basic",
    "basic-reverse": "Basic (and reversed card)",
    "cloze": "Cloze",
}


curr_trigger: str = ""


# FileBackedVar class -------------------------------------------------------------------------
class FileBackedVar:
    def __init__(self, varname: str, convert_fn: Callable = str, init_val: Any = None):
        self._fpath = config_path / varname
        self._convert_fn = convert_fn

        # if the config path doesn't exist, do create it. This may run before the albert
        # initialisation function

        if init_val:
            with open(self._fpath, "w") as f:
                f.write(str(init_val))
        else:
            self._fpath.touch()

    def get(self):
        with open(self._fpath, "r") as f:
            return self._convert_fn(f.read().strip())

    def set(self, val):
        with open(self._fpath, "w") as f:
            return f.write(str(val))


deck_name = FileBackedVar(varname="deck_name", init_val="scratchpad")

# interact with ankiconnect -------------------------------------------------------------------


def anki_post(action, **params) -> Any:
    def request(action, **params):
        return {"action": action, "params": params, "version": 6}

    req_json = json.dumps(request(action, **params)).encode("utf-8")
    response = httpx.post(url="http://localhost:8765", content=req_json).json()
    if len(response) != 2:
        raise RuntimeError("Response has an unexpected number of fields")
    if "error" not in response:
        raise RuntimeError("Response is missing required error field")
    if "result" not in response:
        raise RuntimeError("Response is missing required result field")
    if response["error"] is not None:
        raise RuntimeError(response["error"])
    return response["result"]


# plugin main functions -----------------------------------------------------------------------


def add_anki_note(note_type: str, **kargs):
    """
    :param kargs: Parameters passed directly to the "notes" section of the POST request
    """
    deck = deck_name.get()

    # make sure that the deck is already created, otherwise adding the note will fail
    anki_post("createDeck", deck=deck)

    if note_type not in AVAIL_NOTE_TYPES.values():
        raise RuntimeError(f"Unexpected note type -> {note_type}")

    params = {
        "action": "addNotes",
        "notes": [
            {
                "deckName": deck,
                "modelName": note_type,
                "tags": ["albert"],
            }
        ],
    }
    params["notes"][0].update(kargs)

    resp = anki_post(**params)
    if resp[0] is None:
        notify(f"Unable to add new note, params:\n\n{params}")


# supplementary functions ---------------------------------------------------------------------
def notify(
    msg: str,
    app_name: str = notif_title,
    image=str(icon_path),
):
    Notify.init(app_name)
    n = Notify.Notification.new(app_name, msg, image)
    n.show()


def get_as_item(**kargs) -> v0.Item:
    if "icon" in kargs:
        icon = kargs.pop("icon")
    else:
        icon = icon_path
    return v0.Item(id=notif_title, icon=[icon], **kargs)


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


# subcommands ---------------------------------------------------------------------------------
class Subcommand:
    def __init__(self, *, name, desc):
        self.name = name
        self.desc = desc

    def get_as_albert_item(self, *args, **kargs):
        return get_as_item(
            text=self.desc, completion=f"{curr_trigger}{self.name} ", *args, **kargs
        )

    def get_as_albert_items_full(self, query_str: str):
        return [self.get_as_albert_item()]

    def __str__(self) -> str:
        return f"Name: {self.name} | Description: {self.desc}"


class ChangeDeck(Subcommand):
    usage_str = "Type the new deck name"

    def __init__(self):
        super(ChangeDeck, self).__init__(
            name="change-deck", desc="Change the default deck to dump new notes to"
        )

    def get_as_albert_items_full(self, query_str: str):
        item = self.get_as_albert_item(
            subtext=ChangeDeck.usage_str if not query_str else f"Deck to use: {query_str}",
            actions=[
                FuncAction(
                    "Change deck",
                    lambda new_deck_name=query_str: ChangeDeck.change_to(new_deck_name),
                )
            ],
        )
        return [item]

    @staticmethod
    def change_to(new_deck_name: str):
        # check that that deck exists already:
        avail_decks = anki_post("deckNames")
        if new_deck_name not in avail_decks:
            notify(
                "Given deck doesn't exist. Try again with one of the following"
                f" names:\n\n{avail_decks}"
            )
            return

        global deck_name
        deck_name.set(new_deck_name)
        notify(f"New deck name: {deck_name.get()}")


class AddClozeNote(Subcommand):
    usage_str = "USAGE: Add text including notations like {{c1::this one}}"

    def __init__(self):
        super(AddClozeNote, self).__init__(
            name="cloze",
            desc="Add a new cloze note. Use {{c1:: ... }}, {{c2:: ... }} and so forth",
        )

    def get_as_albert_items_full(self, query_str: str):
        if self.detect_cloze_note(query_str):
            subtext = query_str
        else:
            subtext = AddClozeNote.usage_str

        actions = [
            FuncAction(
                "Add a new cloze note",
                lambda cloze_text=query_str: self.add_cloze_note(cloze_text=cloze_text),
            )
        ]

        item = self.get_as_albert_item(subtext=subtext, actions=actions)
        return [item]

    def detect_cloze_note(self, cloze_text: str):
        return re.search("{{.*}}", cloze_text)

    def add_cloze_note(self, cloze_text: str):
        if not self.detect_cloze_note(cloze_text):
            notify(f"Not a valid cloze text: {cloze_text}")
            return

        add_anki_note(
            note_type="Cloze",
            fields={"Text": cloze_text, "Extra": ""},
            options={"clozeAfterAdding": True},
        )


class AddBasicNote(Subcommand):
    usage_str = "USAGE: front content | back content"

    def __init__(self, with_reverse):
        if with_reverse:
            self.name = "basic-reverse"
            self.note_type = AVAIL_NOTE_TYPES[self.name]
        else:
            self.name = "basic"
            self.note_type = "Basic"

        super(AddBasicNote, self).__init__(name=self.name, desc=f"Add a new {self.name} note")

    def get_as_albert_items_full(self, query_str: str):
        query_parts = AddBasicNote.parse_query_str(query_str)
        if query_parts:
            front = query_parts[0]
            back = query_parts[1]
            subtext = f'{front} | {back}'
        else:
            subtext = AddBasicNote.usage_str

        actions = [
            FuncAction(
                f"Add {self.name} Note",
                lambda query_str=query_str: self.add_anki_note(query_str),
            )
        ]
        item = self.get_as_albert_item(subtext=subtext, actions=actions)
        return [item]

    @staticmethod
    def parse_query_str(query_str: str) -> Optional[Tuple[str, str]]:
        """Parse the front and back contents. Return None if parsing fails."""
        sep = "|"
        if sep not in query_str:
            return

        parts = query_str.split("|")
        if len(parts) != 2:
            return

        return parts  # type: ignore

    def add_anki_note(self, query_str: str):
        parts = AddBasicNote.parse_query_str(query_str)
        if parts is None:
            notify(msg=AddBasicNote.usage_str)
            return

        front, back = parts
        add_anki_note(note_type=self.note_type, fields={"Front": front, "Back": back})


class SubcommandQuery:
    def __init__(self, subcommand: Subcommand, query: str):
        """
        Query for a specific subcommand.

        :query: Query text - doesn't include the subcommand itself
        """

        self.command = subcommand
        self.query = query

    def __str__(self) -> str:
        return f"Command: {self.command}\nQuery Text: {self.query}"


def create_subcommands():
    return [
        AddBasicNote(with_reverse=False),
        AddBasicNote(with_reverse=True),
        AddClozeNote(),
        ChangeDeck(),
    ]


subcommands = create_subcommands()


def get_subcommand_for_name(name: str) -> Optional[Subcommand]:
    """Get a subcommand with the indicated name."""
    matching = [s for s in subcommands if s.name.lower() == name.lower()]
    if matching:
        return matching[0]


def get_subcommand_query(query_str: str) -> Optional[SubcommandQuery]:
    """
    Determine whether current query is of a subcommand.

    If so first returned the corresponding SubcommandQeury object.
    """
    if not query_str:
        return None

    # spilt:
    # "subcommand_name rest of query" -> ["subcommand_name", "rest of query""]
    query_parts = query_str.strip().split(None, maxsplit=1)

    if len(query_parts) < 2:
        query_str = ""
    else:
        query_str = query_parts[1]

    subcommand = get_subcommand_for_name(query_parts[0])
    if subcommand:
        return SubcommandQuery(subcommand=subcommand, query=query_str)


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
        return "anki "

    def synopsis(self):
        return "new card content"

    def initialize(self):
        pass

    def finalize(self):
        pass

    def handleQuery(self, query) -> None:
        """Hook that is called by albert with *every new keypress*."""  # noqa
        results = []

        global curr_trigger
        curr_trigger = query.trigger

        try:
            query_str = query.string
            if len(query_str) < 2:
                results.extend([s.get_as_albert_item() for s in subcommands])

            else:
                subcommand_query = get_subcommand_query(query_str)

                if subcommand_query:
                    results.extend(
                        subcommand_query.command.get_as_albert_items_full(
                            subcommand_query.query
                        )
                    )

        except Exception:  # user to report error
            v0.critical(traceback.format_exc())

            results.insert(
                0,
                v0.Item(
                    id=notif_title,
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

        query.add(results)
