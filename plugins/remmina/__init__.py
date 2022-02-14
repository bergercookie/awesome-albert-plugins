"""Lookup and Start Remmina Connections."""

import configparser
import os
import subprocess
from glob import glob
from pathlib import Path
from re import IGNORECASE, search
from typing import Tuple, Sequence

from albert import FuncAction, Item

__title__ = "Remmina"
__version__ = "0.4.0"
__triggers__ = "rem"
__authors__ = "Oğuzcan Küçükbayrak, Nikos Koukis"
__exec_deps__ = ["remmina"]
__py_deps__ = ["configparser"]

MODULE_PATH = Path(__file__).absolute().parent
ICON_PATH = MODULE_PATH / "icons" / "remmina.svg"
CONNECTIONS_PATH = Path(os.environ["HOME"]) / ".local" / "share" / "remmina"


def get_protocol_icon_path(proto: str) -> Path:
    path = MODULE_PATH / "icons" / f"remmina-{proto.lower()}-symbolic.svg"
    if path.is_file():
        return path
    else:
        return ICON_PATH


def runRemmina(cf: str = "") -> None:
    args = (["remmina"], ["remmina", "-c", cf])[len(cf) > 0]
    subprocess.Popen(args)


def getConfigFiles() -> Sequence[str]:
    return [f for f in glob(str(CONNECTIONS_PATH) + "**/*.remmina", recursive=True)]


def getAsItem(name, group, server, proto, file):
    return Item(
        id=__title__,
        icon=str(get_protocol_icon_path(proto)),
        text=(name, "%s/ %s" % (group, name))[len(group) > 0],
        subtext="%s %s" % (proto, server),
        actions=[FuncAction("Open connection", lambda cf=file: runRemmina(cf))],
    )


def getConnectionProperties(f: str) -> Tuple[str, str, str, str, str]:
    assert os.path.isfile(f), f"No such file -> {f}"

    conf = configparser.ConfigParser()
    conf.read(f)

    name = conf["remmina"]["name"]
    group = conf["remmina"]["group"]
    server = conf["remmina"]["server"]
    proto = conf["remmina"]["protocol"]

    return name, group, server, proto, f


def handleQuery(query):
    if query.isTriggered:
        query.disableSort()

        files = getConfigFiles()
        all_connections = [getConnectionProperties(f) for f in files]
        stripped = query.string.strip()
        results = []
        if stripped:  # specific query by the user
            for p in all_connections:
                # search in names and groups
                if search(stripped, p[0], IGNORECASE) or search(stripped, p[1], IGNORECASE):
                    results.append(getAsItem(*p))

        else:  # nothing specified yet, show all possible connections
            for p in all_connections:
                results.append(getAsItem(*p))

        # add it at the very end - fallback choice in case none of the connections is what the
        # user wants
        results.append(
            Item(
                id=__title__,
                icon=str(ICON_PATH),
                text=__title__,
                subtext=__doc__,
                actions=[FuncAction("Open Remmina", runRemmina)],
            )
        )

        return results
