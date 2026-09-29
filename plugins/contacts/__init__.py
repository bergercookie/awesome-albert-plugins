"""Contact VCF Viewer."""

import json
import subprocess
import traceback
from pathlib import Path
from shutil import copyfile, which
from typing import Any, Dict, Iterator, List, Optional, Sequence

import gi
from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    PluginInstance,
    StandardItem,
    openUrl,
    setClipboardText,
)
from fuzzywuzzy import process

gi.require_version("Notify", "0.7")  # isort:skip
gi.require_version("GdkPixbuf", "2.0")  # isort:skip
from gi.repository import GdkPixbuf, Notify  # isort:skip  # type: ignore

md_iid = "5.0"
md_version = "0.3"
md_name = "Contacts"
md_description = "Contact VCF Viewer"
md_url = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/contacts"
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["fuzzywuzzy"]
md_bin_dependencies = ["vcfxplr"]
ICON_PATH = Path(__file__).parent / "contacts.png"


class Contact:
    def __init__(
        self,
        fullname: str,
        telephones: Optional[Sequence[str]],
        emails: Optional[Sequence[str]] = None,
    ):
        self._fullname = fullname
        self._telephones = telephones or []
        self._emails = emails or []

    @property
    def fullname(self) -> str:
        return self._fullname

    @property
    def telephones(self) -> Sequence[str]:
        return self._telephones

    @property
    def emails(self) -> Sequence[str]:
        return self._emails

    @classmethod
    def parse(cls, k, v):
        def values(name: str) -> Sequence[Any]:
            array = v.get(name)
            if array is None:
                return []

            return [item["value"] for item in array]

        return cls(
            fullname=k,
            telephones=[tel.replace(" ", "") for tel in values("tel")],
            emails=values("email"),
        )


# FileBackedVar class -------------------------------------------------------------------------
class FileBackedVar:
    def __init__(self, config_path, varname, convert_fn=str, init_val=None):
        self._fpath = config_path / varname
        self._convert_fn = convert_fn

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


# plugin main functions -----------------------------------------------------------------------


def do_notify(msg: str, image=None):
    app_name = "Contacts"
    Notify.init(app_name)
    image = image
    n = Notify.Notification.new(app_name, msg, image)
    n.show()


# supplementary functions ---------------------------------------------------------------------
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


