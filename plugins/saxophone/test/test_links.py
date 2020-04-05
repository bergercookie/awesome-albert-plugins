import json
import logging
from concurrent import futures
from pathlib import Path

import requests

logger = logging.getLogger("__file__")


def check_link(link: str) -> int:
    headers = {}
    req = requests.head(link, headers=headers, timeout=1)
    return req


def test_links():
    json_file = Path(__file__).absolute().parent.parent / "config" / "saxophone.json"

    with open(json_file, "r") as f:
        conts = json.load(f)

    links = []
    for stream in conts["all"]:
        links.extend([val for key, val in stream.items() if key in ("url", "homepage")])

    with futures.ThreadPoolExecutor(max_workers=10) as executor:
        fs = {executor.submit(check_link, link): link for link in links}
        for f in futures.as_completed(fs):
            link = fs[f]
            logger.debug(f"Checking link - {link}")
            # Cannot get HEAD from RadioParadise links - that's OK for now.
            assert f.result().ok or f.result().status_code == 400, f"Invalid link detected - {link}"
            logger.debug(f"OK - {link}")
