# -*- coding: utf-8 -*-

"""Search and start Remmina connections."""

import configparser
import os
import subprocess
from glob import glob
from re import IGNORECASE, search
from typing import Tuple

from albert import FuncAction, Item, critical

__title__ = "Remmina"
__version__ = "0.4.0"
__triggers__ = "rem"
__authors__ = "Oğuzcan Küçükbayrak, Nikos Koukis"
__exec_deps__ = ["remmina"]
__py_deps__ = ["configparser"]

MODULE_PATH = os.path.dirname(__file__)
ICON_PATH = MODULE_PATH + "/icons/remmina.svg"
PROTOCOL_ICONS_PATH = MODULE_PATH + "/icons/remmina-%s-symbolic.svg"
CONNECTIONS_PATH = "%s/.local/share/remmina" % os.environ["HOME"]


def runRemmina(cf=""):
    args = (["remmina"], ["remmina", "-c", cf])[len(cf) > 0]
    subprocess.Popen(args)


def getConfigFiles():
    return [f for f in glob(CONNECTIONS_PATH + "**/*.remmina", recursive=True)]


def getAsItem(name, group, server, proto, file):
    return Item(
        id=__title__,
        icon=PROTOCOL_ICONS_PATH % (proto.lower()),
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
                icon=ICON_PATH,
                text=__title__,
                subtext=__doc__,
                actions=[FuncAction("Open Remmina", runRemmina)],
            )
        )

        return results