# main plugin class ------------------------------------------------------------
class Plugin(PluginInstance, GeneratorQueryHandler):
    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)

        self.cache_path = Path(self.cacheLocation()) / "contacts"
        self.config_path = Path(self.configLocation()) / "contacts"
        self.data_path = Path(self.dataLocation()) / "contacts"

        for p in (self.cache_path, self.config_path, self.data_path):
            p.mkdir(parents=True, exist_ok=True)

        self.stats_path = self.config_path / "stats"
        self.vcf_path = self.cache_path / "contacts.vcf"

        self.contacts: List[Contact] = []
        self.fullnames_to_contacts: Dict[str, Contact] = {}

        if self.vcf_path.is_file():
            self.reindex_contacts()

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "c "

    def synopsis(self, query):
        return "TODO"

    # -- contacts index ------------------------------------------------------------------------

    def reindex_contacts(self) -> None:
        self.contacts = self.get_new_contacts()
        self.fullnames_to_contacts = {c.fullname: c for c in self.contacts}

    def get_new_contacts(self) -> List[Contact]:
        proc = subprocess.run(
            ["vcfxplr", "-c", str(self.vcf_path), "json", "-g", "fn"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        contacts_json = json.loads(proc.stdout)
        return [Contact.parse(k, v) for k, v in contacts_json.items()]

    def save_data(self, data: str, data_name: str):
        """Save a piece of data in the configuration directory."""
        with open(self.config_path / data_name, "w") as f:
            f.write(data)

    def load_data(self, data_name: str) -> str:
        """Load a piece of data from the configuration directory."""
        with open(self.config_path / data_name, "r") as f:
            data = f.readline().strip().split()[0]

        return data

    def data_exists(self, data_name: str) -> bool:
        """Check whwether a piece of data exists in the configuration directory."""
        return (self.config_path / data_name).is_file()

    def save_vcf_file(self, query: str):
        p = Path(query).expanduser().absolute()
        if not p.is_file():
            do_notify(f'Given path "{p}" is not valid - please input it again.')

        copyfile(p, self.vcf_path)
        self.reindex_contacts()
        do_notify(f"Copied VCF contacts file to -> {self.vcf_path}. You should be ready to go...")

    def setup(self, ctx) -> Optional[List[StandardItem]]:
        """Return the setup items the user has to deal with first - None if there's nothing
        to set up.
        """
        if not which("vcfxplr"):
            return [
                StandardItem(
                    id=f"{self.id()}.vcfxplr-missing",
                    icon_factory=self.makeIcon,
                    text='"vcfxplr" is not installed.',
                    subtext=(
                        "You can install it via pip - <u>pip3 install --user --upgrade vcfxplr</u>"
                    ),
                    actions=[
                        Action(
                            "copy",
                            "Copy install command",
                            lambda: setClipboardText(
                                "pip3 install --user --upgrade vcfxplr"
                            ),
                        ),
                        Action(
                            "open",
                            'Open "vcfxplr" page',
                            lambda: openUrl("https://github.com/bergercookie/vcfxplr"),
                        ),
                    ],
                )
            ]

        if self.vcf_path.exists() and not self.vcf_path.is_file():
            raise RuntimeError(f"vcf file exists but it's not a file -> {self.vcf_path}")

        if not self.vcf_path.exists():
            return [
                StandardItem(
                    id=f"{self.id()}.vcf-setup",
                    icon_factory=self.makeIcon,
                    text="Please input the path to your VCF contacts file.",
                    subtext=f"{ctx.query}",
                    actions=[
                        Action(
                            "save", "Save VCF file", lambda q=ctx.query: self.save_vcf_file(q)
                        ),
                    ],
                )
            ]

        return None

    # -- items --------------------------------------------------------------------------------

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

    def get_reindex_item(self, ctx) -> StandardItem:
        return StandardItem(
            id=f"{self.id()}.reindex",
            icon_factory=self.makeIcon,
            text="Re-index contacts",
            input_action_text=ctx.trigger,
            actions=[Action("reindex", "Re-index contacts", self.reindex_contacts)],
        )

    def get_contact_as_item(self, ctx, contact: Contact) -> StandardItem:
        """
        Return an item - ready to be appended to the items list and be rendered by Albert.
        """
        text = contact.fullname
        phones_and_emails = set(contact.emails).union(contact.telephones)
        subtext = " | ".join(phones_and_emails)
        completion = f"{ctx.trigger}{contact.fullname}"

        actions = []

        for field in phones_and_emails:
            actions.append(Action("copy", f"Copy {field}", lambda f=field: setClipboardText(f)))

        actions.append(Action("copy", "Copy name", lambda: setClipboardText(contact.fullname)))

        return StandardItem(
            id=f"{self.id()}.contact-{contact.fullname}",
            icon_factory=self.makeIcon,
            text=text,
            subtext=subtext,
            input_action_text=completion,
            actions=actions,
        )

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        """Hook that is called by albert with *every new keypress*."""  # noqa
        results = []

        try:
            results_setup = self.setup(ctx)
            if results_setup is not None:
                yield results_setup
                return

            query_str = ctx.query

            if not query_str:
                results.append(
                    StandardItem(
                        id=f"{self.id()}.hint",
                        icon_factory=self.makeIcon,
                        input_action_text=ctx.trigger,
                        text="Add more characters to fuzzy-search",
                        actions=[],
                    )
                )
                results.append(self.get_reindex_item(ctx))
            else:
                matched = process.extract(query_str, self.fullnames_to_contacts.keys(), limit=10)
                results.extend(
                    [
                        self.get_contact_as_item(ctx, self.fullnames_to_contacts[m[0]])
                        for m in matched
                    ]
                )

            yield results

        except Exception:  # user to report error
            trace = traceback.format_exc()
            print(trace)

            yield [self.get_error_item(trace)]
