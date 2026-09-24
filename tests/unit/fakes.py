"""
Lightweight stand-ins for the `indigo` module and Indigo device/trigger objects.

plugin.py is designed to run inside the Indigo host process, which injects the `indigo`
module automatically. To exercise plugin.py's own logic directly and offline -- with no
running Indigo server -- this module builds a minimal fake `indigo` module (just enough
surface area for plugin.py to import and run) and installs it into `sys.modules` before
plugin.py is imported.

This is intentionally separate from, and does not modify, `tests/shared` (the read-only
TestingBase submodule used by the Indigo-server-dependent tests in test_plugin.py and
test_xml.py).
"""

import contextlib
import datetime as dt
import logging
import sys
import types
from typing import Any, Optional
from unittest.mock import MagicMock


class FakeDevice:
    """A minimal stand-in for an indigo.Device, sufficient for plugin.py's device methods."""

    def __init__(
        self,
        dev_id: int = 1,
        name: str = "Test Station",
        plugin_props: Optional[dict] = None,
        enabled: bool = True,
        configured: bool = True,
        last_changed: Optional[dt.datetime] = None,
    ) -> None:
        self.id = dev_id
        self.name = name
        self.pluginProps = plugin_props or {}
        self.states: dict[str, Any] = {}
        self.enabled = enabled
        self.configured = configured
        self.lastChanged = last_changed or dt.datetime.min
        self.error_state: Optional[str] = None
        self.state_images: list = []

    def updateStateOnServer(self, key: str, value: Any = None, uiValue: Optional[str] = None) -> None:  # noqa
        self.states[key] = value

    def updateStatesOnServer(self, states_list: list) -> None:
        for entry in states_list:
            self.states[entry['key']] = entry['value']

    def updateStateImageOnServer(self, image_sel: Any) -> None:
        self.state_images.append(image_sel)

    def setErrorStateOnServer(self, message: str) -> None:
        self.error_state = message

    def stateListOrDisplayStateIdChanged(self) -> None:
        pass


class FakeDevicesCollection:
    """Stand-in for the `indigo.devices` collection."""

    def __init__(self) -> None:
        self._devices: list[FakeDevice] = []

    def add(self, device: FakeDevice) -> None:
        self._devices.append(device)

    def clear(self) -> None:
        self._devices = []

    def iter(self, filter: str = "") -> list:  # noqa
        return list(self._devices)

    def __iter__(self):
        return iter(self._devices)


class FakeTrigger:
    """A minimal stand-in for an indigo.Trigger."""

    def __init__(self, trigger_id: int, enabled: bool = True) -> None:
        self.id = trigger_id
        self.enabled = enabled


def install_fake_indigo() -> types.ModuleType:
    """Build a fake `indigo` module, install it into `sys.modules`, and return it.

    Safe to call more than once; later calls replace the module (and its device/trigger
    collections) with a fresh instance so tests don't leak state between test modules.

    Returns:
        types.ModuleType: The fake `indigo` module now installed in `sys.modules['indigo']`.
    """
    indigo_module = types.ModuleType("indigo")

    # ------------------------- Type-annotation placeholders -------------------------
    # plugin.py annotates several method signatures with these (e.g. `Optional[indigo.Device]`).
    # Python evaluates those annotations at class-definition time, so they must exist here even
    # though tests pass in FakeDevice/plain dicts/etc. instead -- annotations aren't enforced at
    # runtime, so the placeholders themselves never need to do anything.
    indigo_module.Dict = dict
    indigo_module.Device = type("Device", (), {})
    indigo_module.Trigger = type("Trigger", (), {})
    indigo_module.actionGroup = type("actionGroup", (), {})

    class PluginBase:
        """Minimal stand-in for indigo.PluginBase."""

        def __init__(
            self,
            plugin_id: str = "",
            plugin_display_name: str = "",
            plugin_version: str = "",
            plugin_prefs: Optional[dict] = None,
        ) -> None:
            self.pluginId = plugin_id
            self.pluginPrefs = dict(plugin_prefs or {})
            self.plugin_file_handler = MagicMock()
            self.indigo_log_handler = MagicMock()
            self.logger = logging.getLogger("bikeshare.test")

        def __del__(self) -> None:
            pass

        def sleep(self, seconds: float) -> None:  # noqa
            pass

        class StopThread(Exception):
            pass

    indigo_module.PluginBase = PluginBase

    # -------------------------------- Runtime surface --------------------------------
    indigo_module.devices = FakeDevicesCollection()
    indigo_module.triggers = {}
    indigo_module.trigger = MagicMock()
    indigo_module.device = MagicMock()
    indigo_module.server = MagicMock()
    indigo_module.kStateImageSel = types.SimpleNamespace(
        Error=object(),
        SensorOn=object(),
        SensorOff=object(),
    )

    sys.modules["indigo"] = indigo_module
    return indigo_module


@contextlib.contextmanager
def freeze_time(fixed_now: dt.datetime):
    """Make `plugin.dt.datetime.now()` return a fixed value for the duration of the `with` block.

    plugin.py's logic methods call `dt.datetime.now()` directly, so tests that depend on "now"
    (business_hours(), parse_bike_data()'s dataAge calculation) would otherwise be
    non-deterministic. This patches only `.now()`; every other `datetime`/`timedelta` behavior
    (`.replace()`, comparisons, `.fromtimestamp()`, etc.) is untouched real stdlib behavior.

    Args:
        fixed_now (datetime.datetime): The value `dt.datetime.now()` should return while active.

    Yields:
        None
    """
    import plugin  # local import: plugin.py must already be imported by the time this is used

    real_datetime = plugin.dt.datetime

    class _FrozenDatetime(real_datetime):
        @classmethod
        def now(cls, tz=None):  # noqa
            return fixed_now

    plugin.dt.datetime = _FrozenDatetime
    try:
        yield
    finally:
        plugin.dt.datetime = real_datetime
