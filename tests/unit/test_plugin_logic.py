"""
Tests for the BikeShare plugin's core parsing and business logic.

Unlike test_plugin.py and test_xml.py, these tests do NOT require a running Indigo server,
an installed/enabled plugin, or a tests/.env file. They install a fake `indigo` module (see
fakes.py) and mock `httpx` so that plugin.py's logic methods -- parse_bike_data(),
business_hours(), process_triggers(), get_system_list(), get_bike_data(), and
refresh_bike_data() -- can be exercised directly and offline.

This suite intentionally does not use tests/shared's APIBase, since APIBase's setUpClass
talks to a live Indigo server (via the HTTP API and the indigo-host CLI) to do its work --
there's no offline mode for it, and it is imperative that tests/shared itself never be
modified to add one. Nothing in tests/shared is touched by this suite.
"""

import csv
import datetime as dt
import io
import sys
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import httpx

from .fakes import FakeDevice, FakeTrigger, freeze_time, install_fake_indigo

# ============================ Import plugin.py offline =============================
# plugin.py is designed to run inside the Indigo host process, which puts "Server Plugin"
# on sys.path and injects the `indigo` module automatically. To import it here, we have to
# do both of those things ourselves, in this order: install the fake `indigo` module first
# (plugin.py does `import indigo` at module scope), then add the real "Server Plugin"
# directory to sys.path (plugin.py also does bare `import constants`/`from plugin_defaults
# import ...`/`import DLFramework.DLFramework`, all of which need to be found there).
SERVER_PLUGIN_DIR = (
    Path(__file__).resolve().parents[2] / "Bike Share.indigoPlugin" / "Contents" / "Server Plugin"
)

fake_indigo = install_fake_indigo()
if str(SERVER_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_PLUGIN_DIR))

import plugin  # noqa: E402  (must come after the fake indigo module is installed)
from plugin_defaults import kDefaultPluginPrefs  # noqa: E402


def _make_plugin(extra_prefs: Optional[dict] = None) -> "plugin.Plugin":
    """Build a Plugin instance wired up to the fake indigo module for a single test.

    Args:
        extra_prefs (dict, optional): Plugin preference overrides for this instance.

    Returns:
        plugin.Plugin: A freshly constructed plugin instance.
    """
    fake_indigo.devices.clear()
    prefs = dict(kDefaultPluginPrefs)
    prefs.update(extra_prefs or {})
    return plugin.Plugin(
        plugin_id="com.fogbert.indigoplugin.bikeShare",
        plugin_display_name="Bike Share",
        plugin_version="2025.2.5",
        plugin_prefs=prefs,
    )


def _sample_system_data() -> dict:
    """A minimal, realistic two-station GBFS fixture (station_information + station_status)."""
    return {
        'station_information': {
            'data': {
                'stations': [
                    {
                        'station_id': 'A',
                        'name': 'Station A',
                        'capacity': 20,
                        'lat': 45.5,
                        'lon': -122.6,
                    },
                    {
                        'station_id': 'B',
                        'name': 'Station B',
                        'capacity': 15,
                        'lat': 45.6,
                        'lon': -122.7,
                    },
                ]
            }
        },
        'station_status': {
            'data': {
                'stations': [
                    {
                        'station_id': 'A',
                        'is_renting': 1,
                        'is_returning': 1,
                        'num_bikes_available': 3,
                        'num_bikes_disabled': 0,
                        'num_docks_available': 17,
                        'num_docks_disabled': 0,
                        'num_ebikes_available': 1,
                        'last_reported': 1700000000,
                    },
                    {
                        'station_id': 'B',
                        'is_renting': 0,
                        'is_returning': 1,
                        'num_bikes_available': 0,
                        'num_bikes_disabled': 2,
                        'num_docks_available': 13,
                        'num_docks_disabled': 0,
                        'num_ebikes_available': 0,
                        'last_reported': 1700000000,
                    },
                ]
            }
        },
    }


