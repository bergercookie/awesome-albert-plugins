"""Create new anki cards fast."""

import json
import re
import traceback
from pathlib import Path
from typing import Any, Callable, Iterator, List, Optional, Tuple

import httpx
from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    Notification,
    PluginInstance,
    StandardItem,
    setClipboardText,
)

md_name = "Anki"
md_description = "Anki Interaction - Create new anki cards fast"
md_iid = "5.0"
md_version = "0.3"
md_license = "MIT"
md_url = "https://github.com/bergercookie/awesome-albert-plugins"
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["httpx"]
notif_title = "Anki Interaction"  # Custom metadata

ICON_PATH = Path(__file__).parent / "anki.png"

AVAIL_NOTE_TYPES = {
    "basic": "Basic",
    "basic-reverse": "Basic (and reversed card)",
    "cloze": "Cloze",
}


curr_trigger: str = ""


# FileBackedVar class -------------------------------------------------------------------------
class FileBackedVar:
    def __init__(
        self,
        varname: str,
        convert_fn: Callable = str,
        init_val: Any = None,
        config_dir: Path = None,
    ):
        self._config_dir = config_dir
        self._varname = varname
        self._fpath = (config_dir / varname) if config_dir else None
        self._convert_fn = convert_fn

        self._init_val = init_val

    def bind(self, config_dir: Path) -> "FileBackedVar":
        """Point this var at the plugin's config dir and materialise the file."""
        self._config_dir = config_dir
        self._fpath = config_dir / self._varname
        self._fpath.parent.mkdir(parents=True, exist_ok=True)

        if self._init_val and not self._fpath.is_file():
            with open(self._fpath, "w") as f:
                f.write(str(self._init_val))
        elif not self._fpath.is_file():
            self._fpath.touch()

        return self

    def _path(self) -> Path:
        if self._fpath is None:
            self.bind(DEFAULT_CONFIG_DIR)
        return self._fpath

    def get(self):
        with open(self._path(), "r") as f:
            return self._convert_fn(f.read().strip() or (self._init_val or ""))

    def set(self, val):
        with open(self._path(), "w") as f:
            return f.write(str(val))


# The config dir is only known once a PluginInstance exists, so this is a lazy
# proxy: the backing file is created on first use.
# Albert's config location is only available on a PluginInstance; this is
# replaced with the real path in Plugin.__init__.
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "albert" / "anki"

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
):
    Notification(app_name, msg).send()


def get_as_item(**kargs) -> StandardItem:
    if "icon" in kargs:
        icon = kargs.pop("icon")
    else:
        icon = str(ICON_PATH)
    # item ids drive de-duplication, so derive a stable one from the text
    kargs.setdefault("id", f"anki-{kargs.get('text', '')}")
    return StandardItem(icon_factory=lambda: Icon.image(icon), **kargs)


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


# subcommands ---------------------------------------------------------------------------------
class Subcommand:
    def __init__(self, *, name, desc):
        self.name = name
        self.desc = desc

    def get_as_albert_item(self, *args, **kargs):
        return get_as_item(
            text=self.desc, input_action_text=f"{curr_trigger}{self.name} ", *args, **kargs
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
                Action(
                    "change-deck",
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
            Action(
                "add-note",
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
            subtext = f"{front} | {back}"
        else:
            subtext = AddBasicNote.usage_str

        actions = [
            Action(
                "add-note",
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

        deck_name.bind(self.config_path)

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "anki "

    def synopsis(self, query):
        return "new card content"

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        """Yield the subcommand items for the current query."""
        results = []

        global curr_trigger
        curr_trigger = ctx.trigger

        try:
            query_str = ctx.query
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
            trace = traceback.format_exc()
            critical(trace)

            results.insert(
                0,
                StandardItem(
                    id="anki-error",
                    icon_factory=self.makeIcon,
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        Action(
                            "copy",
                            f"Copy error - report it to {md_url[8:]}",
                            lambda: setClipboardText(trace),
                        )
                    ],
                ),
            )

        yield results
