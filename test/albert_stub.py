"""Faithful mock of the Albert v5.0 Python plugin API (Python interface 5.0).

Used purely to smoke-test plugin code in CI / locally without a real Albert
install. Mirrors the surface described in albertlauncher's `albert.pyi` stub
and the pybind11 bindings in `src/embeddedmodule.hpp`.

Enable the extra assertions (e.g. "items() must yield lists") with
ALBERT_MOCK_STRICT=1.
"""

import os
import sys
from typing import ClassVar, Dict, List

STRICT = os.environ.get("ALBERT_MOCK_STRICT") == "1"


class _Enum:
    def __init__(self, *names):
        for i, n in enumerate(names):
            setattr(self, n, i)


# --------------------------------------------------------------------------- #
# Icons
# --------------------------------------------------------------------------- #
class Icon:
    StandardIconType = _Enum(
        "Any", "Computer", "Drive", "Folder", "Network", "OpticalMedia",
        "World", "Application", "Document", "Executable", "File", "Favorites",
        "Font", "Game", "Config", "Package", "Device", "Terminal", "Text",
        "Image", "Audio", "Video", "Archive", "User", "System", "Preferences",
        "Screenshot", "Unknown", "Frequent", "Featured", "Trash", "New",
        "Warning", "Information", "Error", "Calendar", "Contact", "Play",
        "TabCloseButton", "CalendarToday", "CalendarTomorrow", "CalendarNext",
        "FileDialogBack", "FileDialogContents", "FileDialogFileName",
        "FileDialogInfo", "FileDialogListView", "FileDialogNewFolder",
        "FileDialogOpen", "FileDialogPermissions", "FileDialogSave",
        "FileDialogDetailedView", "FileDialogDetailedContents",
    )

    def __init__(self, kind="empty", payload=None):
        self.kind = kind
        self.payload = payload

    @staticmethod
    def image(path):
        return Icon("image", str(path))

    @staticmethod
    def fileType(path):
        return Icon("fileType", str(path))

    @staticmethod
    def theme(name):
        return Icon("theme", name)

    @staticmethod
    def standard(t):
        return Icon("standard", t)

    @staticmethod
    def grapheme(grapheme, scalar=1.0, brush=None):
        return Icon("grapheme", grapheme)

    @staticmethod
    def iconified(icon, background_brush=None, border_radius=1.0,
                  border_width=1, border_brush=None):
        return Icon("iconified", icon)

    @staticmethod
    def composed(icon1, icon2, size1=0.7, size2=0.7, x1=0.0, y1=0.0, x2=1.0, y2=1.0):
        return Icon("composed", (icon1, icon2))

    def __str__(self):
        return f"albert-icon://{self.kind}/{self.payload}"

    def __repr__(self):
        return f"Icon({self.kind!r}, {self.payload!r})"


class Color:
    def __init__(self, r=0, g=0, b=0, a=255):
        self.rgba = (r, g, b, a)

    def __repr__(self):
        return f"Color{self.rgba}"


class Brush:
    def __init__(self, color):
        self.color = color

    def __repr__(self):
        return f"Brush({self.color!r})"


# --------------------------------------------------------------------------- #
# Items
# --------------------------------------------------------------------------- #
class Item:
    def __init__(self, **kwargs):
        self._icon = None
        self.id = kwargs.get("id")
        self.text = kwargs.get("text")
        self.subtext = kwargs.get("subtext")
        self.actions = list(kwargs.get("actions", []))
        for k in kwargs:
            if k not in ("id", "text", "subtext", "actions", "icon_factory"):
                raise TypeError(f"Item got unexpected keyword argument {k!r}")

    @property
    def icon(self):
        return self._icon() if callable(self._icon) else self._icon

    def __repr__(self):
        return f"<{type(self).__name__} text={self.text!r} id={self.id!r}>"


