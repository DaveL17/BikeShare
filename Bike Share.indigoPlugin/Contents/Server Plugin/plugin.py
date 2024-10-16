# noqa pylint: disable=too-many-lines, line-too-long, invalid-name, unused-argument, redefined-builtin, broad-except, fixme

"""
BikeShare Indigo Plugin
Author: DaveL17

The BikeShare Plugin takes JSON data provided by services and makes it available in Indigo. Users create individual
devices that represent bike dock stations. The plugin makes 100% of the data available--however, some sharing services
don't currently populate 100% of the fields that the system provides. Any service that uses the "Station Bean List"
format should be compatible with this plugin. If there are stations that support this format which are not included in
this plugin, please feel free to post to the BikeShare Plugin forum on the Indigo community forums.
"""

# ================================== IMPORTS ==================================

# Built-in modules
import datetime as dt
import logging
import csv
import requests
from requests import utils

# Third-party modules
try:
    import indigo  # noqa
    import pydevd  # noqa
except ImportError:
    pass

# My modules
import DLFramework.DLFramework as Dave
from constants import *  # noqa
from plugin_defaults import kDefaultPluginPrefs  # noqa
# =================================== HEADER ==================================

__author__    = Dave.__author__
__copyright__ = Dave.__copyright__
__license__   = Dave.__license__
__build__     = Dave.__build__
__title__     = 'BikeShare Plugin for Indigo'
__version__   = '2023.0.3'


