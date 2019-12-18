# -*- coding: utf-8 -*-

"""Search and start Remmina connections."""

from shutil import which
from albertv0 import Item, FuncAction, critical
import os
import subprocess
from glob import glob
from re import search, IGNORECASE
import configparser

__iid__ = "PythonInterface/v0.2"
__prettyname__ = "Remmina"
__version__ = "0.2"
__trigger__ = "rem"
__author__ = "Oğuzcan Küçükbayrak"
__dependencies__ = ["remmina"]

if not which('remmina'):
    raise Exception("`remmina` is not in $PATH.");

MODULE_PATH = os.path.dirname(__file__)
ICON_PATH = MODULE_PATH + "/icons/remmina.svg"
PROTOCOL_ICONS_PATH = MODULE_PATH + "/icons/remmina-%s-symbolic.svg"
CONNECTIONS_PATH = "%s/.local/share/remmina" % os.environ['HOME']

def runRemmina(cf=""):
    args = (['remmina'], ['remmina', '-c', cf])[len(cf) > 0]
    subprocess.Popen(args)

def searchConfigFiles(query):
    results = []
    files = [f for f in glob(CONNECTIONS_PATH + "**/*.remmina", recursive=True)]
    for f in files:
        conf = configparser.ConfigParser()
        conf.read(f)

        name = conf['remmina']['name']
        group = conf['remmina']['group']
        server = conf['remmina']['server']
        proto = conf['remmina']['protocol']
        if (search(query, name, IGNORECASE)):
            results.append(
                Item(
                    id=__prettyname__,
                    icon=PROTOCOL_ICONS_PATH % (proto.lower()),
                    text=(name, "%s/ %s" % (group, name))[len(group) > 0],
                    subtext="%s %s" % (proto, server),
                    actions=[
                        FuncAction("Open connection",
                                   lambda cf=f: runRemmina(cf))
                    ]
                )
            )
    return results


def handleQuery(query):
    if query.isTriggered:
        stripped = query.string.strip()
        if stripped:
            results = searchConfigFiles(stripped)
            if results:
                return results

        return Item(
            id=__prettyname__,
            icon=ICON_PATH,
            text=__prettyname__,
            subtext=__doc__,
            actions=[FuncAction("Open Remmina", runRemmina)]
        )