class StandardItem(Item):
    def __init__(self, id=None, text=None, subtext=None, icon_factory=None,
                 actions=None, input_action_text=None):
        # None, not []: a mutable default is shared by every StandardItem ever
        # made. Item.__init__ copies what it is given, so this cannot leak.
        super().__init__(id=id, text=text, subtext=subtext, actions=actions)
        self._icon = icon_factory
        self.input_action_text = input_action_text

    def __setattr__(self, name, value):
        # The C++ props are writable in the real binding; mirror that.
        object.__setattr__(self, name, value)


class Action:
    def __init__(self, id=None, text=None, callable=None, **kwargs):
        if "name" in kwargs:
            # v5 kwarg is `id`; a `name=` kwarg is a v0-ism and must fail loudly.
            raise TypeError("Action() got an unexpected keyword argument 'name'")
        self.id = id
        self.text = text
        self.callable = callable

    def __repr__(self):
        return f"<Action {self.id!r} {self.text!r}>"


class RankItem:
    def __init__(self, item=None, score=0.0):
        if not isinstance(score, float):
            raise TypeError("RankItem score must be a float")
        self.item = item
        self.score = score


class IndexItem:
    def __init__(self, item=None, string=""):
        self.item = item
        self.string = string


# --------------------------------------------------------------------------- #
# Query context / handlers
# --------------------------------------------------------------------------- #
class QueryContext:
    def __init__(self, query="", trigger=""):
        self._query = query
        self._trigger = trigger
        self._valid = True

    @property
    def query(self):
        return self._query

    @property
    def string(self):
        raise AttributeError(
            "QueryContext.string was removed in interface 5.0; use .query"
        )

    @property
    def trigger(self):
        return self._trigger

    @property
    def isValid(self):
        return self._valid

    @property
    def usageScoring(self):
        return None


# Old alias, deliberately absent from the module namespace in real Albert.
_UNSET = object()


class _HandlerBase:
    pass


class QueryHandler(_HandlerBase):
    def __init__(self):
        pass

    def __init_subclass__(cls, **kwargs):
        for gone in ("handleTriggerQuery", "handleGlobalQuery", "handleQuery",
                     "setQuery", "setParent", "updateItem", "removeItem"):
            if gone in cls.__dict__:
                raise TypeError(
                    f"{cls.__name__} defines removed API method {gone}()"
                )
        super().__init_subclass__(**kwargs)


class GeneratorQueryHandler(QueryHandler):
    def items(self, ctx):
        raise NotImplementedError


class RankedQueryHandler(QueryHandler):
    def rankItems(self, ctx):
        raise NotImplementedError

    def items(self, ctx):
        if STRICT:
            return NotImplementedError(
                "RankedQueryHandler must implement rankItems()"
            )
        raise NotImplementedError


class GlobalQueryHandler(RankedQueryHandler):
    def __init__(self):
        RankedQueryHandler.__init__(self)


class IndexQueryHandler(QueryHandler):
    def updateIndexItems(self):
        raise NotImplementedError

    def setIndexItems(self, items):
        self._index_items = list(items)

    def setFuzzyMatching(self, enabled):
        return self.updateIndexItems()


class FallbackHandler(QueryHandler):
    def fallbacks(self, query_string):
        raise NotImplementedError


class Extension:
    pass


class UsageScoring:
    def modifyMatchScores(self, extension_id, rank_items):
        return None


# --------------------------------------------------------------------------- #
# Matching
# --------------------------------------------------------------------------- #
class MatchConfig:
    def __init__(self, case_sensitive=False, ignore_case=True, fuzzy=True):
        self.case_sensitive = case_sensitive
        self.fuzzy = fuzzy


class Match:
    def __init__(self, score=0.0, text=""):
        self._score = score
        self.text = text

    def __float__(self):
        return float(self._score)

    def isExactMatch(self):
        return self._score >= 1.0

    def isEmptyMatch(self):
        return self._score == 0.0

    def __repr__(self):
        return f"<Match {self._score} {self.text!r}>"


