"""Lookup and Start Remmina Connections."""

import configparser
import os
import subprocess
from glob import glob
from pathlib import Path
from re import IGNORECASE, search
from typing import Iterator, List, Sequence, Tuple

from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    PluginInstance,
    StandardItem,
)

md_iid = "5.0"
md_version = "0.3"
md_name = "Remmina"
md_description = "Start a Remmina VNC/SFTP connection"
md_license = "MIT"
md_url = "https://github.com/bergercookie/awesome-albert-plugins"
md_maintainers = ["Oğuzcan Küçükbayrak", "Nikos Koukis"]
md_bin_dependencies = ["remmina"]


def runRemmina(cf: str = "") -> None:
    args = (["remmina"], ["remmina", "-c", cf])[len(cf) > 0]
    subprocess.Popen(args)


def getConnectionProperties(f: str) -> Tuple[str, str, str, str, str]:
    assert os.path.isfile(f), f"No such file -> {f}"

    conf = configparser.ConfigParser()
    conf.read(f)

    name = conf["remmina"]["name"]
    group = conf["remmina"]["group"]
    server = conf["remmina"]["server"]
    proto = conf["remmina"]["protocol"]

    return name, group, server, proto, f


class Plugin(PluginInstance, GeneratorQueryHandler):

    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)

        self.module_path = Path(__file__).absolute().parent
        self.icon_path = self.module_path / "icons" / "remmina.svg"
        self.connections_path = (
            Path(os.environ["HOME"]) / ".local" / "share" / "remmina"
        )

    def get_protocol_icon_path(self, proto: str) -> Path:
        path = self.module_path / "icons" / f"remmina-{proto.lower()}-symbolic.svg"
        if path.is_file():
            return path
        else:
            return self.icon_path

    def getConfigFiles(self) -> Sequence[str]:
        return [
            f for f in glob(str(self.connections_path) + "**/*.remmina", recursive=True)
        ]

    def getAsItem(self, name, group, server, proto, file) -> StandardItem:
        icon = self.get_protocol_icon_path(proto)
        return StandardItem(
            id=f"remmina-{file}",
            icon_factory=lambda: Icon.image(icon),
            text=(name, "%s/ %s" % (group, name))[len(group) > 0],
            subtext="%s %s" % (proto, server),
            actions=[Action("open", "Open connection", lambda cf=file: runRemmina(cf))],
        )

    def defaultTrigger(self):
        return "rem"

    def synopsis(self, query):
        return "<connection name>"

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        files = self.getConfigFiles()
        all_connections = [getConnectionProperties(f) for f in files]
        stripped = ctx.query.strip()
        results = []
        if stripped:  # specific query by the user
            for p in all_connections:
                # search in names and groups
                if search(stripped, p[0], IGNORECASE) or search(
                    stripped, p[1], IGNORECASE
                ):
                    results.append(self.getAsItem(*p))

        else:  # nothing specified yet, show all possible connections
            for p in all_connections:
                results.append(self.getAsItem(*p))

        # add it at the very end - fallback choice in case none of the connections is what the
        # user wants
        results.append(
            StandardItem(
                id="remmina-launch",
                icon_factory=lambda: Icon.image(self.icon_path),
                text=md_name,
                subtext=__doc__,
                actions=[Action("open", "Open Remmina", runRemmina)],
            )
        )

        yield results