# =============================================================================
class Plugin(indigo.PluginBase):
    """
    Standard Indigo Plugin Class

    :param indigo.PluginBase:
    """
    def __init__(self, plugin_id: str = "", plugin_display_name: str = "", plugin_version: str = "",
                 plugin_prefs: indigo.Dict = None):
        """
        Plugin initialization

        :param str plugin_id:
        :param str plugin_display_name:
        :param str plugin_version:
        :param indigo.Dict plugin_prefs:
        """
        super().__init__(plugin_id, plugin_display_name, plugin_version, plugin_prefs)

        # ============================ Instance Attributes =============================
        self.open_for_business       = None
        self.debug_level             = int(self.pluginPrefs.get('showDebugLevel', 30))
        self.download_interval       = int(self.pluginPrefs.get('downloadInterval', 900))
        self.master_trigger_dict     = {}
        self.plugin_is_initializing  = True
        self.plugin_is_shutting_down = False
        self.system_data             = {}

        # =============================== Debug Logging ================================
        self.plugin_file_handler.setFormatter(logging.Formatter(Dave.LOG_FORMAT, datefmt='%Y-%m-%d %H:%M:%S'))
        self.debug_level = int(self.pluginPrefs.get('showDebugLevel', "30"))

        # Convert debugLevel scale to new scale
        try:
            if self.debug_level < 4:
                self.debug_level *= 10
        except ValueError:
            self.debug_level = 30

        self.indigo_log_handler.setLevel(self.debug_level)

        # ========================== Initialize DLFramework ===========================
        self.fogbert = Dave.Fogbert(self)

        # ============================= Remote Debugging ==============================
        try:
            pydevd.settrace('localhost', port=5678, stdoutToServer=True, stderrToServer=True, suspend=False)
        except:
            pass

        self.plugin_is_initializing = False

    # =============================================================================
    def log_plugin_environment(self):
        """
        Log pluginEnvironment information when plugin is first started
        """
        self.fogbert.pluginEnvironment()

    # =============================================================================
    def __del__(self):
        """
        Title Placeholder
        :return:
        """
        indigo.PluginBase.__del__(self)

    # =============================================================================
    # =============================== Indigo Methods ===============================
    # =============================================================================
    def closed_prefs_config_ui(self, values_dict: indigo.Dict = None, user_cancelled: bool = False):
        """
        Standard Indigo method called when plugin preferences dialog is closed.

        :param indigo.Dict values_dict:
        :param bool user_cancelled:
        :return:
        """
        if not user_cancelled:
            # Ensure that self.pluginPrefs includes any recent changes.
            for k in values_dict:
                self.pluginPrefs[k] = values_dict[k]

            # Debug Logging
            self.debug_level = int(values_dict['showDebugLevel'])
            self.indigo_log_handler.setLevel(self.debug_level)
            indigo.server.log(f"Debugging on (Level: {DEBUG_LABELS[self.debug_level]} ({self.debug_level})")

            # Plugin-specific actions
            self.download_interval = int(values_dict.get('downloadInterval', 15))
            self.logger.debug("Plugin prefs saved.")

        else:
            self.logger.debug("Plugin prefs cancelled.")

        return values_dict

    # =============================================================================
    def device_start_comm(self, dev: indigo.Device = None):  # noqa
        """
        Standard Indigo method when device comm is enabled

        :param indigo.Device dev:
        :return:
        """
        dev.updateStateOnServer('onOffState', value=False, uiValue="Starting")
        # We send a copy of the device to the refresh_bike_data method here so that the plugin doesn't do a global
        # update of all devices for each device started.
        self.refresh_bike_data(device=dev, force=True)
        self.parse_bike_data(dev=dev)

    # =============================================================================
    @staticmethod
    def device_stop_comm(dev: indigo.Device = None):  # noqa
        """
        Standard Indigo method when device comm is disabled

        :param indigo.Device dev:
        :return:
        """
        dev.updateStateOnServer('onOffState', value=False, uiValue="Disabled")
        dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    # =============================================================================
    def get_prefs_config_ui_values(self):  # noqa
        """
        Standard Indigo method for when plugin preferences dialog is opened
        """
        plugin_prefs = self.pluginPrefs

        # Default choices for dynamic menus
        if plugin_prefs.get('start_time', "") == "":
            plugin_prefs['start_time'] = "00:00"

        if plugin_prefs.get('stop_time', "") == "":
            plugin_prefs['stop_time'] = "24:00"

        if int(plugin_prefs.get('showDebugLevel', "30")) < 4:
            plugin_prefs['showDebugLevel'] = '30'

        return plugin_prefs

    # =============================================================================
    def run_concurrent_thread(self):  # noqa
        """
        Standard Indigo method that runs continuously (if present)
        """
        self.sleep(2)

        try:
            while True:
                if self.business_hours():
                    self.refresh_bike_data(force=False)
                    self.process_triggers()
                self.download_interval = int(self.pluginPrefs.get('downloadInterval', 900))
                self.sleep(self.download_interval)

        except self.StopThread:
            self.logger.debug("Stopping concurrent thread.")

    # =============================================================================
    @staticmethod
    def sendDevicePing(dev_id: int = 0, suppress_logging: bool = False):  # noqa
        """
        Standard Indigo method for when plugin device receives a ping request

        :param int dev_id:
        :param bool suppress_logging:
        :return:
        """
        indigo.server.log("BikeShare Plugin devices do not support the ping function.")
        return {'result': 'Failure'}

    # =============================================================================
    def shutdown(self):
        """
        Standard Indigo method for when the plugin is shut down
        """
        self.plugin_is_shutting_down = True

    # =============================================================================
    def startup(self):
        """
        Standard Indigo method for when the plugin is started
        """
        # =========================== Audit Indigo Version ============================
        self.fogbert.audit_server_version(min_ver=2022)

    # =============================================================================
    def trigger_start_processing(self, trigger: indigo.Trigger):  # noqa
        """
        Standard Indigo Method for trigger enabled

        :param indigo.Trigger trigger:
        :return:
        """
        self.master_trigger_dict[trigger.pluginProps['listOfStations']] = trigger.id

    # =============================================================================
    def trigger_stop_processing(self, trigger = indigo.Trigger):  # noqa
        """
        Standard Indigo Method for trigger disabled

        :param indigo.Trigger trigger:
        :return:
        """

    # =============================================================================
    # ============================ BikeShare Methods ==============================
    # =============================================================================
    def business_hours(self):
        """
        Test to see if current time is within plugin operation hours

        The business_hours() method tests to see if the current time is within the operation hours set within the
        plugin configuration dialog.  It returns True if it is within business hours, otherwise returns False.
        ---
        :return bool:
        """
        now = dt.datetime.now()
        start_updating = self.pluginPrefs.get('start_time', "00:00")
        start_time     = now.replace(hour=int(start_updating[0:2]), minute=int(start_updating[3:5]))
        stop_updating  = self.pluginPrefs.get('stop_time', "23:59")
        if stop_updating == "24:00":
            stop_updating = "23:59"
        stop_time      = now.replace(hour=int(stop_updating[0:2]), minute=int(start_updating[3:5]))

        # Otherwise, let's check to see if we're open for business.
        if start_time < now < stop_time:
            value = True
        else:
            self.logger.info("Closed for business.")
            value = False

        self.open_for_business = value
        return value

    # =============================================================================
    def commsKillAll(self):  # noqa
        """
        The commsKillAll() method has been deprecated.

        Supports legacy installations.
        """
        self.comms_kill_all()

    # =============================================================================
    @staticmethod
    def comms_kill_all():
        """
        Disable all plugin devices in Indigo

        comms_kill_all() sets the enabled status of all plugin devices to false.
        """
        for dev in indigo.devices.iter(filter="self"):
            indigo.device.enable(dev, value=False)

    # =============================================================================
    def commsUnkillAll(self):  # noqa
        """
        The commsUnkillAll() method has been deprecated.

        Supports legacy installations.
        """
        self.comms_unkill_all()

    # =============================================================================
    @staticmethod
    def comms_unkill_all():
        """
        Enable all plugin devices in Indigo

        comms_unkill_all() sets the enabled status of all plugin devices to true.
        """
        for dev in indigo.devices.iter(filter="self"):
            indigo.device.enable(dev, value=True)

    # =============================================================================
    def dump_bike_data(self):
        """
        Title Placeholder
        """
        debug_level = int(self.pluginPrefs.get('showDebugLevel', "30"))
        time_stamp  = dt.datetime.now().strftime("%Y-%m-%d %H.%M")
        log_path    = indigo.server.getLogsFolderPath()
        file_name   = f"{log_path}/com.fogbert.indigoplugin.bikeShare/{time_stamp} BikeShare data.txt"

        with open(file_name, 'w', encoding="utf-8") as out_file:
            out_file.write("BikeShare Plugin Data\n")
            out_file.write(f"{time_stamp}\n")
            out_file.write(f"{self.system_data}")

        self.indigo_log_handler.setLevel(20)
        self.logger.info(f"Data written to {file_name}")
        self.indigo_log_handler.setLevel(debug_level)

    # =============================================================================
    @staticmethod
    def generator_time(filter: str = "", values_dict: indigo.Dict = None, type_id: str = "", target_id: int = 0):  # noqa
        """
        List of hours generator

        Creates a list of times for use in setting the desired time for weather forecast emails to be sent.

        :param str filter:
        :param indigo.Dict values_dict:
        :param str type_id:
        :param int target_id:
        :return list:
        """
        return [(f"{hour:02.0f}:00", f"{hour:02.0f}:00") for hour in range(0, 25)]

    # =============================================================================
    def get_bike_data(self):
        """
        Download the necessary JSON data from the bike sharing service

        The get_bike_data action reaches out to the bike share server and downloads the JSON needed data.

        :return dict self.system_data:
        """
        self.system_data = {}

        try:
            # Get the selected service from the plugin config dict.
            lang = self.pluginPrefs.get('language', 'en')
            auto_discovery_url = self.pluginPrefs.get('bike_system', None)

            # Waiting for pluginPrefs to be written to server upon first install.
            while not auto_discovery_url:
                self.sleep(4)
                auto_discovery_url = self.pluginPrefs.get('bike_system', None)
                self.logger.debug("Waiting for bike system data.")

            # Go and get the data from the bike sharing service.
            self.logger.debug(f"Auto-discovery URL: {auto_discovery_url}")
            reply = requests.get(auto_discovery_url, timeout=15)
            for feed in reply.json()['data'][lang]['feeds']:
                self.system_data[feed['name']] = requests.get(feed['url']).json()
            return self.system_data

        # ======================== Communication Error Handling ========================
        except requests.exceptions.ConnectionError:
            self.logger.exception("Connection Error. Will try again later.")

        except Exception:  # noqa
            self.logger.exception("General exception.")
            self.logger.debug("Error: ", exc_info=True)

    # =============================================================================
    def get_system_list(self, filter: str = "", type_id: int = 0, values_dict: indigo.Dict = None, target_id: int = 0) -> list:  # noqa
        """
        Title Placeholder

        :param str filter:
        :param int type_id:
        :param indigo.Dict values_dict:
        :param int target_id:
        :return:
        """
        with requests.get("https://raw.githubusercontent.com/NABSA/gbfs/master/systems.csv", timeout=10) as response:
            csv_dict = csv.DictReader(response.content.decode('utf-8').splitlines())

        # convert the DictReader object to a list because DictReader objects are not subscriptable.
        new_dict = list(csv_dict)

        # construct the combined name for a dropdown list.
        for system in new_dict:
            name = system['Name'].lstrip(' ')
            loc  = system['Location']
            system["Combined Name"] = f"{name} ({loc})"

        # convert iterator into list and collapse any spaces in the URL field.
        list_li = [(_["Auto-Discovery URL"].replace(" ", ""), _["Combined Name"]) for _ in new_dict]

        # Percent-encode as much as possible.
        list_li = [(requests.utils.quote(k, safe="%:/"), v) for (k, v) in list_li]

        # Log the number of available systems.
        num_systems = len(list_li)

        self.logger.debug(f"{num_systems} bike sharing systems available.")
        return sorted(list_li, key=lambda tup: tup[1].lower())

    # =============================================================================
    def get_station_list(self, filter: str = "", type_id: int = 0, values_dict: indigo.Dict = None, target_id: int = 0):  # noqa
        """
        Create a list of bike sharing stations for dropdown menus

        The get_station_list() method generates a sorted list of station names for use in device config dialogs.

        :param str filter:
        :param str type_id:
        :param int target_id:
        :param indigo.Dict values_dict:
        :return list:
        """
        station_information = self.system_data['station_information']['data']['stations']
        return sorted([(key['station_id'], key['name']) for key in station_information], key=lambda x: x[-1])

    # =============================================================================
    def parse_bike_data(self, dev: indigo.Device = None):
        """
        Parse bike data for saving to custom device states

        The parse_bike_data() method takes the JSON data (contained within 'self.system_data' variable) and assigns
        values to relevant device states. In instances where the service provides a null string value, the plugin
        assigns the value of "Not provided." to alert the user to that fact.

        :param indigo.Device dev:
        :return:
        """
        states_list = []
        station_id  = dev.pluginProps['stationName']

        # Station information
        for station in self.system_data['station_information']['data']['stations']:
            if station['station_id'] == station_id:
                for key in ('capacity', 'lat', 'lon', 'name',):
                    states_list.append({'key': key, 'value': station.get(key, 'Unknown')})

        # Station Status
        for station in self.system_data['station_status']['data']['stations']:
            if station['station_id'] == station_id:
                for key in (
                    'is_renting',
                    'is_returning',
                    'num_bikes_available',
                    'num_bikes_disabled',
                    'num_docks_available',
                    'num_docks_disabled',
                    'num_ebikes_available',
                ):

                    # Coerce select entries to bool
                    for _ in ('is_renting', 'is_returning'):
                        if station[_] == 1:
                            station[_] = True
                        else:
                            station[_] = False

                    states_list.append({'key': key, 'value': station.get(key, 'Unknown')})

                # ================================== Data Age ==================================
                try:
                    last_report = int(station['last_reported'])
                    fmt = "%Y-%m-%d %H:%M:%S"
                    last_report_human = dt.datetime.fromtimestamp(last_report).strftime(fmt)

                    diff_time = dt.datetime.now() - dt.datetime.fromtimestamp(last_report)

                    # Sometimes the sharing service clock is ahead of the Indigo server clock. Since the result can't
                    # be negative by definition, let's make it zero and call it a day.
                    time_diff = max(diff_time.total_seconds(), 0)
                    diff = dt.timedelta(seconds=time_diff)
                    diff_time_str = f"{diff}"

                    states_list.append({'key': 'last_reported', 'value': station.get(last_report_human, 'Unknown')})
                    states_list.append({'key': 'dataAge', 'value': station.get(diff_time_str, 'Unknown')})

                except Exception:  # noqa
                    self.logger.exception()
                    states_list.append({'key': 'dataAge', 'value': "Unknown", 'uiValue': "Unknown"})

        dev.updateStatesOnServer(states_list)

    # =============================================================================
    def process_triggers(self):
        """
        Process plugin triggers

        The process_triggers method will examine the statusValue state of each device, determine whether there is a
        trigger for any stations reported as not in service, and fire the corresponding trigger.

        :return:
        """
        try:
            for dev in indigo.devices.iter(filter='self'):

                station_name   = dev.states['stationName']
                station_status = dev.states['statusValue']
                if station_name in self.master_trigger_dict:

                    # This relies on all services reporting status value of 'In Service' when things are normal.
                    if station_status != 'In Service':
                        trigger_id = self.master_trigger_dict[station_name]

                        if indigo.triggers[trigger_id].enabled:
                            indigo.trigger.execute(trigger_id)
                            indigo.server.log(f"{dev.name} location is not in service.")

        except KeyError:
            pass

    # =============================================================================
    def refreshBikeAction(self, values_dict: indigo.Device = None):  # noqa
        """
        The refreshBikeAction() method has been deprecated.

        Supports legacy installations.

        :param indigo.Dict values_dict:
        :return:
        """
        self.refresh_bike_action(values_dict=values_dict)

    # =============================================================================
    def refresh_bike_action(self, values_dict: indigo.Dict = None):  # noqa
        """
        Refresh bike data based on call from Indigo Action item

        The refresh_bike_action method is used to trigger a data refresh cycle (get it?) when requested by the user
        through an Indigo action.

        :param indigo.Dict values_dict:
        :return:
        """
        self.refresh_bike_data()

    # =============================================================================
    def refresh_bike_data(self, device=None, force: bool = False) -> None:
        """
        Refresh bike data based on a call from Indigo Plugin menu

        This method refreshes bike data for all devices based on a plugin menu call. Note that this method does not
        honor the "business hours" limitation, as it is assumed that--since the user has requested an update--they are
        interested in getting one regardless of the time of day.
        """

        try:
            states_list = []

            self.get_bike_data()

            for dev in indigo.devices.iter(filter="self"):
                # If the caller has provided a device and the device provided is not the iterated device, we skip it.
                # This is to ensure that the refresh_bike_data method isn't run for each existing device when
                # device_start_comm is called (it's the only place that provides a specific device instance).
                if device and device.id != dev.id:
                    continue

                # determine if a device update is needed
                date_diff = (dt.datetime.now() - dev.lastChanged).total_seconds()
                time_to_refresh = date_diff > (int(self.pluginPrefs['downloadInterval'] - 5))

                # It's not time to refresh devices yet. If force is True, we go ahead and update the device anyway.
                if not force or time_to_refresh:
                    self.logger.debug("Not time to refresh devices.")
                    return

                dev.updateStateOnServer('onOffState', value=True, uiValue="Refreshing")
                dev.stateListOrDisplayStateIdChanged()

                if not dev.configured:
                    indigo.server.log(f"[{dev.name}] Skipping device because it is not fully configured.")
                    self.sleep(60)

                elif dev.enabled:
                    try:
                        if self.system_data:
                            self.parse_bike_data(dev)

                            if dev.states['is_renting'] == 1:
                                num_bikes = dev.states['num_bikes_available']
                                states_list.append({'key': 'onOffState', 'value': True, 'uiValue': f"{num_bikes}"})
                                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
                            else:
                                states_list.append({'key': 'onOffState', 'value': False, 'uiValue': "Not Renting"})
                                dev.updateStateImageOnServer(indigo.kStateImageSel.Error)

                        else:
                            dev.setErrorStateOnServer("No Comm")
                            self.logger.debug("Comm error. Sleeping until next scheduled poll.")
                            dev.updateStateImageOnServer(indigo.kStateImageSel.Error)

                    except Exception:  # noqa
                        states_list.append({
                            'key': 'onOffState',
                            'value': False,
                            'uiValue': f"{dev.states['num_bikes_available']}"
                            },
                        )
                        dev.setErrorStateOnServer("Error")
                        self.logger.exception()
                        self.logger.debug("Sleeping until next scheduled poll.")
                        dev.updateStateImageOnServer(indigo.kStateImageSel.Error)

                    states_list.append({
                        'key': 'businessHours',
                        'value': self.open_for_business,
                        'uiValue': self.open_for_business
                        }
                    )
                    self.logger.info(f"[{dev.name}] Data refreshed.")
                    dev.updateStatesOnServer(states_list)

        except Exception:  # noqa
            self.logger.exception("There was a problem refreshing the data. Will try on next cycle.")

    def my_tests(self, action: indigo.PluginAction = None) -> None:
        """
        The main unit test method

        The my_tests method is called from a plugin action item and, when called, imports all unit tests and runs them.
        If the unit test module returns True, then all tests have passed.
        """
        from Tests import test_plugin  # test_devices
        tests = test_plugin.TestPlugin()
        if tests.test_plugin_action(self):
            self.logger.warning("Plugin action tests passed.")
        if tests.test_get_system_list(self):
            self.logger.warning("Get system list tests passed.")
        if tests.test_get_station_list(self):
            self.logger.warning("Get station list tests passed.")
        if tests.test_get_bike_data(self):
            self.logger.warning("Get bike data tests passed.")

