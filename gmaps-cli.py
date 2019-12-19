#!/usr/bin/env python3

import argparse
import time
import webbrowser
from pathlib import Path
from typing import Tuple

from pyvirtualdisplay import Display
from selenium import webdriver

GMAPS = "https://maps.google.com"
USE_VIRTUAL_DISPLAY = False

# supplementary functions ---------------------------------------------------------------------
def add_parser_arg(parser: argparse.ArgumentParser, arg_name: str, **kargs):
    parser.add_argument(
        "-{}".format(arg_name[0]), "--{}".format(arg_name.replace("_", "-")), **kargs
    )


def start_selenium() -> Tuple[webdriver.firefox.webdriver.WebDriver, Display]:
    """Initialise selenium and return a WebDriver instance."""
    display = None
    if USE_VIRTUAL_DISPLAY:
        display = Display(visible=0, size=(1366, 768))
        display.start()

    driver = webdriver.Firefox()
    if USE_VIRTUAL_DISPLAY:
        driver.set_window_size(1366, 768)

    driver.get(GMAPS)

    return driver, display


def route(driver, src: str, dst: str, travel_by: str) -> str:
    """Compute and return a link to google maps for the desired route"""

    # toggle directions
    directions_btn = driver.find_element_by_id("searchbox-directions")
    directions_btn.click()
    time.sleep(1.0)

    # fill source, destination
    src_field_div = driver.find_element_by_id("directions-searchbox-0")
    src_searchbox = src_field_div.find_element_by_class_name("tactile-searchbox-input")
    src_searchbox.send_keys(src)

    dst_field_div = driver.find_element_by_id("directions-searchbox-1")
    dst_searchbox = dst_field_div.find_element_by_class_name("tactile-searchbox-input")
    dst_searchbox.send_keys(dst)
    time.sleep(0.5)

    # select travel mode
    travel_mode_btn = driver.find_element_by_class_name(
        f"directions-travel-mode-icon.directions-{travel_by}-icon"
    )
    travel_mode_btn.click()
    time.sleep(1.0)

    return driver.current_url


def autocomplete_place():
    raise NotImplementedError()


def main():
    # argument parsing ------------------------------------------------------------------------
    parser = argparse.ArgumentParser(prog=Path(__file__).name)
    subparsers = parser.add_subparsers(help="Available subcommands")

    # workaround for requiring a sub-command - https://bugs.python.org/issue9253#msg186387
    subparsers.required = True
    subparsers.dest = "sub-command"

    parser_route = subparsers.add_parser(
        "route", help="Compute the google-maps URL for the route and transit options specified"
    )
    add_parser_arg(parser_route, "source", help="Route origin", required=True)
    add_parser_arg(parser_route, "destination", help="Route destination", required=True)
    add_parser_arg(
        parser_route,
        "travel-by",
        help="Means of transportation",
        choices=["walk", "drive", "bicycle", "fly", "transit"],
        default="drive",
    )
    add_parser_arg(
        parser_route,
        "open",
        help="Open computed GoogleMaps route URL in the default browser",
        action="store_true",
    )

    parser_autocomplete_place = subparsers.add_parser(
        "autocomplete-place",
        help="[NOT WORKING] Get place autocompletion based on the given text",
    )
    parser_autocomplete_place.add_argument(
        "search_string", type=str, help="String to autocomplete"
    )

    parser_args = vars(parser.parse_args())

    driver, display = start_selenium()
    gmaps_url = None
    if parser_args["sub-command"] == "route":
        gmaps_url = route(
            driver,
            src=parser_args["source"],
            dst=parser_args["destination"],
            travel_by=parser_args["travel_by"],
        )
        print("gmaps_url: ", gmaps_url)
    else:
        autocomplete_place(driver, search_string=parser_args["search_string"])

    driver.quit()
    if USE_VIRTUAL_DISPLAY:
        display.stop()

    if gmaps_url and parser_args["open"]:
        webbrowser.open(gmaps_url)


if __name__ == "__main__":
    main()