# ================================= parse_bike_data =================================
class TestParseBikeData(unittest.TestCase):
    """Tests for Plugin.parse_bike_data()."""

    def setUp(self) -> None:
        self.plugin = _make_plugin()
        self.plugin.system_data = _sample_system_data()

    def test_parses_known_station(self) -> None:
        """A station present in both feeds gets all its states populated."""
        dev = FakeDevice(plugin_props={'stationName': 'A'})
        self.plugin.parse_bike_data(dev)

        self.assertEqual(dev.states['capacity'], 20)
        self.assertEqual(dev.states['lat'], 45.5)
        self.assertEqual(dev.states['lon'], -122.6)
        self.assertEqual(dev.states['name'], 'Station A')
        self.assertIs(dev.states['is_renting'], True)
        self.assertIs(dev.states['is_returning'], True)
        self.assertEqual(dev.states['num_bikes_available'], 3)
        self.assertEqual(dev.states['num_docks_available'], 17)
        self.assertEqual(
            dev.states['last_reported'],
            dt.datetime.fromtimestamp(1700000000).strftime("%Y-%m-%d %H:%M:%S"),
        )

    def test_is_renting_coerced_to_bool_when_falsy(self) -> None:
        """`is_renting`/`is_returning` come in as 1/0 ints and must be coerced to real bools."""
        dev = FakeDevice(plugin_props={'stationName': 'B'})
        self.plugin.parse_bike_data(dev)

        self.assertIs(dev.states['is_renting'], False)
        self.assertIs(dev.states['is_returning'], True)

    def test_stops_at_first_match_not_just_first_station(self) -> None:
        """Regression test for the item #13 fix: matching must not depend on list position."""
        dev = FakeDevice(plugin_props={'stationName': 'B'})
        self.plugin.parse_bike_data(dev)

        # Station B is second in both lists; if the early-`break` were placed incorrectly
        # (e.g. breaking on the first station regardless of match), these values -- which
        # belong to B, not A -- would never get set.
        self.assertEqual(dev.states['name'], 'Station B')
        self.assertEqual(dev.states['num_bikes_available'], 0)

    def test_unknown_station_leaves_states_untouched(self) -> None:
        """A station id absent from both feeds results in no states being set (no crash)."""
        dev = FakeDevice(plugin_props={'stationName': 'does-not-exist'})
        self.plugin.parse_bike_data(dev)

        self.assertEqual(dev.states, {})

    def test_malformed_last_reported_falls_back_to_unknown(self) -> None:
        """A non-numeric `last_reported` is caught and reported as "Unknown", not raised."""
        self.plugin.system_data['station_status']['data']['stations'][0]['last_reported'] = "not-a-timestamp"
        dev = FakeDevice(plugin_props={'stationName': 'A'})
        self.plugin.parse_bike_data(dev)

        self.assertEqual(dev.states['last_reported'], "Unknown")
        self.assertEqual(dev.states['dataAge'], "Unknown")

    def test_data_age_reflects_elapsed_time(self) -> None:
        """`dataAge` is the (non-negative) difference between now and `last_reported`."""
        fixed_now = dt.datetime(2024, 1, 1, 0, 5, 0)
        last_reported_ts = int(dt.datetime(2024, 1, 1, 0, 0, 0).timestamp())
        self.plugin.system_data['station_status']['data']['stations'][0]['last_reported'] = last_reported_ts

        dev = FakeDevice(plugin_props={'stationName': 'A'})
        with freeze_time(fixed_now):
            self.plugin.parse_bike_data(dev)

        self.assertEqual(dev.states['dataAge'], "0:05:00")

    def test_future_last_reported_clamps_data_age_to_zero(self) -> None:
        """If the service's clock is ahead of ours, dataAge must not go negative."""
        fixed_now = dt.datetime(2024, 1, 1, 0, 0, 0)
        last_reported_ts = int(dt.datetime(2024, 1, 1, 0, 5, 0).timestamp())
        self.plugin.system_data['station_status']['data']['stations'][0]['last_reported'] = last_reported_ts

        dev = FakeDevice(plugin_props={'stationName': 'A'})
        with freeze_time(fixed_now):
            self.plugin.parse_bike_data(dev)

        self.assertEqual(dev.states['dataAge'], "0:00:00")


