"""Looking for the photo in memory: what is still reachable once the request is over.

``reachable(roots)`` walks everything the roots refer to, the way the garbage collector sees it
(``gc.get_referents``): attributes, dictionary and list contents, slots, the variables a function
closed over, the local variables of a coroutine that is still waiting. That is wider than walking
the fields of dataclasses and models by hand, which cannot see a photo captured by a closure or
kept in a pending task.

What it does not do, on purpose: follow modules, classes and the globals of a function. They are
code, and following them leads to the whole interpreter. State kept in a module (a cache, a
singleton) is reached by passing the module's variables as roots (``module_state``).

What it cannot see: memory that is not Python objects (the buffers inside a PIL image's pixel store,
a C library's heap, what torch holds on a device), and memory the process freed but the operating
system has not yet overwritten. A real model's weights could keep a copy of the input; this audit
runs with a fake model, so that is checked in the code (see ``docs/privacy.md``), not here.
"""

import asyncio
import contextlib
import gc
import logging
import sys
import types
from collections import deque
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from PIL import Image

from tests.guards.privacy.traces import Trace, find, is_an_image, signs_of_an_image
from vga.models import QueryImage, SearchRequest

_NOT_FOLLOWED = (
    types.ModuleType,
    type,
    types.CodeType,
    types.BuiltinFunctionType,
    types.MethodDescriptorType,
    types.WrapperDescriptorType,
    types.GetSetDescriptorType,
    types.MemberDescriptorType,
    asyncio.AbstractEventLoop,
    logging.Logger,
)
"""Things whose referents are the rest of the interpreter, not state the request left behind."""

_TEST_MACHINERY = ("_pytest", "pytest", "respx", "pluggy")
"""Modules whose objects belong to the test tools, not to the product. The test's own doubles (the
fake OpenAI server, the fake clock) record what they were sent by design and are passed to
``reachable`` in ``skip`` one by one, so that nothing is hidden by a rule about names."""

MAX_OBJECTS = 2_000_000


def _children(obj: object) -> Iterator[object]:
    if isinstance(obj, types.FunctionType):
        # Follow what the function closed over and its defaults, not its globals.
        for cell in obj.__closure__ or ():
            try:
                yield cell.cell_contents
            except ValueError:  # an empty cell
                continue
        yield from obj.__defaults__ or ()
        yield from (obj.__kwdefaults__ or {}).values()
    elif isinstance(obj, types.MethodType):
        yield obj.__self__
        yield obj.__func__
    elif not isinstance(obj, _NOT_FOLLOWED):
        yield from gc.get_referents(obj)


def _is_test_machinery(obj: object) -> bool:
    return type(obj).__module__.startswith(_TEST_MACHINERY)


def reachable(roots: Iterable[object], *, skip: Iterable[object] = ()) -> Iterator[object]:
    """Every object reachable from ``roots``, once each. ``skip`` holds objects (the test's own
    doubles) that are neither yielded nor followed."""
    seen: set[int] = {id(item) for item in skip}
    with contextlib.suppress(RuntimeError):  # outside a running loop there is no current task
        seen.add(id(asyncio.current_task()))  # the test itself: its locals are the test's
    queue: deque[object] = deque(roots)
    while queue:
        obj = queue.popleft()
        if id(obj) in seen or _is_test_machinery(obj):
            continue
        seen.add(id(obj))
        if len(seen) > MAX_OBJECTS:
            msg = f"the walk left the request's state ({MAX_OBJECTS} objects): narrow the roots"
            raise RuntimeError(msg)
        yield obj
        queue.extend(_children(obj))


def module_state(prefixes: tuple[str, ...] = ("vga", "app")) -> list[object]:
    """The module-level variables of our own modules: caches, singletons, anything kept between
    requests without being owned by the pipeline object."""
    state: list[object] = []
    for name, module in list(sys.modules.items()):
        if module is None or not (
            name in prefixes or name.startswith(tuple(f"{p}." for p in prefixes))
        ):
            continue
        state += [
            value for value in vars(module).values() if not isinstance(value, types.ModuleType)
        ]
    return state


# --------------------------------------------------------------------------------------------
# What counts as a photo being held
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Held:
    what: str
    where: str


def holds_a_photo(obj: object, traces: list[Trace]) -> str | None:
    """Why ``obj`` is, or contains, the photo; ``None`` when it is not. Looks at the object itself,
    not at what it refers to (``reachable`` visits those)."""
    if isinstance(obj, bytes | bytearray | memoryview):
        blob = bytes(obj)
        if found := find(blob, traces):
            return f"bytes containing {found[0]}"
        if signs := signs_of_an_image(blob) or (
            ["a decodable picture"] if is_an_image(blob) else []
        ):
            return f"bytes that are an image ({signs[0]})"
    elif isinstance(obj, str):
        if found := find(obj, traces):
            return f"text containing {found[0]}"
        if signs := signs_of_an_image(obj):
            return f"text with {signs[0]}"
    elif isinstance(obj, Image.Image):
        return f"a decoded picture ({obj.size[0]}x{obj.size[1]}) kept in memory"
    elif isinstance(obj, QueryImage) and obj.image is not None:
        return "a QueryImage that still has its photo"
    elif isinstance(obj, SearchRequest) and obj.image is not None:
        return "a SearchRequest that still has its photo"
    return None


def photos_held(
    roots: Iterable[object], traces: list[Trace], *, skip: Iterable[object] = ()
) -> list[Held]:
    """Everything reachable from ``roots`` that is, or contains, the photo."""
    held: list[Held] = []
    for obj in reachable(roots, skip=skip):
        if (why := holds_a_photo(obj, traces)) is not None:
            held.append(Held(why, f"{type(obj).__qualname__} object"))
    return held


def new_holders_of(photo: bytes, *, ignore: Iterable[object]) -> list[str]:
    """What refers to this very bytes object now, apart from the objects in ``ignore``."""
    ignored = {id(item) for item in ignore}
    holders: list[str] = []
    for referrer in gc.get_referrers(photo):
        if id(referrer) in ignored or isinstance(referrer, types.FrameType | list):
            continue
        holders.append(type(referrer).__qualname__)
    return holders


def describe(held: list[Held]) -> list[Any]:
    return [f"{item.what} in a {item.where}" for item in held]
