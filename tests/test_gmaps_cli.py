from pathlib import Path
import subprocess

import pytest

gmaps_cli_path = Path(__file__).parent.parent / "gmaps-cli.py"


def test_gmaps_cli_noargs():
    p = subprocess.Popen([gmaps_cli_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, stderr = p.communicate(timeout=2)
    assert any(["sub-command" in l.decode("utf-8") for l in stderr.splitlines()])
    assert p.returncode == 2


def test_gmaps_cli_help():
    subprocess.check_call([gmaps_cli_path, "-h"])
    subprocess.check_call([gmaps_cli_path, "--help"])


def test_gmaps_cli_invalid_command():
    p = subprocess.Popen([gmaps_cli_path, "kalimera"])
    p.communicate(timeout=2)
    assert p.returncode == 2


def test_gmaps_cli_sample_route():
    subprocess.Popen([gmaps_cli_path, "route"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)


@pytest.mark.skip(reason="Not Implemented")
def test_gmaps_cli_autocomplete_place():
    p = subprocess.Popen(
        [gmaps_cli_path, "autocomplete-place", "lond"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = p.communicate(timeout=2)

    assert any(["London" in l.decode("utf-8") for l in stdout.splitlines()])
    assert not stderr
    assert p.returncode == 0
