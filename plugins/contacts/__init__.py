"""Contact VCF Viewer."""

import os
import json
import pickle
import subprocess
import sys
import time
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

__title__ = "Contact VCF Viewer"
__version__ = "0.4.0"
__triggers__ = "c "
__authors__ = "Nikos Koukis"
__homepage__ = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/contacts"
)
__exec_deps__ = []
__py_deps__ = []

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


def initialize():
    """Called when the extension is loaded (ticked in the settings) - blocking."""
    if vcf_path.is_file():
        reindex_contacts()


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

            # ---------------------------------------------------------------------------------
            if not query_str:
                results.append(
                    v0.Item(
                        id=__title__,
                        icon=icon_path,
                        completion=__triggers__,
                        text="Add more characters to fuzzy-search",
                        actions=[],
                    )
                )
                results.append(get_reindex_item())
            else:
                matched = process.extract(query_str, fullnames_to_contacts.keys(), limit=10)
                results.extend(
                    [get_contact_as_item(fullnames_to_contacts[m[0]]) for m in matched]
                )

        except Exception:  # user to report error
            v0.critical(traceback.format_exc())
            if dev_mode:  # let exceptions fly!
                raise
            else:
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
def get_reindex_item():
    return v0.Item(
        id=__title__,
        icon=icon_path,
        text="Re-index contacts",
        completion=__triggers__,
        actions=[v0.FuncAction("Re-index contacts", reindex_contacts)],
    )


def get_contact_as_item(contact: Contact):
    """Return an item - ready to be appended to the items list and be rendered by Albert."""
    text = contact.fullname
    phones_and_emails = set(contact.emails).union(contact.telephones)
    subtext = " | ".join(phones_and_emails)
    completion = f"{__triggers__}{contact.fullname}"

    actions = []

    for field in phones_and_emails:
        actions.append(v0.ClipAction(f"Copy {field}", field))

    actions.append(v0.ClipAction("Copy name", contact.fullname))

    return v0.Item(
        id=__title__,
        icon=icon_path,
        text=text,
        subtext=subtext,
        completion=completion,
        actions=actions,
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


def setup(query):  # type: ignore
    results = []

    if not which("vcfxplr"):
        results.append(
            v0.Item(
                id=__title__,
                icon=icon_path,
                text=f'"vcfxplr" is not installed.',
                subtext="You can install it via pip - <u>pip3 install --user --upgrade vcfxplr</u>",
                completion=__triggers__,
                actions=[
                    v0.ClipAction(
                        "Copy install command", "pip3 install --user --upgrade vcfxplr"
                    ),
                    v0.UrlAction(
                        'Open "vcfxplr" page', "https://github.com/bergercookie/vcfxplr"
                    ),
                ],
            )
        )
        return results

    if vcf_path.exists() and not vcf_path.is_file():
        raise RuntimeError(f"vcf file exists but it's not a file -> {vcf_path}")

    if not vcf_path.exists():
        results.append(
            v0.Item(
                id=__title__,
                icon=icon_path,
                text=f"Please input the path to your VCF contacts file.",
                subtext=f"{query.string}",
                completion=__triggers__,
                actions=[
                    v0.FuncAction(
                        "Save VCF file", lambda query=query: save_vcf_file(query.string)
                    ),
                ],
            )
        )

    return results
