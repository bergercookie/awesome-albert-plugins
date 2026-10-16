"""Type stub for the `albert` module a plugin runs against.

`albert` is injected into the plugin's interpreter by the launcher's python
plugin loader, so it is not an importable module and cannot be typechecked from
its source. This stub is what mypy reads instead.

It is deliberately not a copy of the upstream `albert.pyi`: that file is
hand-written and it lists the logging helpers as members of `albert`, which they
are not. The launcher does

    py::setattr(module_, "critical", ...)

on the *plugin's own module* just before `exec_module`, so inside a plugin they
are bare globals. `test/albert_stub.py` is the matching runtime double, and
`test/test_albert_stub.py` asserts the two agree on the public names.

Keep the signatures here loose. This exists to catch the mistakes that are
actually made when writing a plugin - a misspelled keyword, a StandardItem
constructed wrong, a Result used as a list - not to describe C++ precisely.
"""

from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Protocol, Union

# --- icons ---------------------------------------------------------------------------


class IconUrl(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> str: ...


class Icon(Protocol):
    @property
    def urls(self) -> List[str]: ...
    def isDark(self) -> bool: ...
    def isTemplate(self) -> bool: ...
    @staticmethod
    def image(path: Any) -> Icon:
        """An icon from an image file, given as a str or a pathlib.Path."""
        ...


# --- results --------------------------------------------------------------------------


class Result(Protocol):
    def text(self) -> str: ...
    def subtext(self) -> str: ...
    def icon(self) -> Icon: ...


class Item(Result, Protocol):
    @property
    def id(self) -> str: ...
    @property
    def actions(self) -> List[Action]: ...
    def isActionable(self) -> bool: ...


class RankItem(Item, Protocol):
    def score(self) -> float: ...


class IndexItem(Item, Protocol):
    def index(self) -> Any: ...


class ActionItem(Item, Protocol):
    def call(self) -> None: ...


# --- actions -------------------------------------------------------------------------


# The callable is `Callable[..., Any]`, not `Callable[[], Any]`: the idiom in this
# repo is to bind loop and closure variables with a default argument
# (`lambda name=name: ...`), which mypy cannot reconcile with a zero-argument
# signature. The launcher itself only ever calls it with no arguments.
class Action:
    def __init__(
        self,
        id: str,
        text: str,
        callable: Callable[..., Any],
    ) -> None: ...
    def id(self) -> str: ...
    def text(self) -> str: ...
    def callable(self) -> Callable[..., Any]: ...


# --- query handling -------------------------------------------------------------------


class Context:
    @property
    def trigger(self) -> str: ...
    @property
    def query(self) -> str: ...
    @property
    def isValid(self) -> bool: ...
    @property
    def usageScoring(self) -> bool: ...
    def setQuery(self, query: str) -> None: ...


class QueryContext(Context):
    @property
    def plugin(self) -> str: ...


class QueryHandler:
    def update(self, query: str) -> None: ...


class QueryResultItem(Protocol): ...


class ItemQueryHandler(QueryHandler):
    def __init__(self) -> None: ...
    def setQuery(self, ctx: Context) -> None: ...
    def setItems(self, items: List[Result]) -> None: ...
    def clearItems(self) -> None: ...
    def update(self, *args: Any, **kwargs: Any) -> None: ...


class GeneratorQueryHandler(QueryHandler):
    def __init__(self) -> None: ...
    # `Iterator[Any]`, not `Iterator[Sequence[Result]]`: a plugin annotates its
    # own items() as `Iterator[List[StandardItem]]`, and neither List nor
    # Sequence makes that a legal override, because Result is a Protocol and
    # `List[StandardItem]` is not a `Sequence[Result]` in mypy's eyes. Typing
    # the element type here buys nothing - every plugin's own annotation is
    # checked against its own yields - and costs every plugin an error it cannot
    # fix. The launcher only ever iterates what it is given.
    def items(self, ctx: Context) -> Iterator[Any]: ...


class StandardQueryHandler(QueryHandler):
    def __init__(self) -> None: ...


class RankedQueryHandler(QueryHandler):
    def __init__(self) -> None: ...
    def rankItems(self, ctx: Context) -> Iterator[Any]: ...
    def items(self, ctx: Context) -> Iterator[Any]: ...


class GlobalQueryHandler(RankedQueryHandler):
    def __init__(self) -> None: ...


class IndexQueryHandler(QueryHandler):
    def updateIndexItems(self) -> None: ...
    def setIndexItems(self, items: List[Result]) -> None: ...
    def setFuzzyMatching(self, enabled: bool) -> None: ...


class FallbackHandler(QueryHandler):
    def fallbacks(self, query_string: str) -> Iterator[Any]: ...


# --- results, concretely ----------------------------------------------------------------


class StandardItem:
    def __init__(
        self,
        id: Optional[str] = None,
        text: Optional[str] = None,
        subtext: Optional[str] = None,
        # Callable[..., Icon] for the same reason as Action.__init__: the idiom
        # in this repo is `lambda p=path: Icon.image(p)`, which mypy rejects
        # against a zero-argument signature.
        icon_factory: Optional[Callable[..., Icon]] = None,
        actions: Optional[List[Action]] = None,
        input_action_text: Optional[str] = None,
    ) -> None: ...
    def id(self) -> str: ...
    def text(self) -> str: ...
    def subtext(self) -> str: ...
    @property
    def icon(self) -> Icon: ...
    def actions(self) -> List[Action]: ...
    def isActionable(self) -> bool: ...


class RankItem_(RankItem, Protocol): ...


# --- config ---------------------------------------------------------------------------


class ConfigWidget(Protocol): ...


class PluginInstance:
    def id(self) -> str: ...
    def iid(self) -> str: ...
    def name(self) -> str: ...
    def icon(self) -> str: ...
    def cacheLocation(self) -> Path: ...
    def configLocation(self) -> Path: ...
    # dataLocation() is what the launcher provides, and it hands back a
    # pathlib.Path, not the str the docstring above implies - the plugins here
    # do `Path(self.dataLocation())` or plain `self.dataLocation() / x`.
    def dataLocation(self) -> Path: ...
    def state(self) -> Dict[str, Any]: ...
    def setState(self, state: Dict[str, Any]) -> None: ...
    def readConfig(self, key: str, type: Callable = ...) -> Any: ...
    def writeConfig(self, key: str, value: Any) -> bool: ...
    def setConfigWidget(self, widget: Any) -> None: ...


# --- ui -------------------------------------------------------------------------------


class Notification:
    def __init__(self, title: str = "", text: str = "") -> None: ...
    def send(self) -> None: ...
    def dismiss(self) -> None: ...


# --- clipboard and browser ------------------------------------------------------------


def setClipboardText(text: str) -> None: ...


def setClipboardTextAndPaste(text: str) -> None: ...


def openUrl(url: str, hideOnFocus: bool = ...) -> None: ...


def openTerminal(
    path: str = ...,
    additionalArguments: str = ...,
    escape: bool = ...,
) -> None: ...


def runTerminal(
    commandList: List[str] = ...,
    workingDirectory: str = ...,
    splitOutput: bool = ...,
) -> None: ...


def openFile(path: str, handler: str = ...) -> None: ...


def runDetachedProcess(cmdln: List[str], workdir: str = ...) -> int: ...


def havePasteSupport() -> bool: ...


def eventFilter(obj: Any, event: Any) -> None: ...


# --- matching and extensions ------------------------------------------------------------


class Color:
    def __init__(self, r: int = 0, g: int = 0, b: int = 0, a: int = 255) -> None: ...
    @property
    def rgba(self) -> Any: ...


class Brush:
    def __init__(self, color: Color) -> None: ...
    @property
    def color(self) -> Color: ...


class MatchConfig:
    def __init__(
        self,
        case_sensitive: bool = ...,
        ignore_case: bool = ...,
        fuzzy: bool = ...,
    ) -> None: ...
    @property
    def case_sensitive(self) -> bool: ...
    @property
    def fuzzy(self) -> bool: ...


class Match:
    def __init__(self, score: float = 0.0, text: str = "") -> None: ...
    @property
    def text(self) -> str: ...
    def __float__(self) -> float: ...
    def isExactMatch(self) -> bool: ...
    def isEmptyMatch(self) -> bool: ...


class Matcher:
    def __init__(self, query: str, config: Optional[MatchConfig] = ...) -> None: ...
    @property
    def query(self) -> str: ...
    @property
    def config(self) -> MatchConfig: ...
    def match(self, strings: Union[str, List[str]]) -> Optional[Match]: ...


class Extension:
    def id(self) -> str: ...


class UsageScoring:
    def modifyMatchScores(self, extension_id: str, rank_items: List[RankItem]) -> None: ...