class Matcher:
    def __init__(self, query, config=None):
        self.query = query
        self.config = config or MatchConfig()

    def match(self, strings):
        if isinstance(strings, str):
            strings = [strings]
        q = self.query.lower()
        for s in strings:
            t = (s or "").lower()
            if q in t:
                return Match(len(q) / max(len(t), 1), s)
        return None


# --------------------------------------------------------------------------- #
# Plugin instance
# --------------------------------------------------------------------------- #
class Notification:
    # ClassVar, not a per-instance list: a plugin's tests read Notification.SENT
    # to see what it sent, and the launcher keeps one notification object alive.
    SENT: ClassVar[List] = []

    def __init__(self, title="", text=""):
        self.title = title
        self.text = text
        self._dismissed = False

    def send(self):
        Notification.SENT.append((self.title, self.text))
        return self

    def dismiss(self):
        self._dismissed = True
        return self


class PluginInstance:
    # ClassVar for the same reason as Notification.SENT: the store is shared,
    # and it is reset per test in conftest rather than per instance.
    _CONFIG: ClassVar[Dict] = {}

    def __init__(self):
        self._trigger = None
        self._fuzzy = True
        self._exts = []

    def id(self):
        return "python.mock"

    def name(self):
        return "Mock"

    def description(self):
        return "Mock plugin"

    def cacheLocation(self):
        return _TMP("cache") / self.id()

    def configLocation(self):
        return _TMP("config") / self.id()

    def dataLocation(self):
        return _TMP("data") / self.id()

    def extensions(self):
        return self._exts

    def readConfig(self, key, type=None):
        if type is None:
            raise TypeError(
                "readConfig() missing required argument: 'type' (str|int|float|bool)"
            )
        if type not in (str, int, float, bool):
            raise TypeError(f"readConfig(): unsupported type {type!r}")
        return self._CONFIG.get((self.id(), key))

    def writeConfig(self, key, value):
        self._CONFIG[(self.id(), key)] = value

    def defaultTrigger(self):
        return self.id()[len("python."):] + " "

    def setTrigger(self, trigger):
        self._trigger = trigger

    def trigger(self):
        return self._trigger or self.defaultTrigger()

    def allowTriggerRemap(self):
        return True

    def supportsFuzzyMatching(self):
        return self._fuzzy

    def setFuzzyMatching(self, enabled):
        self._fuzzy = enabled

    def synopsis(self, query):
        return ""


# --------------------------------------------------------------------------- #
# Module functions
# --------------------------------------------------------------------------- #
def _TMP(kind):
    from pathlib import Path

    p = Path(os.environ.get("ALBERT_MOCK_HOME", "/tmp/albert-mock")) / kind
    p.mkdir(parents=True, exist_ok=True)
    return p


_CLIPBOARD = {"text": ""}

# NOTE: albert does NOT export debug/info/warning/critical. The real loader
# (pypluginloader.cpp) does py::setattr(module_, "debug"/"info"/"warning"/
# "critical", ...) on the *plugin's own module*, so plugins call them as bare
# globals without importing. They are deliberately absent here so that a plugin
# doing `from albert import critical` fails here exactly as it does on a real
# install. The harness injects them per-plugin, the way the loader does.
_LOGS: List = []


def _record(level):
    def _log(arg):
        _LOGS.append((level, str(arg)))

    return _log


def setClipboardText(text):
    _CLIPBOARD["text"] = text


def setClipboardTextAndPaste(text):
    setClipboardText(text)


def havePasteSupport():
    return False


def openUrl(url):
    _CLIPBOARD.setdefault("urls", []).append(url)


def openFile(path):
    _CLIPBOARD.setdefault("files", []).append(path)


def runDetachedProcess(cmdln, workdir=""):
    return 0


def runTerminal(script):
    _CLIPBOARD.setdefault("terminals", []).append(script)


def __getattr__(name):
    # Anything not defined above does not exist in the v5.0 API.
    raise AttributeError(
        f"module 'albert' has no attribute {name!r} "
        f"(removed or never part of the v5.0 API)"
    )