# ================================= business_hours ===================================
class TestBusinessHours(unittest.TestCase):
    """Tests for Plugin.business_hours()."""

    def test_same_day_window_open(self) -> None:
        p = _make_plugin({'start_time': "08:00", 'stop_time': "18:00"})
        with freeze_time(dt.datetime(2024, 1, 1, 12, 0, 0)):
            self.assertTrue(p.business_hours())

    def test_same_day_window_closed(self) -> None:
        p = _make_plugin({'start_time': "08:00", 'stop_time': "18:00"})
        with freeze_time(dt.datetime(2024, 1, 1, 20, 0, 0)):
            self.assertFalse(p.business_hours())

    def test_overnight_window_open_after_start(self) -> None:
        """Regression test for the item #7 fix: a start time later than the stop time wraps."""
        p = _make_plugin({'start_time': "22:00", 'stop_time': "06:00"})
        with freeze_time(dt.datetime(2024, 1, 1, 23, 30, 0)):
            self.assertTrue(p.business_hours())

    def test_overnight_window_open_before_stop(self) -> None:
        p = _make_plugin({'start_time': "22:00", 'stop_time': "06:00"})
        with freeze_time(dt.datetime(2024, 1, 1, 2, 0, 0)):
            self.assertTrue(p.business_hours())

    def test_overnight_window_closed_during_the_day(self) -> None:
        p = _make_plugin({'start_time': "22:00", 'stop_time': "06:00"})
        with freeze_time(dt.datetime(2024, 1, 1, 12, 0, 0)):
            self.assertFalse(p.business_hours())

    def test_stop_time_24_00_includes_last_second_of_day(self) -> None:
        p = _make_plugin({'start_time': "00:00", 'stop_time': "24:00"})
        with freeze_time(dt.datetime(2024, 1, 1, 23, 59, 59)):
            self.assertTrue(p.business_hours())

    def test_updates_business_hours_state_on_all_devices(self) -> None:
        p = _make_plugin({'start_time': "08:00", 'stop_time': "18:00"})
        dev1, dev2 = FakeDevice(dev_id=1), FakeDevice(dev_id=2)
        fake_indigo.devices.add(dev1)
        fake_indigo.devices.add(dev2)

        with freeze_time(dt.datetime(2024, 1, 1, 12, 0, 0)):
            p.business_hours()

        self.assertTrue(dev1.states['businessHours'])
        self.assertTrue(dev2.states['businessHours'])


# ================================ process_triggers ===================================
class TestProcessTriggers(unittest.TestCase):
    """Tests for Plugin.process_triggers()."""

    def setUp(self) -> None:
        self.plugin = _make_plugin()
        fake_indigo.triggers.clear()
        fake_indigo.trigger.execute.reset_mock()

    def test_fires_trigger_for_out_of_service_station(self) -> None:
        dev = FakeDevice(plugin_props={'stationName': 'A'})
        dev.states['is_renting'] = False
        fake_indigo.devices.add(dev)
        fake_indigo.triggers[99] = FakeTrigger(99, enabled=True)
        self.plugin.master_trigger_dict = {'A': 99}

        self.plugin.process_triggers()

        fake_indigo.trigger.execute.assert_called_once_with(99)

    def test_does_not_fire_when_station_is_renting(self) -> None:
        dev = FakeDevice(plugin_props={'stationName': 'A'})
        dev.states['is_renting'] = True
        fake_indigo.devices.add(dev)
        fake_indigo.triggers[99] = FakeTrigger(99, enabled=True)
        self.plugin.master_trigger_dict = {'A': 99}

        self.plugin.process_triggers()

        fake_indigo.trigger.execute.assert_not_called()

    def test_does_not_fire_when_trigger_disabled(self) -> None:
        dev = FakeDevice(plugin_props={'stationName': 'A'})
        dev.states['is_renting'] = False
        fake_indigo.devices.add(dev)
        fake_indigo.triggers[99] = FakeTrigger(99, enabled=False)
        self.plugin.master_trigger_dict = {'A': 99}

        self.plugin.process_triggers()

        fake_indigo.trigger.execute.assert_not_called()

    def test_no_registered_trigger_for_station_is_a_no_op(self) -> None:
        dev = FakeDevice(plugin_props={'stationName': 'A'})
        dev.states['is_renting'] = False
        fake_indigo.devices.add(dev)
        self.plugin.master_trigger_dict = {}

        # Should not raise.
        self.plugin.process_triggers()

        fake_indigo.trigger.execute.assert_not_called()

    def test_missing_is_renting_state_is_swallowed(self) -> None:
        """A device without an `is_renting` state yet (e.g. never successfully parsed) must not raise."""
        dev = FakeDevice(plugin_props={'stationName': 'A'})
        fake_indigo.devices.add(dev)
        self.plugin.master_trigger_dict = {'A': 99}
        fake_indigo.triggers[99] = FakeTrigger(99, enabled=True)

        # Should not raise.
        self.plugin.process_triggers()

        fake_indigo.trigger.execute.assert_not_called()


