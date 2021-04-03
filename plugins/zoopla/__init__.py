""" Zoopla - Search Property to Buy, Rent, House Prices """

import os
import traceback
from pathlib import Path

import zoopla as z

import albert as v0

__title__ = "Zoopla - Search Properties"
__version__ = "0.4.0"
__triggers__ = "z "
__authors__ = "Nikos Koukis"
__homepage__ = "https://github.com/bergercookie/zoopla-albert-plugin"

iconPath = v0.iconLookup("zoopla")
if not iconPath:
    iconPath = os.path.join(os.path.dirname(__file__), "zoopla")
settings_path = Path(v0.cacheLocation()) / "zoopla"

api_key = "sn2dtcnvekktbjbv8ays8e33"
zoopla = z.Zoopla(api_key=api_key)

str_to_key = {"sale": "listing_status", "rent": "listing_status"}

str_to_actual_name = {"sale": "sale", "rent": "rent"}


def initialize():
    # Called when the extension is loaded (ticked in the settings) - blocking

    # create cache location
    settings_path.mkdir(parents=False, exist_ok=True)


def finalize():
    pass


def format_query(query):
    tokens = query.string.strip().split()
    options = []
    for i, t in enumerate(tokens):
        if t.startswith("--"):
            options.append(tokens.pop(i)[2:])

    print("tokens: ", tokens)
    query_dict = {"postcode": " ".join(tokens)}
    for opt in options:
        query_dict.update({str_to_key[opt]: str_to_actual_name[opt]})

    return query_dict


def handleQuery(query):
    results = []

    if query.isTriggered:
        try:
            if len(query.string) >= 3:
                query_dict = format_query(query)
                search = zoopla.property_listings(query_dict)

                for s in search["listing"]:
                    results.append(get_as_item(s))

        except Exception:  # user to report error
            results.insert(
                0,
                v0.Item(
                    id=__title__,
                    icon=iconPath,
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


def get_as_item(s):
    actions = []
    if s.details_url:
        actions.append(v0.UrlAction("Open on Zoopla", s.details_url))
    if s.floor_plan:
        actions.append(v0.UrlAction("Floorplan", s.floor_plan[0]))
    if s.price:
        actions.append(v0.ClipAction("Copy price", str(s.price)))

    if s.price:
        if s.listing_status == "rent":
            price_str = f"Weekly: £{s.price} | "
        else:
            price_str = f"Total: £{s.price} | "
    else:
        price_str = ""

    return v0.Item(
        id=__title__,
        icon=iconPath,
        text=f"{s.description}",
        subtext="{}{}{}".format(
            f"Type: {s.property_type} | " if s.property_type else "",
            f"Code: {s.outcode} | " if s.outcode else "",
            price_str,
            f"# Bedrooms: {s.num_bedrooms} | " if s.num_bedrooms else "",
        )[:-2],
        actions=actions,
    )
