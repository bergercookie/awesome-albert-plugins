import imghdr
import json
import subprocess
from functools import cached_property
from pathlib import Path
from typing import Iterator, Optional

import albert as v0
import requests
from bs4 import BeautifulSoup

"""Search and potentially download images using Bing."""

user_agent = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:72.0) Gecko/20100101 Firefox/72.0"
)


class BingImage:
    def __init__(self, url: str, download_dir=Path()):
        self._url: str = url
        self._download_dir = download_dir
        self._type = ""

    @property
    def type(self) -> str:
        if self._type is "":
            self._type = imghdr.what(str(self.image))

            if self._type is None:
                self._type = ""

        return self._type

    @property
    def download_dir(self):
        return self._download_dir

    @download_dir.setter
    def download_dir(self, d):
        self._download_dir = d

    @cached_property
    def image(self):
        """Get the path to the downloaded image - Reuses the image if it's already in the cache."""
        assert self._url is not None

        filepath = self.download_dir / self._url.split("/")[-1]
        if not filepath.is_file():
            download_image(url=self._url, filepath=filepath)

        return filepath

    @property
    def thumbnail(self):
        return self.image
        # assert self._url is not None
        # if not self._cached_thumb:
        #     img = self.image

        # return self._cached_thumb

    @property
    def url(self):
        return self._url


def download_image(url, filepath: Path = Path()):
    v0.debug(f"Downloading image {url} -> {filepath}...")
    subprocess.check_output(["wget", "-O", str(filepath), url], stderr=subprocess.STDOUT)
    v0.debug(f"Downloaded image {url} -> {filepath}")


def bing_search(query: str, limit: int, adult_filter=False) -> Iterator[BingImage]:

    bool_corrs = {
        True: "on",
        False: "off",
    }

    page_counter = 0
    results_counter = 0
    while results_counter < limit:
        # Parse the page source and download pics
        headers = {"User-Agent": user_agent}
        payload = (
            ("q", str(query)),
            ("first", page_counter),
            ("adlt", bool_corrs[adult_filter]),
        )
        source = requests.get(
            "https://www.bing.com/images/async", params=payload, headers=headers
        ).content
        soup = BeautifulSoup(str(source).replace("\r\n", ""), "lxml")

        for a in soup.find_all("a", class_="iusc"):
            if results_counter >= limit:
                break

            try:
                iusc = json.loads(a.get("m").replace("\\", ""))
                url = iusc["murl"]
                yield BingImage(url=url)

                results_counter += 1
            except (json.decoder.JSONDecodeError, RuntimeError):
                continue
        page_counter += 1


if __name__ == "__main__":
    import sys

    assert len(sys.argv) >= 2, "I need a query string"
    query = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    imgs = bing_search(query, limit)
    print("Downloaded images: ")
    for img in imgs:
        print(f"\t{img.image}")
