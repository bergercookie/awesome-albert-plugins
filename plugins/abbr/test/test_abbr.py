"""Tests for the abbr plugin."""

from conftest import load_plugin

abbr = load_plugin("abbr")


def test_entries_keep_abbreviations_that_share_a_key():
    entries = abbr.make_latest_entries(
        ["* foo: first\n", "* foo: second\n", "* bar: third\n"]
    )
    assert entries == [("foo", "first"), ("foo", "second"), ("bar", "third")]


def test_search_index_lists_every_entry_for_a_shared_key():
    entries = abbr.make_latest_entries(["* foo: first\n", "* foo: second\n"])
    index = abbr.make_search_index(entries)
    assert index["foo"] == [0, 1]


def test_search_index_also_matches_descriptions():
    entries = abbr.make_latest_entries(["* foo: first\n"])
    index = abbr.make_search_index(entries)
    assert index["first"] == [0]


def test_append_abbreviation_uses_the_configured_separator(tmp_path):
    path = tmp_path / "abbreviations.txt"
    path.write_text("")

    abbr.append_abbreviation(path, "foo", "bar", "=")

    assert path.read_text() == "\n* foo= bar"


def test_config_widget_exposes_path_and_separator():
    properties = {
        widget["property"]
        for widget in abbr.Plugin().configWidget()
        if "property" in widget
    }
    assert properties == {"abbreviations_path", "separator"}
