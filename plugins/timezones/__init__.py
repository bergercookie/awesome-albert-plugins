"""Timezones lookup."""

import concurrent.futures

# TODO Remove this
import pprint
import time
import traceback
from datetime import datetime
from pathlib import Path

import albert as v0  # type: ignore
import pycountry
import pytz
import requests
import tzlocal
from thefuzz import process
from PIL import Image

md_name = "Timezones"
md_description = "Timezones lookup based on city/country"
md_iid = "0.5"
md_version = "0.2"
md_maintainers = "Nikos Koukis"
md_url = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/timezones"
md_lib_dependencies = [
    "Pillow",
    "pycountry",
    "thefuzz[speedup]",
    "tzlocal==2.1",
    "requests",
    "pytz",
]


icon_path = str(Path(__file__).parent / "timezones")

cache_path = Path(v0.cacheLocation()) / "timezones"
config_path = Path(v0.configLocation()) / "timezones"
data_path = Path(v0.dataLocation()) / "timezones"
country_logos_path = data_path / "logos"

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
local_tz_str = tzlocal.get_localzone().zone


def get_pretty_city_name(city: str) -> str:
    return "".join(city.split("/")[-1].split("_"))


full_name_to_city = {
    f"{city_to_code[city]}{country.replace(' ', '')}{get_pretty_city_name(city)}": city
    for country in countries
    for city in country_to_cities[country]
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


def get_logo_path_for_code_orig(code: str) -> Path:
    """Return the path to the cached country logo"""
    return country_logos_path / f"{code}-orig.png"


def get_logo_path_for_code(code: str) -> Path:
    """Return the path to the cached country logo"""
    return country_logos_path / f"{code}.png"


def save_logo_for_code(code: str, data: bytes):
    fname_orig = get_logo_path_for_code_orig(code)
    fname = get_logo_path_for_code(code)

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


def download_and_save_logo_for_code(code):
    save_logo_for_code(code, download_logo_for_code(code))


def download_all_logos():
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        future_to_code = {
            executor.submit(download_and_save_logo_for_code, code): code for code in codes
        }
        for future in concurrent.futures.as_completed(future_to_code):
            code = future_to_code[future]
            try:
                future.result()
                print(f"Fetched logo for country {code}")
            except Exception as exc:
                print(f"[W] Fetching logo for {code} generated an exception: {exc}")


# plugin main functions -----------------------------------------------------------------------


def get_uniq_elements(seq):
    """Return only the unique elements off the list - Preserve the order.

    .. ref:: https://stackoverflow.com/questions/480214/how-do-you-remove-duplicates-from-a-list-whilst-preserving-order
    """
    seen = set()
    seen_add = seen.add
    return [x for x in seq if not (x in seen or seen_add(x))]


# supplementary functions ---------------------------------------------------------------------


def get_as_item(city: str):
    """Return an item - ready to be appended to the items list and be rendered by Albert."""
    code = city_to_code[city]

    icon = str(get_logo_path_for_code(code))
    utc_dt = pytz.utc.localize(datetime.utcnow())
    dst_tz = pytz.timezone(city)
    dst_dt = utc_dt.astimezone(dst_tz)

    text = f'{dst_dt.strftime("%Y-%m-%d %H:%M %z (%Z)")}'
    subtext = f"[{code}] | {city}"

    return v0.Item(
        id=f"{md_name}_{code}",
        icon=[icon],
        text=text,
        subtext=subtext,
        completion=city,
        actions=[
            UrlAction(
                "Open in zeitverschiebung.net",
                (
                    f'https://www.zeitverschiebung.net/en/timezone/{city.replace("/", "--").lower()}'
                ),
            ),
        ],
    )


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


def save_data(data: str, data_name: str):
    """Save a piece of data in the configuration directory."""
    with open(config_path / data_name, "w") as f:
        f.write(data)


def load_data(data_name) -> str:
    """Load a piece of data from the configuration directory."""
    with open(config_path / data_name, "r") as f:
        data = f.readline().strip().split()[0]

    return data


# helpers for backwards compatibility ------------------------------------------
class UrlAction(v0.Action):
    def __init__(self, name: str, url: str):
        super().__init__(name, name, lambda: v0.openUrl(url))


class ClipAction(v0.Action):
    def __init__(self, name, copy_text):
        super().__init__(name, name, lambda: v0.setClipboardText(copy_text))


class FuncAction(v0.Action):
    def __init__(self, name, command):
        super().__init__(name, name, command)


# main plugin class ------------------------------------------------------------
class Plugin(v0.QueryHandler):
    def id(self) -> str:
        return __name__

    def name(self) -> str:
        return md_name

    def description(self):
        return md_description

    def defaultTrigger(self):
        return "tz "

    def synopsis(self):
        return "city/country name"

    def initialize(self):
        """Called when the extension is loaded (ticked in the settings) - blocking."""

        # create plugin locations
        for p in (cache_path, config_path, data_path):
            p.mkdir(parents=False, exist_ok=True)

        # fetch all logos at startup
        country_logos_path.mkdir(exist_ok=True)
        if not list(country_logos_path.iterdir()):
            print("Downloading country logos")
            t = time.time()
            download_all_logos()
            print(f"Downloaded country logos - Took {time.time() - t} seconds")

    def finalize(self):
        pass

    def handleQuery(self, query) -> None:
        """Hook that is called by albert with *every new keypress*."""  # noqa
        results = []

        try:
            query_str = query.string.strip()

            matched = [
                elem for elem in process.extract(query_str, full_name_to_city.keys(), limit=8)
            ]
            v0.debug(matched)

            unique_cities_matched = get_uniq_elements(
                [full_name_to_city[m[0]] for m in matched]
            )

            # add own timezone:
            if local_tz_str in unique_cities_matched:
                unique_cities_matched.remove(local_tz_str)
                unique_cities_matched.insert(0, local_tz_str)
            results.extend([get_as_item(m) for m in unique_cities_matched])

        except Exception:  # user to report error
            print(traceback.format_exc())

            results.insert(
                0,
                v0.Item(
                    id=md_name,
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

        query.add(results)
