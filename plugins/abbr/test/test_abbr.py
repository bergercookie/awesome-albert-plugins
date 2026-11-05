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