# ================================= get_system_list ===================================
class TestGetSystemList(unittest.TestCase):
    """Tests for Plugin.get_system_list()."""

    def setUp(self) -> None:
        self.plugin = _make_plugin()

    @staticmethod
    def _csv_response(rows: list) -> MagicMock:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=["Name", "Location", "Auto-Discovery URL"])
        writer.writeheader()
        writer.writerows(rows)
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.content = buffer.getvalue().encode("utf-8")
        return response

    def test_parses_and_sorts_systems(self) -> None:
        rows = [
            {"Name": " Zeta Bikes", "Location": "City Z", "Auto-Discovery URL": "https://zeta.example/gbfs.json"},
            {"Name": "Alpha Bikes", "Location": "City A", "Auto-Discovery URL": "https://alpha.example/gbfs .json"},
        ]
        with patch.object(plugin.httpx, "get", return_value=self._csv_response(rows)):
            result = self.plugin.get_system_list()

        self.assertEqual(
            result,
            [
                ("https://alpha.example/gbfs.json", "Alpha Bikes (City A)"),
                ("https://zeta.example/gbfs.json", "Zeta Bikes (City Z)"),
            ],
        )

    def test_http_error_returns_empty_list(self) -> None:
        """Regression test for the item #5/#6 split: an HTTP error is a distinct, handled branch."""
        response = MagicMock()
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "boom", request=MagicMock(), response=MagicMock(status_code=500)
        )
        with patch.object(plugin.httpx, "get", return_value=response):
            with self.assertLogs(self.plugin.logger, level="ERROR") as log_ctx:
                result = self.plugin.get_system_list()

        self.assertEqual(result, [])
        self.assertTrue(any("Communication error" in message for message in log_ctx.output))

    def test_unexpected_error_returns_empty_list(self) -> None:
        """Regression test for the item #6 split: a non-httpx bug is logged distinctly."""
        with patch.object(plugin.httpx, "get", side_effect=TypeError("boom")):
            with self.assertLogs(self.plugin.logger, level="ERROR") as log_ctx:
                result = self.plugin.get_system_list()

        self.assertEqual(result, [])
        self.assertTrue(any("Unexpected error" in message for message in log_ctx.output))


# ================================== get_bike_data ====================================
class TestGetBikeData(unittest.TestCase):
    """Tests for Plugin.get_bike_data()."""

    AUTO_DISCOVERY_URL = "https://example.test/gbfs.json"

    def setUp(self) -> None:
        self.plugin = _make_plugin({'bike_system': self.AUTO_DISCOVERY_URL, 'language': 'en'})

    def _discovery_response(self) -> MagicMock:
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            'data': {
                'en': {
                    'feeds': [
                        {'name': 'station_information', 'url': 'https://example.test/station_information.json'},
                        {'name': 'station_status', 'url': 'https://example.test/station_status.json'},
                    ]
                }
            }
        }
        return response

    def test_success_populates_system_data(self) -> None:
        feed_response = MagicMock()
        feed_response.raise_for_status = MagicMock()
        feed_response.json.return_value = {'ok': True}

        with patch.object(
            plugin.httpx, "get", side_effect=[self._discovery_response(), feed_response, feed_response]
        ):
            result = self.plugin.get_bike_data()

        self.assertEqual(result, {'station_information': {'ok': True}, 'station_status': {'ok': True}})
        self.assertEqual(self.plugin.system_data, {'station_information': {'ok': True}, 'station_status': {'ok': True}})

    def test_http_error_returns_none(self) -> None:
        """Regression test for the item #5 fix: raise_for_status() now runs on the discovery call too."""
        bad_response = MagicMock()
        bad_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "boom", request=MagicMock(), response=MagicMock(status_code=503)
        )
        with patch.object(plugin.httpx, "get", return_value=bad_response):
            with self.assertLogs(self.plugin.logger, level="ERROR") as log_ctx:
                result = self.plugin.get_bike_data()

        self.assertIsNone(result)
        self.assertTrue(any("Communication error" in message for message in log_ctx.output))

    def test_unexpected_error_returns_none(self) -> None:
        """Regression test for the item #6 split applied to get_bike_data() too."""
        with patch.object(plugin.httpx, "get", side_effect=[self._discovery_response()]):
            # Malformed feed data (not a list) triggers a TypeError while iterating, not an httpx error.
            bad_response = self._discovery_response()
            bad_response.json.return_value = {'data': {'en': {'feeds': None}}}
            with patch.object(plugin.httpx, "get", return_value=bad_response):
                with self.assertLogs(self.plugin.logger, level="ERROR") as log_ctx:
                    result = self.plugin.get_bike_data()

        self.assertIsNone(result)
        self.assertTrue(any("Unexpected error" in message for message in log_ctx.output))


