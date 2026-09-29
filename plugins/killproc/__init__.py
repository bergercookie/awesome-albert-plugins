"""Kill a process v2."""

import fnmatch
import re
import signal
import traceback
from pathlib import Path
from typing import Dict, Iterator, List

import psutil
from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    PluginInstance,
    StandardItem,
    setClipboardText,
)
from fuzzywuzzy import process
from gi.repository import GdkPixbuf, Notify
from psutil import Process

md_iid = "5.0"
md_version = "0.3"
md_name = "Kill Process v2"
md_description = "Terminate/Kill a process - find it using fuzzy expressions ..."
md_url = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/killproc"
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["fuzzywuzzy", "psutil"]

ICON_PATH = Path(__file__).parent / "logo.png"

# supplementary functions ---------------------------------------------------------------------


def notify(
    msg: str,
    app_name: str = md_name,
    image=str(ICON_PATH),
):
    Notify.init(app_name)
    n = Notify.Notification.new(app_name, msg, image)
    n.show()


def cmdline(p: Process) -> str:
    """There must be a bug in psutil and sometimes `cmdline()` raises an exception. I don't
    want that, so I'll override this behavior for now.
    """
    try:
        return " ".join(p.cmdline())
    except psutil.NoSuchProcess:
        return ""


def procs() -> List[Process]:
    """Get a list of all the processes."""
    return list(psutil.process_iter())


def globsearch_procs(s: str) -> List[Process]:
    """Return a list of processes whose command line matches the given glob."""
    pat = re.compile(fnmatch.translate(s))

    procs_ = procs()
    procs_out = list(filter(lambda p: re.search(pat, cmdline(p)) is not None, procs_))
    notify(msg=f"Glob search returned {len(procs_out)} matching processes")
    return procs_out


def get_cmdline_to_procs() -> Dict[str, List[Process]]:
    """Return a Dictionary of command-line args string to all the corresponding processes with
    that."""
    procs_ = procs()
    out = {cmdline(p): [] for p in procs_}
    for p in procs_:
        out[cmdline(p)].append(p)

    return out


def kill_by_name(name: str, signal=signal.SIGTERM):
    """Kill all the processes whose name matches the given one."""
    procs_ = procs()
    for p in filter(lambda p: p.name() == name, procs_):
        p.send_signal(signal)


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

        self.cache_path = Path(self.cacheLocation())
        self.config_path = Path(self.configLocation())
        self.data_path = Path(self.dataLocation())

        # create plugin locations
        for p in (self.cache_path, self.config_path, self.data_path):
            p.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "kill "

    def synopsis(self, query):
        return "process ID/name"

    def get_as_item(self, ctx, p: Process, *extra_actions) -> StandardItem:
        """Return an item - ready to be appended to the items list and be rendered by Albert.

        if Process is not a valid object (.name or .cmdline raise an exception) then return None
        """
        name_field = cmdline(p)

        if not name_field:
            return None

        try:
            actions = [
                Action("terminate", "Terminate", lambda p=p: p.terminate()),
                Action("kill", "Kill", lambda p=p: p.kill()),
                Action("copy", "Get PID", lambda t=f"{p.pid}": setClipboardText(t)),
                Action(
                    "terminate-matching",
                    "Terminate matching names",
                    lambda name=p.name(): kill_by_name(name, signal=signal.SIGTERM),
                ),
                Action(
                    "kill-matching",
                    "Kill matching names",
                    lambda name=p.name(): kill_by_name(name),
                ),
            ]
            actions = [*extra_actions, *actions]
            return StandardItem(
                id=f"killproc-{p.pid}",
                icon_factory=self.makeIcon,
                text=name_field,
                subtext="",
                input_action_text=f"{ctx.trigger}{p.name()}",
                actions=actions,
            )
        except psutil.NoSuchProcess:
            return None

    def save_data(self, data: str, data_name: str):
        """Save a piece of data in the configuration directory."""
        with open(self.config_path / data_name, "w") as f:
            f.write(data)

    def load_data(self, data_name) -> str:
        """Load a piece of data from the configuration directory."""
        with open(self.config_path / data_name, "r") as f:
            data = f.readline().strip().split()[0]

        return data

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        """Called by albert with *every new keypress*."""
        try:
            query_str = ctx.query.strip()

            cmdline_to_procs = get_cmdline_to_procs()
            matched = [
                elem[0]
                for elem in process.extract(query_str, cmdline_to_procs.keys(), limit=15)
            ]

            extra_actions = []
            if any([symbol in query_str for symbol in "*?[]"]):
                extra_actions = [
                    Action(
                        "terminate-glob",
                        "Terminate by glob",
                        lambda q=query_str: list(
                            map(lambda p: p.terminate(), globsearch_procs(q))
                        ),
                    ),
                    Action(
                        "kill-glob",
                        "Kill by glob",
                        lambda q=query_str: list(map(lambda p: p.kill(), globsearch_procs(q))),
                    ),
                ]

            yield [
                res
                for m in matched
                for p in cmdline_to_procs[m]
                if (res := self.get_as_item(ctx, p, *extra_actions)) is not None
            ]

        except Exception:  # user to report error
            trace = traceback.format_exc()
            print(trace)

            yield [
                StandardItem(
                    id="killproc-error",
                    icon_factory=self.makeIcon,
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        Action(
                            "copy",
                            f"Copy error - report it to {md_url[8:]}",
                            lambda t=trace: setClipboardText(t),
                        )
                    ],
                )
            ]
