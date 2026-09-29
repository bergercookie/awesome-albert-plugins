"""Contact VCF Viewer."""

import json
import subprocess
import traceback
from pathlib import Path
from shutil import which
from typing import Any, Dict, Iterator, List, Optional, Sequence

from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    Notification,
    PluginInstance,
    StandardItem,
    openUrl,
    setClipboardText,
)
from fuzzywuzzy import process

md_iid = "5.0"
md_version = "0.3"
md_name = "Contacts"
md_description = "Contact VCF Viewer"
md_url = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/contacts"
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["fuzzywuzzy", "vcfxplr"]
md_bin_dependencies = []
ICON_PATH = Path(__file__).parent / "contacts.png"

CONFIG_VCF_PATH = "vcf_path"


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


# plugin main functions -----------------------------------------------------------------------


def do_notify(msg: str):
    app_name = "Contacts"
    Notification(app_name, msg).send()


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
        self.cache_path.mkdir(parents=True, exist_ok=True)

        configured = self.readConfig(CONFIG_VCF_PATH, str) or ""
        if configured:
            self._vcf_path: Optional[Path] = Path(configured).expanduser()
        else:
            # releases before the vcf path became configurable kept a copy in the cache
            legacy = self.cache_path / "contacts.vcf"
            self._vcf_path = legacy if legacy.is_file() else None

        self.contacts: List[Contact] = []
        self.fullnames_to_contacts: Dict[str, Contact] = {}

        if self._vcf_path is not None and self._vcf_path.is_file():
            try:
                self.reindex_contacts()
            except Exception:  # keep the plugin usable, the file may be half-written
                traceback.print_exc()

    # -- config, bound to the settings widget below -----------------------

    @property
    def vcf_path(self) -> str:
        return "" if self._vcf_path is None else str(self._vcf_path)

    @vcf_path.setter
    def vcf_path(self, value: str):
        value = (value or "").strip()

        if not value:
            self._vcf_path = None
            self._reset_contacts()
            self.writeConfig(CONFIG_VCF_PATH, "")
            return

        # store the raw string so a typo is preserved and can be corrected
        self.writeConfig(CONFIG_VCF_PATH, value)
        self._vcf_path = Path(value).expanduser()

        if not self._vcf_path.is_file():
            self._reset_contacts()
            do_notify(f'"{self._vcf_path}" is not a file - please check the plugin settings.')
            return

        try:
            self.reindex_contacts()
        except Exception:
            self._reset_contacts()
            traceback.print_exc()
            do_notify(f'Could not parse "{self._vcf_path}" - see the Albert logs.')

    def configWidget(self):
        return [
            {
                "type": "label",
                "text": (
                    "Path to the vCard (.vcf) file to search, e.g. an export of your Google, "
                    "Nextcloud or Thunderbird contacts. The file is read in place rather than copied, "
                    "so edits show up after the next re-index."
                ),
            },
            {
                "type": "lineedit",
                "property": "vcf_path",
                "label": "Contacts VCF file",
                "widget_properties": {"placeholderText": "/home/you/contacts.vcf"},
            },
        ]

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "c "

    def synopsis(self, query):
        return "TODO"

    # -- contacts index ------------------------------------------------------------------------

    def _reset_contacts(self) -> None:
        self.contacts = []
        self.fullnames_to_contacts = {}

    def reindex_contacts(self) -> None:
        self.contacts = self.get_new_contacts()
        self.fullnames_to_contacts = {c.fullname: c for c in self.contacts}

    def get_new_contacts(self) -> List[Contact]:
        proc = subprocess.run(
            ["vcfxplr", "-c", str(self._vcf_path), "json", "-g", "fn"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        contacts_json = json.loads(proc.stdout)
        return [Contact.parse(k, v) for k, v in contacts_json.items()]

    def clear_vcf_path(self):
        """Forget the configured VCF file, so the setup prompt reappears."""
        self.vcf_path = ""

    def save_vcf_file(self, query: str):
        """Point the plugin at a VCF file, for users who prefer the prompt over the settings UI."""
        self.vcf_path = query
        if self._vcf_path is not None and self._vcf_path.is_file():
            do_notify(
                f"Reading contacts from -> {self._vcf_path}. You should be ready to go..."
            )

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
                            lambda: setClipboardText("pip3 install --user --upgrade vcfxplr"),
                        ),
                        Action(
                            "open",
                            'Open "vcfxplr" page',
                            lambda: openUrl("https://github.com/bergercookie/vcfxplr"),
                        ),
                    ],
                )
            ]

        if self._vcf_path is None:
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

        if not self._vcf_path.is_file():
            return [
                StandardItem(
                    id=f"{self.id()}.vcf-missing",
                    icon_factory=self.makeIcon,
                    text=f"Contacts file not found: {self._vcf_path}",
                    subtext="Fix the path in the plugin settings, or enter a new one here.",
                    actions=[
                        Action(
                            "save",
                            "Use this file instead",
                            lambda q=ctx.query: self.save_vcf_file(q),
                        ),
                        Action("reset", "Forget the configured path", self.clear_vcf_path),
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
            actions.append(
                Action("copy", f"Copy {field}", lambda f=field: setClipboardText(f))
            )

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
                matched = process.extract(
                    query_str, self.fullnames_to_contacts.keys(), limit=10
                )
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
