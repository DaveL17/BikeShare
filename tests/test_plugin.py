"""
Tests for the BikeShare plugin's actions, triggers, and menu items.

Typically, all the tests in this file require the plugin to be installed and enabled.
"""

from tests.shared.classes import APIBase
from tests.shared.utils import run_host_script
import dotenv
import httpx
import os
import textwrap
import time

dotenv.load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))


class TestPluginActions(APIBase):
    """Tests for plugin actions executed via Indigo action groups."""
    @classmethod
    def setUpClass(cls):
        pass

    def test_refresh_bike_data_action(self):
        """Verify that executing the refresh bike data action group succeeds."""
        result = run_host_script(textwrap.dedent(f"""\
            plugin = indigo.server.getPlugin('{os.getenv('PLUGIN_ID')}')
            if plugin.isEnabled():
                indigo.actionGroup.execute({os.getenv('ACTION_GROUP_EXECUTE')})
                return True
            else:
                return False
        """)
        )
        self.assertIsNotNone(result, "run_host_script returned None.")
        self.assertTrue(result, "Plugin is not enabled.")


class TestPluginTriggers(APIBase):
    """Tests for plugin-defined Indigo triggers."""

    @classmethod
    def setUpClass(cls):
        pass

    def test_station_out_of_service_trigger(self):
        """Verify that the station out-of-service trigger can be executed successfully."""
        result = run_host_script(textwrap.dedent(f"""\
            plugin = indigo.server.getPlugin('{os.getenv('PLUGIN_ID')}')
            if plugin.isEnabled():
                indigo.trigger.execute({os.getenv('TRIGGER_STATION_OUT_OF_SERVICE')})
                return True
            else:
                return False
        """)
        )
        self.assertIsNotNone(result, "run_host_script returned None.")
        self.assertTrue(result, "Plugin is not enabled.")


class TestPluginMenuItems(APIBase):
    """Tests for plugin menu items invoked via hidden actions through the Indigo Web Server API."""

    @classmethod
    def setUpClass(cls):
        pass

    @staticmethod
    def _execute_action(action_id: str) -> bool | httpx.Response:
        """Post a plugin.executeAction command to the Indigo Web Server API.

        Args:
            action_id (str): The Indigo action ID to execute.

        Returns:
            bool | httpx.Response: The HTTP response, or False if the request failed.
        """
        try:
            message = {
                "id": "test-plugin-menu-item",
                "message": "plugin.executeAction",
                "pluginId": os.getenv("PLUGIN_ID"),
                "actionId": action_id,
            }
            url = f"{os.getenv('URL_PREFIX')}/v2/api/command/?api-key={os.getenv('GOOD_API_KEY')}"
            return httpx.post(url, json=message, verify=False)
        except Exception as e:
            print(f"API Error {e}")
            return False

    def test_comms_kill_all(self):
        """Verify that disabling and re-enabling all plugin devices both succeed."""
        kill_result = self._execute_action("kill_all_comms")
        self.assertIsInstance(kill_result, httpx.Response, "Kill all request failed; no response received.")
        self.assertEqual(kill_result.status_code, 200, "The kill all comms call was not successful.")

        time.sleep(1)

        unkill_result = self._execute_action("unkill_all_comms")
        self.assertIsInstance(unkill_result, httpx.Response, "Unkill all request failed; no response received.")
        self.assertEqual(unkill_result.status_code, 200, "The unkill all comms call was not successful.")

    def test_log_plugin_information(self):
        """Verify that the 'Display Plugin Information' menu item runs successfully."""
        result = self._execute_action("log_plugin_environment")
        self.assertIsInstance(result, httpx.Response, "Request failed; no response received.")
        self.assertEqual(result.status_code, 200, "The menu item call was not successful.")

    def test_dump_bike_data(self):
        """Verify that the 'Refresh Data Now' menu item triggers a bike data refresh."""
        result = self._execute_action("dump_bike_data")
        self.assertIsInstance(result, httpx.Response, "Request failed; no response received.")
        self.assertEqual(result.status_code, 200, "The menu item call was not successful.")
