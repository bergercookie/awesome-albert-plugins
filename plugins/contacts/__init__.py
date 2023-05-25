"""Contact VCF Viewer."""

import json
import subprocess
import traceback
from pathlib import Path
from shutil import copyfile, which
from typing import Any, Dict, List, Optional, Sequence

import albert as v0
import gi
from fuzzywuzzy import process

gi.require_version("Notify", "0.7")  # isort:skip
gi.require_version("GdkPixbuf", "2.0")  # isort:skip
from gi.repository import GdkPixbuf, Notify  # isort:skip  # type: ignore

md_name = "Contacts"
md_description = "Contact VCF Viewer"
md_iid = "0.5"
md_version = "0.5"
md_maintainers = "Nikos Koukis"
md_url = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/contacts"
md_bin_dependencies = []
md_lib_dependencies = []

icon_path = str(Path(__file__).parent / "contacts")

cache_path = Path(v0.cacheLocation()) / "contacts"
config_path = Path(v0.configLocation()) / "contacts"
data_path = Path(v0.dataLocation()) / "contacts"
dev_mode = True

stats_path = config_path / "stats"
vcf_path = Path(cache_path / "contacts.vcf")


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


contacts: List[Contact]
fullnames_to_contacts: Dict[str, Contact]

# create plugin locations
for p in (cache_path, config_path, data_path):
    p.mkdir(parents=False, exist_ok=True)


def reindex_contacts() -> None:
    global contacts, fullnames_to_contacts
    contacts = get_new_contacts()
    fullnames_to_contacts = {c.fullname: c for c in contacts}


def get_new_contacts() -> List[Contact]:
    proc = subprocess.run(
        ["vcfxplr", "-c", str(vcf_path), "json", "-g", "fn"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    contacts_json = json.loads(proc.stdout)
    return [Contact.parse(k, v) for k, v in contacts_json.items()]


# FileBackedVar class -------------------------------------------------------------------------
class FileBackedVar:
    def __init__(self, varname, convert_fn=str, init_val=None):
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


def save_data(data: str, data_name: str):
    """Save a piece of data in the configuration directory."""
    with open(config_path / data_name, "w") as f:
        f.write(data)


def load_data(data_name: str) -> str:
    """Load a piece of data from the configuration directory."""
    with open(config_path / data_name, "r") as f:
        data = f.readline().strip().split()[0]

    return data


def data_exists(data_name: str) -> bool:
    """Check whwether a piece of data exists in the configuration directory."""
    return (config_path / data_name).is_file()


def save_vcf_file(query: str):
    p = Path(query).expanduser().absolute()
    if not p.is_file():
        do_notify(f'Given path "{p}" is not valid - please input it again.')

    copyfile(p, vcf_path)
    reindex_contacts()
    do_notify(f"Copied VCF contacts file to -> {vcf_path}. You should be ready to go...")


def setup(query) -> bool:  # type: ignore
    if not which("vcfxplr"):
        query.add(
            v0.Item(
                id=md_name,
                icon=[icon_path],
                text='"vcfxplr" is not installed.',
                subtext=(
                    "You can install it via pip - <u>pip3 install --user --upgrade vcfxplr</u>"
                ),
                actions=[
                    ClipAction(
                        "Copy install command", "pip3 install --user --upgrade vcfxplr"
                    ),
                    UrlAction(
                        'Open "vcfxplr" page', "https://github.com/bergercookie/vcfxplr"
                    ),
                ],
            )
        )
        return True

    if vcf_path.exists() and not vcf_path.is_file():
        raise RuntimeError(f"vcf file exists but it's not a file -> {vcf_path}")

    if not vcf_path.exists():
        query.add(
            v0.Item(
                id=md_name,
                icon=[icon_path],
                text="Please input the path to your VCF contacts file.",
                subtext=f"{query.string}",
                actions=[
                    FuncAction(
                        "Save VCF file", lambda query=query: save_vcf_file(query.string)
                    ),
                ],
            )
        )

        return True

    return False


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
        return "c "

    def synopsis(self):
        return "TODO"

    def initialize(self):
        """Called when the extension is loaded (ticked in the settings) - blocking."""
        if vcf_path.is_file():
            reindex_contacts()

    def finalize(self):
        pass

    def handleQuery(self, query) -> None:
        """Hook that is called by albert with *every new keypress*."""  # noqa
        results = []

        try:
            results_setup = setup(query)
            if results_setup:
                return

            query_str = query.string

            if not query_str:
                results.append(
                    v0.Item(
                        id=md_name,
                        icon=[icon_path],
                        completion=query.trigger,
                        text="Add more characters to fuzzy-search",
                        actions=[],
                    )
                )
                results.append(self.get_reindex_item(query))
            else:
                matched = process.extract(query_str, fullnames_to_contacts.keys(), limit=10)
                results.extend(
                    [
                        self.get_contact_as_item(query, fullnames_to_contacts[m[0]])
                        for m in matched
                    ]
                )

            query.add(results)

        except Exception:  # user to report error
            v0.critical(traceback.format_exc())
            if dev_mode:  # let exceptions fly!
                raise
            else:
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

    def get_reindex_item(self, query):
        return v0.Item(
            id=md_name,
            icon=[icon_path],
            text="Re-index contacts",
            completion=query.trigger,
            actions=[FuncAction("Re-index contacts", reindex_contacts)],
        )

    def get_contact_as_item(self, query, contact: Contact):
        """
        Return an item - ready to be appended to the items list and be rendered by Albert.
        """
        text = contact.fullname
        phones_and_emails = set(contact.emails).union(contact.telephones)
        subtext = " | ".join(phones_and_emails)
        completion = f"{query.trigger}{contact.fullname}"

        actions = []

        for field in phones_and_emails:
            actions.append(ClipAction(f"Copy {field}", field))

        actions.append(ClipAction("Copy name", contact.fullname))

        return v0.Item(
            id=md_name,
            icon=[icon_path],
            text=text,
            subtext=subtext,
            completion=completion,
            actions=actions,
        )
