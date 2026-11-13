"""Timezones lookup."""

import concurrent.futures

# TODO Remove this
import pprint
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Iterator, List

import pycountry
import pytz
import requests
import tzlocal
from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    PluginInstance,
    StandardItem,
    openUrl,
    setClipboardText,
)
from PIL import Image
from thefuzz import process

md_iid = "5.0"
md_version = "0.3"
md_name = "Timezones"
md_description = "Timezones lookup based on city/country"
md_url = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/timezones"
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["Pillow", "pycountry", "pytz", "requests", "thefuzz", "tzlocal"]


# country code -> cities
code_to_cities = dict({k: v for k, v in pytz.country_timezones.items()})
codes = list(code_to_cities.keys())
city_to_code = {vi: k for k, v in pytz.country_timezones.items() for vi in v}
cities = list(city_to_code.keys())
country_to_code = {c.name: c.alpha_2 for c in pycountry.countries if c.alpha_2 in codes}
country_to_cities = {
    country: code_to_cities[code] for country, code in country_to_code.items()
}
countries = list(country_to_code.keys())

# US states -> timezone mapping
us_states_to_tz = {
    "Alabama": "America/Chicago",
    "Alaska": "America/Anchorage",
    "Arizona": "America/Phoenix",
    "Arkansas": "America/Chicago",
    "California": "America/Los_Angeles",
    "Colorado": "America/Denver",
    "Connecticut": "America/New_York",
    "Delaware": "America/New_York",
    "Florida": "America/New_York",
    "Georgia": "America/New_York",
    "Hawaii": "Pacific/Honolulu",
    "Idaho": "America/Boise",
    "Illinois": "America/Chicago",
    "Indiana": "America/Indianapolis",
    "Iowa": "America/Chicago",
    "Kansas": "America/Chicago",
    "Kentucky": "America/New_York",
    "Louisiana": "America/Chicago",
    "Maine": "America/New_York",
    "Maryland": "America/New_York",
    "Massachusetts": "America/New_York",
    "Michigan": "America/Detroit",
    "Minnesota": "America/Chicago",
    "Mississippi": "America/Chicago",
    "Missouri": "America/Chicago",
    "Montana": "America/Denver",
    "Nebraska": "America/Chicago",
    "Nevada": "America/Los_Angeles",
    "New Hampshire": "America/New_York",
    "New Jersey": "America/New_York",
    "New Mexico": "America/Phoenix",
    "New York": "America/New_York",
    "North Carolina": "America/New_York",
    "North Dakota": "America/Chicago",
    "Ohio": "America/New_York",
    "Oklahoma": "America/Chicago",
    "Oregon": "America/Los_Angeles",
    "Pennsylvania": "America/New_York",
    "Rhode Island": "America/New_York",
    "South Carolina": "America/New_York",
    "South Dakota": "America/Chicago",
    "Tennessee": "America/Chicago",
    "Texas": "America/Chicago",
    "Utah": "America/Denver",
    "Vermont": "America/New_York",
    "Virginia": "America/New_York",
    "Washington": "America/Los_Angeles",
    "West Virginia": "America/New_York",
    "Wisconsin": "America/Chicago",
    "Wyoming": "America/Denver",
}


def get_local_tz_name() -> str:
    """IANA name of the local timezone, or "" if it can't be determined.

    tzlocal < 3 hands back a pytz tzinfo, which exposes ``zone``; >= 3 returns a
    zoneinfo.ZoneInfo, which exposes ``key`` and has no ``zone`` at all. ``str()``
    yields the same IANA name for both, so prefer the explicit attributes and
    fall back to it.
    """
    try:
        zone = tzlocal.get_localzone()
    except Exception:  # tzlocal raises when it cannot resolve the local zone
        traceback.print_exc()
        return ""

    return str(getattr(zone, "zone", None) or getattr(zone, "key", None) or zone)


local_tz_str = get_local_tz_name()


def get_pretty_city_name(city: str) -> str:
    return "".join(city.split("/")[-1].split("_"))


full_name_to_city = {
    f"{city_to_code[city]}{country.replace(' ', '')}{get_pretty_city_name(city)}": city
    for country in countries
    for city in country_to_cities[country]
}

