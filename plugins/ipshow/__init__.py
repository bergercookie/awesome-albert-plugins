"""IPs of the host machine."""

from typing import Dict
import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
import netifaces
from urllib import request

from fuzzywuzzy import process

import albert as v0

__title__ = "IPs of the host machine"
__version__ = "0.4.0"
__triggers__ = "ip "
__authors__ = "Nikos Koukis"
__homepage__ = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins//ipshow"

icon_path = str(Path(__file__).parent / "ipshow")

cache_path = Path(v0.cacheLocation()) / "ipshow"
config_path = Path(v0.configLocation()) / "ipshow"
data_path = Path(v0.dataLocation()) / "ipshow"

show_ipv4_only = True
families = netifaces.address_families
dev_mode = False

# plugin main functions -----------------------------------------------------------------------


def initialize():
    # Called when the extension is loaded (ticked in the settings) - blocking

    # create plugin locations
    for p in (cache_path, config_path, data_path):
        p.mkdir(parents=False, exist_ok=True)


def finalize():
    pass


def handleQuery(query) -> list:
    results = []

    if query.isTriggered:
        try:
            query.disableSort()

            results_setup = setup(query)
            if results_setup:
                return results_setup

            # External IP address -------------------------------------------------------------
            with request.urlopen("https://ipecho.net/plain") as response:
                external_ip = response.read().decode()

            results.append(
                get_as_item(
                    text=external_ip,
                    subtext="External IP Address",
                    actions=[
                        v0.ClipAction("Copy address", external_ip),
                    ],
                )
            )
            # IP address in all interfaces - by default IPv4 ----------------------------------
            ifaces = netifaces.interfaces()

            for iface in ifaces:  # Each interface
                addrs = netifaces.ifaddresses(iface)
                for family_to_addrs in addrs.items():
                    family = families[family_to_addrs[0]]

                    # discard all but IPv4?
                    if show_ipv4_only and family != "AF_INET":
                        continue

                    for i, addr_dict in enumerate(family_to_addrs[1]):
                        own_addr = addr_dict["addr"]
                        broadcast = addr_dict.get("broadcast")
                        netmask = addr_dict.get("netmask")
                        results.append(
                            get_as_item(
                                text=own_addr,
                                subtext=iface.ljust(15) + f" | {family} | Broadcast: {broadcast} | Netmask: {netmask}",
                                actions=[
                                    v0.ClipAction("Copy address", own_addr),
                                    v0.ClipAction("Copy interface", iface),
                                ],
                            )
                        )

            # Gateways ------------------------------------------------------------------------
            # Default gateway
            def_gws: Dict[int, tuple] = netifaces.gateways()["default"]

            for def_gw in def_gws.items():
                family_int = def_gw[0]
                addr = def_gw[1][0]
                iface = def_gw[1][1]
                results.append(
                    get_as_item(
                        text=f"[GW - {iface}] {addr}",
                        subtext=families[family_int],
                        actions=[
                            v0.ClipAction("Copy address", addr),
                            v0.ClipAction("Copy interface", iface),
                        ],
                    )
                )

        except Exception:  # user to report error
            if dev_mode:  # let exceptions fly!
                print(traceback.format_exc())
                raise

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


def get_as_item(text, subtext, completion="", actions=[]):
    return v0.Item(
        id=__title__,
        icon=icon_path,
        text=text,
        subtext=subtext,
        completion=completion,
        actions=actions,
    )


def get_as_subtext_field(field, field_title=None) -> str:
    """Get a certain variable as part of the subtext, along with a title for that variable.

    """
    s = ""
    if field:
        s = f"{field} | "
    else:
        return ""

    if field_title:
        s = f"{field_title} :" + s

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


def setup(query):
    """setup is successful if an empty list is returned.

    Use this function if you need the user to provide you data
    """

    results = []
    return results
