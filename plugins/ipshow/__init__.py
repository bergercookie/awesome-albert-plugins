"""IPs of the host machine."""

from typing import Dict
import traceback
from pathlib import Path
import netifaces
from urllib import request

from albert import *

md_iid = "0.5"
md_version = "0.5"
#md_id = "overwrite"
md_name = "IPs of the host machine"
md_description = "Shows machine ips"
md_license = "BSD-2"
md_url = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins//ipshow"
md_maintainers = "Nikos Koukis"

icon_path = str(Path(__file__).parent / "ipshow")

cache_path = Path(cacheLocation()) / "ipshow"
config_path = Path(configLocation()) / "ipshow"
data_path = Path(dataLocation()) / "ipshow"


# flags to tweak ------------------------------------------------------------------------------
show_ipv4_only = True
discard_bridge_ifaces = True
dev_mode = True

families = netifaces.address_families

class ClipAction(Action):
    def __init__(self, name, copy_text):
        super().__init__(name, name, lambda: setClipboardText(copy_text))

class Plugin(QueryHandler):
    def id(self):
        return __name__

    def name(self):
        return md_name

    def description(self):
        return md_description

    def initialize(self):
        # Called when the extension is loaded (ticked in the settings) - blocking

        # create plugin locations
        for p in (cache_path, config_path, data_path):
            p.mkdir(parents=False, exist_ok=True)

    def finalize(self):
        pass

    def defaultTrigger(self):
        return 'ip'

    def handleQuery(self, query):
        results = []
        try:
            # External IP address -------------------------------------------------------------
            try:
                with request.urlopen("https://ipecho.net/plain", timeout=1.5) as response:
                    external_ip = response.read().decode()
            except:
                external_ip = "Timeout fetching public IP"

            results.append(
                self.get_as_item(
                    text=external_ip,
                    subtext="External IP Address",
                    actions=[
                        ClipAction("Copy address", external_ip),
                    ],
                )
            )
            # IP address in all interfaces - by default IPv4 ----------------------------------
            ifaces = netifaces.interfaces()

            # for each interface --------------------------------------------------------------
            for iface in ifaces:
                addrs = netifaces.ifaddresses(iface)
                for family_to_addrs in addrs.items():
                    family = families[family_to_addrs[0]]

                    # discard all but IPv4?
                    if show_ipv4_only and family != "AF_INET":
                        continue

                    # discard bridge interfaces?
                    if discard_bridge_ifaces and iface.startswith("br-"):
                        continue

                    # for all addresses in this interface -------------------------------------
                    for i, addr_dict in enumerate(family_to_addrs[1]):
                        own_addr = addr_dict["addr"]
                        broadcast = addr_dict.get("broadcast")
                        netmask = addr_dict.get("netmask")
                        results.append(
                            self.get_as_item(
                                text=own_addr,
                                subtext=iface.ljust(15)
                                + f" | {family} | Broadcast: {broadcast} | Netmask: {netmask}",
                                actions=[
                                    ClipAction("Copy address", own_addr),
                                    ClipAction("Copy interface", iface),
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
                    self.get_as_item(
                        text=f"[GW - {iface}] {addr}",
                        subtext=families[family_int],
                        actions=[
                            ClipAction("Copy address", addr),
                            ClipAction("Copy interface", iface),
                        ],
                    )
                )

        except Exception:  # user to report error
            if dev_mode:  # let exceptions fly!
                print(traceback.format_exc())
                raise

            results.insert(
                0,
                Item(
                    id=self.name,
                    icon=icon_path,
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        ClipAction(
                            f"Copy error - report it to {md_url[8:]}",
                            f"{traceback.format_exc()}",
                        )
                    ],
                ),
            )

        query.add(results)
        return results

    def get_as_item(self, text, subtext, completion="", actions=[]):
        return Item(
            id=self.name(),
            icon=[icon_path],
            text=text,
            subtext=subtext,
            completion=completion,
            actions=actions,
        )


# supplementary functions ---------------------------------------------------------------------


def get_as_subtext_field(field, field_title=None) -> str:
    """Get a certain variable as part of the subtext, along with a title for that variable."""
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

