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

DEVICE_FOLDER = int(os.getenv("DEVICE_FOLDER", 0))


# ================================== Actions ===================================
class TestPluginActions(APIBase):
    """Tests for plugin actions executed via Indigo action groups."""

    # =============================== setUpClass ===============================
    @classmethod
    def setUpClass(cls):
        pass

    # ==================== test_refresh_bike_data_action =======================
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


# ================================= Triggers ===================================
class TestPluginTriggers(APIBase):
    """Tests for plugin-defined Indigo triggers."""

    # =============================== setUpClass ===============================
    @classmethod
    def setUpClass(cls):
        pass

    # ================== test_station_out_of_service_trigger ===================
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


# ================================ Menu Items ==================================
class TestPluginMenuItems(APIBase):
    """Tests for plugin menu items invoked via hidden actions through the Indigo Web Server API."""

    # =============================== setUpClass ===============================
    @classmethod
    def setUpClass(cls):
        pass

    # ============================ _execute_action =============================
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

    # ========================== test_comms_kill_all ===========================
    def test_comms_kill_all(self):
        """Verify that disabling and re-enabling all plugin devices both succeed."""
        kill_result = self._execute_action("kill_all_comms")
        self.assertIsInstance(kill_result, httpx.Response, "Kill all request failed; no response received.")
        self.assertEqual(kill_result.status_code, 200, "The kill all comms call was not successful.")

        time.sleep(1)

        unkill_result = self._execute_action("unkill_all_comms")
        self.assertIsInstance(unkill_result, httpx.Response, "Unkill all request failed; no response received.")
        self.assertEqual(unkill_result.status_code, 200, "The unkill all comms call was not successful.")

    # ==================== test_log_plugin_information =========================
    def test_log_plugin_information(self):
        """Verify that the 'Display Plugin Information' menu item runs successfully."""
        result = self._execute_action("log_plugin_environment")
        self.assertIsInstance(result, httpx.Response, "Request failed; no response received.")
        self.assertEqual(result.status_code, 200, "The menu item call was not successful.")

    # ========================== test_dump_bike_data ===========================
    def test_dump_bike_data(self):
        """Verify that the 'Refresh Data Now' menu item triggers a bike data refresh."""
        result = self._execute_action("dump_bike_data")
        self.assertIsInstance(result, httpx.Response, "Request failed; no response received.")
        self.assertEqual(result.status_code, 200, "The menu item call was not successful.")


# ================================ Devices =====================================
class TestDevices(APIBase):
    """Tests for plugin devices defined in Devices.xml."""

    # =============================== setUpClass ===============================
    @classmethod
    def setUpClass(cls):
        pass

    # ================================= payload ================================
    @staticmethod
    def payload(name: str = "", device_type_id: str = "", props: dict = None):
        """Generate a script payload for creating a device via the Indigo host script API.

        Args:
            name (str): The quoted device name string passed to the host script.
            device_type_id (str): The Indigo device type ID from Devices.xml.
            props (dict): The device props dict passed to the host script.

        Returns:
            str: A host script string that creates the device and returns True on success.
        """
        return textwrap.dedent(f"""\
            try:
                import time
                indigo.device.create(protocol=indigo.kProtocol.Plugin,
                    name={name},
                    description='BikeShare unit test device',
                    pluginId='{os.getenv('PLUGIN_ID')}',
                    deviceTypeId='{device_type_id}',
                    props={props},
                    folder={DEVICE_FOLDER}
                )
                time.sleep(1)
                return True
            except:
                return False
        """)

    # ============================ confirm_creation ============================
    @staticmethod
    def confirm_creation(name: str = ""):
        """Generate a script payload that confirms a device exists in the plugin's device list.

        Args:
            name (str): The quoted device name string passed to the host script.

        Returns:
            str: A host script string that returns True if the device is found.
        """
        return textwrap.dedent(f"""\
            if {name} in [dev.name for dev in indigo.devices.iter('{os.getenv('PLUGIN_ID')}')]:
                return True
            else:
                return False
        """)

    # ============================= delete_device ==============================
    @staticmethod
    def delete_device(name: str = ""):
        """Generate a script payload that deletes a device by name.

        Args:
            name (str): The quoted device name string passed to the host script.

        Returns:
            str: A host script string that deletes the device and returns True on success.
        """
        return textwrap.dedent(f"""\
            try:
                indigo.device.delete({name})
                return True
            except:
                return False
        """)

    # ====================== create_and_delete_device ==========================
    def create_and_delete_device(self, name: str, device_type_id: str, props: dict):
        """Create a plugin device, confirm it exists, then delete it.

        Args:
            name (str): The quoted device name string passed to the host script.
            device_type_id (str): The Indigo device type ID from Devices.xml.
            props (dict): The device props dict passed to the host script.
        """
        host_script = self.payload(name, device_type_id, props)
        run_host_script(host_script)
        self.assertTrue(host_script, "Device creation successful.")

        host_script = self.confirm_creation(name)
        self.assertTrue(host_script, "Could not confirm the device was created.")

        host_script = self.delete_device(name)
        run_host_script(host_script)
        self.assertTrue(host_script, "Device deletion failed.")

    # ======================= Bike Share Station Device ========================
    def test_share_dock_device_creation(self):
        """Verify that a Bike Share Station device can be created and deleted via the Indigo API."""
        my_props = {'stationName': os.getenv("STATION_NAME", "")}
        self.create_and_delete_device("'bs_unit_test_share_dock_device'", 'shareDock', my_props)