# ============================ refresh_bike_data (device isolation) ===================
class TestRefreshBikeDataDeviceIsolation(unittest.TestCase):
    """Regression test for the item #2 fix.

    A device that fails before parse_bike_data() ever populates its states must not
    prevent devices later in the iteration order from being refreshed.
    """

    def test_one_devices_failure_does_not_abort_the_rest(self) -> None:
        p = _make_plugin({'downloadInterval': 895})
        p.system_data = _sample_system_data()
        p.get_bike_data = MagicMock()  # keep this test focused on the per-device loop

        # Station "missing" isn't in system_data, so parse_bike_data() will leave dev_bad's
        # states empty, which used to raise a second, uncaught KeyError inside the except
        # handler and abort the whole loop before dev_good was ever touched.
        dev_bad = FakeDevice(dev_id=1, name="Bad Station", plugin_props={'stationName': 'missing'})
        dev_good = FakeDevice(dev_id=2, name="Good Station", plugin_props={'stationName': 'A'})
        fake_indigo.devices.add(dev_bad)
        fake_indigo.devices.add(dev_good)

        p.refresh_bike_data(force=True)

        self.assertEqual(dev_bad.error_state, "Error")
        self.assertEqual(dev_bad.states.get('onOffState'), False)

        # This is the crux of the regression test: dev_good must have been reached and
        # refreshed normally, which the pre-fix code never allowed once dev_bad raised.
        self.assertEqual(dev_good.error_state, None)
        self.assertEqual(dev_good.states.get('num_bikes_available'), 3)
        self.assertEqual(dev_good.states.get('onOffState'), True)


# ==================== closed_prefs_config_ui / run_concurrent_thread =================
class TestClosedPrefsConfigUiIsNonBlocking(unittest.TestCase):
    """Regression test: closing the plugin config dialog must not block on network I/O.

    closed_prefs_config_ui() should only flag a refresh (self.refresh_requested); the
    actual refresh -- and its synchronous httpx calls -- must happen on the background
    thread (run_concurrent_thread()), not inline in the dialog-close callback.
    """

    def test_sets_refresh_flag_without_calling_refresh_bike_data(self) -> None:
        p = _make_plugin()
        p.get_bike_data = MagicMock()
        p.refresh_bike_data = MagicMock()

        p.closed_prefs_config_ui(
            values_dict={
                'showDebugLevel': '30',
                'downloadInterval': 895,
                'start_time': "08:00",
                'stop_time': "18:00",
            },
            user_cancelled=False,
        )

        p.refresh_bike_data.assert_not_called()
        p.get_bike_data.assert_not_called()
        self.assertTrue(p.refresh_requested)

    def test_cancelled_dialog_does_not_flag_a_refresh(self) -> None:
        p = _make_plugin()
        p.closed_prefs_config_ui(values_dict={}, user_cancelled=True)
        self.assertFalse(p.refresh_requested)


class TestRunConcurrentThreadPicksUpRefreshRequest(unittest.TestCase):
    """Regression test: a flagged refresh is picked up promptly by the background thread."""

    def test_refresh_requested_flag_triggers_immediate_refresh(self) -> None:
        p = _make_plugin({'downloadInterval': 895})
        p.get_bike_data = MagicMock()  # stands in for the network call refresh_bike_data() would trigger
        p.business_hours = MagicMock(return_value=False)  # isolate the flag-driven refresh path
        p.process_triggers = MagicMock()
        p.refresh_requested = True

        call_count = {'n': 0}

        def fake_sleep(seconds):  # noqa
            # First call is the method's fixed 2-second startup delay; the flagged refresh is
            # handled with zero further sleeps (see run_concurrent_thread's chunked-sleep loop),
            # so a second sleep() call only happens once the loop has moved on -- stop it there.
            call_count['n'] += 1
            if call_count['n'] >= 2:
                raise p.StopThread()

        p.sleep = fake_sleep

        p.run_concurrent_thread()

        p.get_bike_data.assert_called_once()
        self.assertFalse(p.refresh_requested)


if __name__ == "__main__":
    unittest.main()
