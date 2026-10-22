"""Tests for the vikunja plugin's query dispatch.

Only the parts that don't need a live Vikunja server: which items a query
yields, and especially that a search with no results falls back to creating a
task instead of opening Vikunja.
"""

from conftest import load_plugin

vikunja = load_plugin("vikunja")


class _Ctx:
    def __init__(self, query):
        self.query = query


class _Task:
    id = "vikunja-task-1"


def _plugin(monkeypatch, results):
    plugin = vikunja.Plugin()
    plugin._base_url = "https://vikunja.example.com"
    plugin._api_token = "token"
    plugin._default_project = "Inbox"
    monkeypatch.setattr(plugin, "_project_map", dict)
    monkeypatch.setattr(plugin, "_fetch_search", lambda query, project_map: results)
    return plugin


def test_search_without_results_offers_to_add_the_task(monkeypatch):
    plugin = _plugin(monkeypatch, [])

    [item] = next(plugin.items(_Ctx("buy milk")))

    assert item.text == "buy milk"
    assert item.subtext.startswith("No matching tasks")
    assert "Project: Inbox" in item.subtext
    assert item.actions[0].text == "Create task in Vikunja"


def test_search_without_results_still_parses_quick_add_magic(monkeypatch):
    plugin = _plugin(monkeypatch, [])

    [item] = next(plugin.items(_Ctx("buy milk +Home *errand")))

    assert item.text == "buy milk"
    assert "Project: Home" in item.subtext
    assert "Labels: errand" in item.subtext


def test_search_with_results_does_not_offer_to_add_the_task(monkeypatch):
    task = _Task()
    plugin = _plugin(monkeypatch, [task])

    items = next(plugin.items(_Ctx("buy milk")))

    assert items == [task]