# timezone abbreviation -> IANA timezone name mapping
TZ_ABBREV_TO_IANA = {
    "UTC": "Etc/UTC",
    "GMT": "Etc/GMT",
    "CST": "America/Chicago",
    "CDT": "America/Chicago",
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "MST": "America/Denver",
    "MDT": "America/Denver",
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
    "JST": "Asia/Tokyo",
    "ET": "America/New_York",
    "CT": "America/Chicago",
    "PT": "America/Los_Angeles",
    "MT": "America/Denver",
}


def download_logo_for_code(code: str) -> bytes:
    """
    Download the logo of the given code.

    .. raises:: KeyError if given code is invalid.
    """
    ret = requests.get(f"https://flagcdn.com/64x48/{code.lower()}.png")
    if not ret.ok:
        print(f"[E] Couldn't download logo for code {code}")
    return ret.content


# plugin main functions -----------------------------------------------------------------------


def get_uniq_elements(seq):
    """Return only the unique elements off the list - Preserve the order.

    .. ref:: https://stackoverflow.com/questions/480214/how-do-you-remove-duplicates-from-a-list-whilst-preserving-order
    """
    seen = set()
    seen_add = seen.add
    return [x for x in seq if not (x in seen or seen_add(x))]


# supplementary functions ---------------------------------------------------------------------


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
        self.country_logos_path = self.data_path / "logos"

        # create plugin locations
        for p in (self.cache_path, self.config_path, self.data_path):
            p.mkdir(parents=True, exist_ok=True)

        # the country logos are fetched on demand - see fetch_logos()
        self.logos_fetched = False

    @staticmethod
    def makeIcon():
        # this plugin ships no icon of its own - the per-item icons are the country flags
        return Icon.standard(Icon.StandardIconType.World)

    def defaultTrigger(self):
        return "tz "

    def synopsis(self, query):
        return "city/country name"

    def get_logo_path_for_code_orig(self, code: str) -> Path:
        """Return the path to the cached country logo"""
        return self.country_logos_path / f"{code}-orig.png"

    def get_logo_path_for_code(self, code: str) -> Path:
        """Return the path to the cached country logo"""
        return self.country_logos_path / f"{code}.png"

    def save_logo_for_code(self, code: str, data: bytes):
        fname_orig = self.get_logo_path_for_code_orig(code)
        fname = self.get_logo_path_for_code(code)

        with open(fname_orig, "wb") as f:
            f.write(data)

        old_img = Image.open(fname_orig)
        old_size = old_img.size
        new_size = (80, 80)
        new_img = Image.new("RGBA", new_size)
        new_img.paste((255, 255, 255, 0), (0, 0, *new_size))
        new_img.paste(
            old_img, ((new_size[0] - old_size[0]) // 2, (new_size[1] - old_size[1]) // 2)
        )

        new_img.save(fname)

    def download_and_save_logo_for_code(self, code):
        self.save_logo_for_code(code, download_logo_for_code(code))

    def download_all_logos(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
            future_to_code = {
                executor.submit(self.download_and_save_logo_for_code, code): code
                for code in codes
            }
            for future in concurrent.futures.as_completed(future_to_code):
                code = future_to_code[future]
                try:
                    future.result()
                    print(f"Fetched logo for country {code}")
                except Exception as exc:
                    print(f"[W] Fetching logo for {code} generated an exception: {exc}")

    def fetch_logos(self):
        """Fetch all the country logos - only once, and only when the plugin is actually used."""
        if self.logos_fetched:
            return

        self.logos_fetched = True

        self.country_logos_path.mkdir(exist_ok=True)
        if not list(self.country_logos_path.iterdir()):
            print("Downloading country logos")
            t = time.time()
            self.download_all_logos()
            print(f"Downloaded country logos - Took {time.time() - t} seconds")

    def get_as_item(self, city: str) -> StandardItem:
        """Return an item - ready to be appended to the items list and be rendered by Albert."""
        code = city_to_code[city]

        utc_dt = pytz.utc.localize(datetime.utcnow())
        dst_tz = pytz.timezone(city)
        dst_dt = utc_dt.astimezone(dst_tz)

        text = f'{dst_dt.strftime("%Y-%m-%d %H:%M %z (%Z)")}'
        subtext = f"[{code}] | {city}"
        url = f"https://www.zeitverschiebung.net/en/timezone/{city.replace('/', '--').lower()}"

        def icon_factory():
            if code == "US":
                return Icon.image(self.get_logo_path_for_code("US"))
            return Icon.image(self.get_logo_path_for_code(code))

        return StandardItem(
            id=f"timezones-{city}",
            icon_factory=icon_factory,
            text=text,
            subtext=subtext,
            input_action_text=city,
            actions=[
                Action("open", "Open in zeitverschiebung.net", lambda u=url: openUrl(u)),
            ],
        )

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
        results = []

        try:
            self.fetch_logos()

            query_str = ctx.query.strip().lower()

            # search for cities in both keys and values
            matched = []

            # Search in full_name_to_city keys (format: "USTexasAustin")
            matched.extend([
                elem for elem in process.extract(query_str, full_name_to_city.keys(), limit=8)
            ])

            # Search in full_name_to_city values (city names like "Austin")
            matched.extend([
                elem for elem in process.extract(query_str, full_name_to_city.values(), limit=8)
            ])

            print(matched)

            # Get unique cities from keys
            unique_cities_from_keys = get_uniq_elements(
                [full_name_to_city[m[0]] for m in matched if m[0] in full_name_to_city]
            )

            # Get unique cities from values
            unique_cities_from_values = get_uniq_elements(
                [m[0] for m in matched if m[0] in full_name_to_city.values()]
            )

            # Combine both lists
            unique_cities_matched = get_uniq_elements(unique_cities_from_keys + unique_cities_from_values)

            # add own timezone:
            if local_tz_str in unique_cities_matched:
                unique_cities_matched.remove(local_tz_str)
                unique_cities_matched.insert(0, local_tz_str)
            results.extend([self.get_as_item(m) for m in unique_cities_matched])

            # search for US states
            matched_states = [
                elem for elem in process.extract(query_str, list(us_states_to_tz.keys()), limit=8)
            ]
            unique_states_matched = get_uniq_elements([m[0] for m in matched_states])

            # create items for US states
            for state in unique_states_matched:
                iana_tz = us_states_to_tz[state]
                utc_dt = pytz.utc.localize(datetime.utcnow())
                dst_tz = pytz.timezone(iana_tz)
                dst_dt = utc_dt.astimezone(dst_tz)

                text = f'{dst_dt.strftime("%Y-%m-%d %H:%M %z (%Z)")}'
                subtext = f"[{iana_tz}] | {state} (State)"

                results.append(
                    StandardItem(
                        id=f"timezones-state-{iana_tz}",
                        icon_factory=self.makeIcon,
                        text=text,
                        subtext=subtext,
                        input_action_text=iana_tz,
                        actions=[
                            Action("open", "Open timezone info", lambda u=iana_tz: openUrl(f"https://en.wikipedia.org/wiki/{u}")),
                        ],
                    )
                )

            # prioritize exact matches at the top
            if query_str in us_states_to_tz:
                state = query_str
                iana_tz = us_states_to_tz[state]
                utc_dt = pytz.utc.localize(datetime.utcnow())
                dst_tz = pytz.timezone(iana_tz)
                dst_dt = utc_dt.astimezone(dst_tz)

                text = f'{dst_dt.strftime("%Y-%m-%d %H:%M %z (%Z)")}'
                subtext = f"[{iana_tz}] | {state} (State)"

                # Insert at the beginning if not already present
                exact_match_item = StandardItem(
                    id=f"timezones-state-exact-{iana_tz}",
                    icon_factory=self.makeIcon,
                    text=text,
                    subtext=subtext,
                    input_action_text=iana_tz,
                    actions=[
                        Action("open", "Open timezone info", lambda u=iana_tz: openUrl(f"https://en.wikipedia.org/wiki/{u}")),
                    ],
                )

                # Check if we already have this exact match
                if not any(item.id == f"timezones-state-exact-{iana_tz}" for item in results):
                    results.insert(0, exact_match_item)

            if query_str in full_name_to_city.values():
                city = query_str
                exact_match_item = self.get_as_item(city)
                exact_match_item.id = f"timezones-city-exact-{city}"

                # Check if we already have this exact match
                if not any(item.id == f"timezones-city-exact-{city}" for item in results):
                    results.insert(0, exact_match_item)

        except Exception:  # user to report error
            trace = traceback.format_exc()
            print(trace)

            results.insert(
                0,
                StandardItem(
                    id="timezones-error",
                    icon_factory=self.makeIcon,
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        Action(
                            "copy",
                            f"Copy error - report it to {md_url[8:]}",
                            lambda t=trace: setClipboardText(t),
                        )
                    ],
                ),
            )

        yield results
