"""Meme Generator - Generate memes with custom quotes - ready to be copied / uploaded / shared at an instant."""

import shutil
import subprocess
import traceback
from pathlib import Path
from typing import Iterator, List

from fuzzywuzzy import process
from gi.repository import GdkPixbuf, Notify

from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    PluginInstance,
    StandardItem,
    setClipboardText,
)

md_name = "Meme"
md_description = (
    "Meme Generator - Generate memes with custom quotes - ready to be copied / uploaded /"
    " shared at an instant"
)
md_iid = "5.0"
md_version = "0.3"
md_license = "MIT"
md_url = "https://github.com/bergercookie/awesome-albert-plugins"
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["fuzzywuzzy"]
md_bin_dependencies = ["convert", "meme", "xclip"]
ICON_PATH = Path(__file__).parent / "meme-generator"

# plugin main functions -----------------------------------------------------------------------
def import_template_ids() -> List[str]:
    """Return a list of all the supported template IDs."""
    if not shutil.which("meme"):
        raise RuntimeError(
            'Cannot find the "meme" go package - "'
            "Are you sure you installed https://github.com/nomad-software/meme?"
        )
    return subprocess.check_output(["meme", "-list-templates"]).decode("utf-8").splitlines()


def get_template_img(meme_id: str) -> Path:
    """Get the path to the template image, given the template meme ID."""
    # may be a bit fragile - TODO Find a better way to do it.
    bin_path = Path(shutil.which("meme")).parent  # type: ignore
    meme_reg_path = bin_path.parent / "pkg" / "mod" / "github.com" / "nomad-software"
    meme_reg_versions = list(meme_reg_path.glob("meme@*"))

    if not meme_reg_versions:
        raise RuntimeError(f'Can\'t find any Go "meme" packages under {meme_reg_path}')

    # use the most recent versions
    return meme_reg_versions[0] / "data" / "images" / f"{meme_id}.jpg"


class Template:
    def __init__(self, id: str):
        self.id = id
        self.img = get_template_img(id)

    def title(self) -> str:
        return self.id.replace("-", " ").capitalize()

    @property
    def albert_id(self):
        return f"{md_name}_{self.id}"

    def get_as_item(self, query):
        """Return it as item - ready to be appended to the items list and be rendered by
        Albert.
        """
        return StandardItem(
            id=self.albert_id,
            icon_factory=lambda: Icon.image(str(self.img)),
            text=self.title(),
            subtext="",
            input_action_text=f"{query.trigger} {self.id} ",
            actions=[
                Action("copy", "Copy vanilla image", lambda: self.copy_vanilla_img()),
                Action("copy", "Copy vanilla image path", lambda: setClipboardText(str(self.img))),
            ],
        )

    def _create_custom_meme(self, caption1: str, caption2: str) -> Path:
        output = "/tmp/albert-meme.png"
        subprocess.check_call(
            ["meme", "-i", self.id, "-o", output, "-t", f"{caption1}|{caption2}"]
        )

        return Path(output)

    def _create_n_copy_to_clipboard(self, caption1: str, caption2: str):
        p = self._create_custom_meme(caption1=caption1, caption2=caption2)
        subprocess.check_call(["xclip", "-selection", "clipboard", "-t", "image/png", str(p)])

    def _create_n_copy_path_to_clipboard(self, caption1: str, caption2: str):
        p = self._create_custom_meme(caption1=caption1, caption2=caption2)
        subprocess.Popen(f"echo {p}| xclip -selection clipboard", shell=True)

    def get_as_item_custom(self, query, caption1=None, caption2=None):
        if caption1 or caption2:
            subtext = f"UP: {caption1} | DOWN: {caption2}"
        else:
            subtext = f"USAGE: {self.id} [upper-text] | [lower-text]"
        return StandardItem(
            id=f"{md_name}-{self.id}",
            icon_factory=lambda: Icon.image(str(self.img)),
            text=self.title(),
            subtext=subtext,
            input_action_text=f"{query.trigger} {self.id} ",
            actions=[
                Action(
                    "copy",
                    "Copy generated custom meme to clipboard",
                    lambda caption1=caption1, caption2=caption2: self._create_n_copy_to_clipboard(
                        caption1=caption1, caption2=caption2
                    ),
                ),
                Action(
                    "copy",
                    "Copy generated custom meme path",
                    lambda caption1=caption1, caption2=caption2: str(
                        self._create_n_copy_path_to_clipboard(
                            caption1=caption1, caption2=caption2
                        )
                    ),
                ),
            ],
        )

    def copy_vanilla_img(self):
        fname_out = "/tmp/meme.png"
        subprocess.check_call(["convert", "-format", "png", str(self.img), fname_out])
        subprocess.check_call(
            ["xclip", "-selection", "clipboard", "-t", "image/png", fname_out]
        )


_templates_cache: List["Template"] = []


def get_all_templates() -> List["Template"]:
    """Return all the supported templates, loading them on first use."""
    global _templates_cache
    if not _templates_cache:
        _templates_cache = [Template(id=id) for id in import_template_ids()]
    return _templates_cache


# supplementary functions ---------------------------------------------------------------------
def notify(
    msg: str,
    app_name: str = md_name,
    image=str(ICON_PATH),
):
    Notify.init(app_name)
    n = Notify.Notification.new(app_name, msg, image)
    n.show()


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

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "meme "

    def synopsis(self, query):
        return "some meme"

    def save_data(self, data: str, data_name: str):
        """Save a piece of data in the configuration directory."""
        with open(self.config_path / data_name, "w") as f:
            f.write(data)

    def load_data(self, data_name) -> str:
        """Load a piece of data from the configuration directory."""
        with open(self.config_path / data_name, "r") as f:
            return f.readline().strip().split()[0]

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        """Yield the memes matching the current query."""
        results = []

        try:
            all_templates = get_all_templates()
            query_str = ctx.query
            query_parts = query_str.split()

            if not query_parts:
                yield [template.get_as_item(ctx) for template in all_templates]
                return

            id_to_template = {template.id: template for template in all_templates}
            meme_id = query_parts[0]
            if meme_id in id_to_template:
                captions = [c.strip() for c in " ".join(query_parts[1:]).split("|")]
                c1 = captions[0]
                c2 = captions[1] if len(captions) > 1 else ""
                results.insert(
                    0,
                    id_to_template[meme_id].get_as_item_custom(
                        ctx, caption1=c1, caption2=c2
                    ),
                )
            else:
                title_to_templ = {template.title(): template for template in all_templates}
                # do fuzzy search - show relevant issues
                matched = process.extract(
                    query_str.strip(), list(title_to_templ.keys()), limit=5
                )
                for m in [elem[0] for elem in matched]:
                    results.append(title_to_templ[m].get_as_item(ctx))

        except Exception:  # user to report error
            trace = traceback.format_exc()
            critical(trace)
            results.insert(
                0,
                StandardItem(
                    id="meme-error",
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
