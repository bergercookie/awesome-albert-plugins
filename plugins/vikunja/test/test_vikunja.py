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


# -- searching tasks ---------------------------------------------------------------


def _task(task_id, title, description=""):
    return {"id": task_id, "title": title, "description": description, "done": False}


class _SearchClient:
    def __init__(self, tasks):
        self.tasks = tasks
        self.calls = []

    def get_all_tasks(self, filter_expr=None, search=None, per_page=100, max_pages=20):
        self.calls.append(
            {"filter_expr": filter_expr, "search": search, "per_page": per_page}
        )
        return self.tasks


def _search_plugin(monkeypatch, client):
    plugin = vikunja.Plugin()
    plugin._base_url = "https://vikunja.example.com"
    plugin._api_token = "token"
    monkeypatch.setattr(plugin, "_project_map", dict)
    monkeypatch.setattr(vikunja.Plugin, "client", property(lambda self: client))
    return plugin


def test_get_all_tasks_walks_every_page_and_dedupes(monkeypatch):
    client = vikunja.VikunjaClient("https://vikunja.example.com", "token")
    pages = {
        1: [{"id": 1}, {"id": 2}],
        2: [{"id": 2}, {"id": 3}],
        3: [],
    }
    calls = []

    def fake_get_tasks(filter_expr=None, search=None, per_page=100, page=1):
        calls.append((filter_expr, search, page))
        return pages.get(page, [])

    monkeypatch.setattr(client, "get_tasks", fake_get_tasks)

    tasks = client.get_all_tasks(filter_expr="done = false", search="middle")

    assert [t["id"] for t in tasks] == [1, 2, 3]
    assert calls == [
        ("done = false", "middle", 1),
        ("done = false", "middle", 2),
        ("done = false", "middle", 3),
    ]


def test_search_matches_a_word_from_the_middle_of_a_title(monkeypatch):
    client = _SearchClient([_task(7, "Review the quarterly budget spreadsheet")])
    plugin = _search_plugin(monkeypatch, client)

    items = plugin._fetch_search("budget", {})

    assert [item.text for item in items] == ["Review the quarterly budget spreadsheet"]
    assert client.calls == [
        {"filter_expr": "done = false", "search": "budget", "per_page": 100}
    ]


def test_search_falls_back_to_local_fuzzy_matching_for_typos(monkeypatch):
    class _Client:
        def __init__(self):
            self.searches = []

        def get_all_tasks(self, filter_expr=None, search=None, per_page=100, max_pages=20):
            self.searches.append(search)
            if search is not None:
                return []
            return [_task(1, "Buy milk")]

    client = _Client()
    plugin = _search_plugin(monkeypatch, client)

    items = plugin._fetch_search("mikl", {})

    assert [item.text for item in items] == ["Buy milk"]
    assert client.searches == ["mikl", None]
