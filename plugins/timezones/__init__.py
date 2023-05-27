"""Timezones lookup."""

import concurrent.futures
import time
import traceback
from datetime import datetime
from pathlib import Path

import albert as v0  # type: ignore
import pycountry
import pytz
import requests
import tzlocal
from fuzzywuzzy import process
from PIL import Image, ImageOps

__title__ = "Timezones lookup"
__version__ = "0.4.0"
__triggers__ = "tz "
__authors__ = "Nikos Koukis"
__homepage__ = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/timezones"
)
__py_deps__ = ["Pillow", "pycountry", "fuzzywuzzy", "tzlocal", "requests", "traceback", "pytz"]


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
    country: [code_to_cities[code]] for country, code in country_to_code.items()
}
countries = list(country_to_code.keys())

local_tz_str = tzlocal.get_localzone().zone


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


def initialize():
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


def finalize():
    pass


def get_uniq_elements(seq):
    """Return only the unique elements off the list - Preserve the order.

    .. ref:: https://stackoverflow.com/questions/480214/how-do-you-remove-duplicates-from-a-list-whilst-preserving-order
    """
    seen = set()
    seen_add = seen.add
    return [x for x in seq if not (x in seen or seen_add(x))]


def handleQuery(query) -> list:
    """Hook that is called by albert with *every new keypress*."""  # noqa
    results = []

    if query.isTriggered:
        try:
            query.disableSort()

            results_setup = setup(query)
            if results_setup:
                return results_setup

            query_str = query.string.strip()

            matched = [
                elem[0] for elem in process.extract(query_str, [*cities, *countries], limit=8)
            ]

            matched2 = []
            # replace country names with its cities
            for m in matched:
                if m in countries:
                    matched2.extend(*country_to_cities[m])
                else:
                    matched2.append(m)
            matched2 = get_uniq_elements(matched2)

            # add own timezone:
            if local_tz_str in matched2:
                matched2.remove(local_tz_str)

            matched2.insert(0, local_tz_str)
            results.extend([get_as_item(m) for m in matched2])

        except Exception:  # user to report error
            print(traceback.format_exc())

            query.add(
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
        id=__title__,
        icon=icon,
        text=text,
        subtext=subtext,
        completion=city,
        actions=[
            v0.UrlAction(
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


def setup(query):
    """Setup is successful if an empty list is returned.

    Use this function if you need the user to provide you data
    """

    results = []
    return results
