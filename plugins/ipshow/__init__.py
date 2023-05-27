"""IPs of the host machine."""

from typing import Dict
import traceback
from pathlib import Path
import netifaces
from urllib import request
from fuzzywuzzy import process

from albert import *

md_iid = "0.5"
md_version = "0.2"
md_name = "IPs of the host machine"
md_description = "Shows machine IPs"
md_license = "BSD-2"
md_url = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins//ipshow"
md_maintainers = "Nikos Koukis"
md_lib_dependencies = ["fuzzywuzzy"]

icon_path = str(Path(__file__).parent / "ipshow")

cache_path = Path(cacheLocation()) / "ipshow"
config_path = Path(configLocation()) / "ipshow"
data_path = Path(dataLocation()) / "ipshow"


# flags to tweak ------------------------------------------------------------------------------
show_ipv4_only = True
discard_bridge_ifaces = True

families = netifaces.address_families


def filter_actions_by_query(items, query, score_cutoff=20):
    sorted_results_text = process.extractBests(
        query, [x.text for x in items], score_cutoff=score_cutoff
    )
    sorted_results_subtext = process.extractBests(
        query, [x.subtext for x in items], score_cutoff=score_cutoff
    )

    results_arr = [(x, score_cutoff) for x in items]
    for text_res, score in sorted_results_text:
        for i in range(len(items)):
            if items[i].text == text_res and results_arr[i][1] < score:
                results_arr[i] = (items[i], score)

    for subtext_res, score in sorted_results_subtext:
        for i in range(len(items)):
            if items[i].subtext == subtext_res and results_arr[i][1] < score:
                results_arr[i] = (items[i], score)

    return [x[0] for x in results_arr if x[1] > score_cutoff or len(query.strip()) == 0]


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
        return "ip "

    def handleQuery(self, query):
        results = []

        if not query.isValid:
            return

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
            print(traceback.format_exc())

            results.insert(
                0,
                Item(
                    id=self.name,
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
        query.add(filter_actions_by_query(results, query.string, 20))

    def get_as_item(self, text, subtext, actions=[]):
        return Item(
            id=self.name(),
            icon=[icon_path],
            text=text,
            subtext=subtext,
            completion=self.defaultTrigger() + text,
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
