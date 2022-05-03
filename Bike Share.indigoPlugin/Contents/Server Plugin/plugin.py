# noqa pylint: disable=too-many-lines, line-too-long, invalid-name, unused-argument, redefined-builtin, broad-except, fixme

"""
BikeShare Indigo Plugin
Author: DaveL17

The BikeShare Plugin takes JSON data provided by services and makes it available in Indigo. Users
create individual devices that represent bike dock stations. The plugin makes 100% of the data
available--however, some sharing services don't currently populate 100% of the fields that the
system provides. Any service that uses the "Station Bean List" format should be compatible with
this plugin. If there are stations that support this format which are not included in this plugin,
please feel free to post to the BikeShare Plugin forum on the Indigo community forums.
"""

# =================================== TO DO ===================================
# TODO - Move system choice from plugin config to device (then users can manage multiple systems).
# TODO - What happens when a system goes away?
# TODO - It looks like you have to restart the plugin when the service is changed in order for the
#        new service to be picked up.

# ================================== IMPORTS ==================================

# Built-in modules
import datetime as dt
import logging
import csv

# Third-party modules
try:
    import indigo  # noqa
#     import pydevd
    import requests
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
__version__   = '2022.0.1'


# =============================================================================
class Plugin(indigo.PluginBase):
    """
    Standard Indigo Plugin Class

    :param indigo.PluginBase:
    """
    def __init__(self, plugin_id="", plugin_display_name="", plugin_version="", plugin_prefs=None):
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
        log_format = '%(asctime)s.%(msecs)03d\t%(levelname)-10s\t%(name)s.%(funcName)-28s %(msg)s'
        self.plugin_file_handler.setFormatter(
            logging.Formatter(log_format, datefmt='%Y-%m-%d %H:%M:%S')
        )
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
        # Log pluginEnvironment information when plugin is first started
        self.fogbert.pluginEnvironment()

        # ============================= Remote Debugging ==============================
        # try:
        #     pydevd.settrace(
        #         'localhost',
        #         port=5678,
        #         stdoutToServer=True,
        #         stderrToServer=True,
        #         suspend=False
        #     )
        # except:
        #     pass

        self.plugin_is_initializing = False

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
    def closedPrefsConfigUi(self, values_dict=None, user_cancelled=False):  # noqa
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
            indigo.server.log(
                f"Debugging on (Level: {DEBUG_LABELS[self.debug_level]} ({self.debug_level})"
            )

            # Plugin-specific actions
            self.download_interval = int(values_dict.get('downloadInterval', 15))
            self.logger.debug("Plugin prefs saved.")

        else:
            self.logger.debug("Plugin prefs cancelled.")

        return values_dict

    # =============================================================================
    def deviceStartComm(self, dev=None):  # noqa
        """
        Standard Indigo method when device comm is enabled

        :param indigo.Device dev:
        :return:
        """
        self.parse_bike_data(dev=dev)
        dev.updateStateOnServer('onOffState', value=False, uiValue="Enabled")

    # =============================================================================
    @staticmethod
    def deviceStopComm(dev=None):  # noqa
        """
        Standard Indigo method when device comm is disabled

        :param indigo.Device dev:
        :return:
        """
        dev.updateStateOnServer('onOffState', value=False, uiValue="Disabled")
        dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    # =============================================================================
    def getPrefsConfigUiValues(self):  # noqa
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
    def runConcurrentThread(self):  # noqa
        """
        Standard Indigo method that runs continuously (if present)
        """
        self.logger.debug(
            "runConcurrentThread initiated. Sleeping for 2 seconds to allow the Indigo Server to "
            "finish."
        )
        self.sleep(2)

        try:
            while True:
                if self.business_hours():
                    self.download_interval = int(self.pluginPrefs.get('downloadInterval', 900))
                    self.refresh_bike_data()
                    self.process_triggers()
                self.sleep(self.download_interval)

        except self.StopThread:
            self.logger.debug("Stopping concurrent thread.")

    # =============================================================================
    @staticmethod
    def sendDevicePing(dev_id=0, suppress_logging=False):  # noqa
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

        # Update system data
        self.get_bike_data()

    # =============================================================================
    def triggerStartProcessing(self, trigger):  # noqa
        """
        Standard Indigo Method for trigger enabled

        :param indigo.trigger trigger:
        :return:
        """
        self.master_trigger_dict[trigger.pluginProps['listOfStations']] = trigger.id

    # =============================================================================
    def triggerStopProcessing(self, trigger):  # noqa
        """
        Standard Indigo Method for trigger disabled

        :param indigo.trigger trigger:
        :return:
        """

    # =============================================================================
    # ============================ BikeShare Methods ==============================
    # =============================================================================
    def business_hours(self):
        """
        Test to see if current time is within plugin operation hours

        The business_hours() method tests to see if the current time is within the operation hours
        set within the plugin configuration dialog.  It returns True if it is within business hours,
        otherwise returns False.
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
        for dev in indigo.devices.itervalues("self"):
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
        for dev in indigo.devices.itervalues("self"):
            indigo.device.enable(dev, value=True)

    # =============================================================================
    def dump_bike_data(self):
        """
        Title Placeholder
        """
        debug_level = int(self.pluginPrefs.get('showDebugLevel', "30"))
        time_stamp  = dt.datetime.now().strftime(fmt="%Y-%m-%d %H.%M")
        log_path    = indigo.server.getLogsFolderPath()
        file_name   = (
            f"{log_path}/com.fogbert.indigoplugin.bikeShare/{time_stamp} BikeShare data.txt"
        )

        with open(file_name, 'w', encoding="utf-8") as out_file:
            out_file.write("BikeShare Plugin Data\n")
            out_file.write(f"{time_stamp}\n")
            out_file.write(f"{self.system_data}")

        self.indigo_log_handler.setLevel(20)
        self.logger.info(f"Data written to {file_name}")
        self.indigo_log_handler.setLevel(debug_level)

    # =============================================================================
    @staticmethod
    def generator_time(filter="", values_dict=None, type_id="", target_id=0):  # noqa
        """
        List of hours generator

        Creates a list of times for use in setting the desired time for weather forecast emails to
        be sent.

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

        The get_bike_data action reaches out to the bike share server and downloads the JSON needed
        data.

        :return dict self.system_data:
        """
        self.system_data = {}

        try:
            # Get the selected service from the plugin config dict.
            lang = self.pluginPrefs.get('language')
            auto_discovery_url = self.pluginPrefs.get('bike_system')
            self.logger.debug(f"Auto-discovery URL: {auto_discovery_url}")

            # Go and get the data from the bike sharing service.
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
    def get_system_list(self, filter="", type_id=0, values_dict=None, target_id=0):  # noqa
        """
        Title Placeholder

        :param str filter:
        :param int type_id:
        :param indigo.Dict values_dict:
        :param int target_id:
        :return:
        """
        # # Download the latest systems list from GitHub and create a pandas dataframe.
        # data_frame = pd.read_csv("https://raw.githubusercontent.com/NABSA/gbfs/master/systems.csv")
        #
        # # Make minor changes to the provided data for proper display.
        # data_frame['Name'] = [n.lstrip(" ") for n in data_frame['Name']]
        #
        # # Create a new field: Name (Location)
        # data_frame['Combined Name'] = data_frame['Name'] + " (" + data_frame['Location'] + ")"
        #
        # # Remove any leading spaces in URL values which Indigo doesn't like as a dropdown ID.
        # data_frame['Auto-Discovery URL'] = data_frame['Auto-Discovery URL'].str.replace(" ", "")
        #
        # # Create a list of tuples for dropdown menu.
        # services = zip(list(data_frame['Auto-Discovery URL']), list(data_frame['Combined Name']))
        #
        # # Convert iterator into list
        # list_li = list(services)

        # =============================================================================
        # download the data.
        with requests.get("https://raw.githubusercontent.com/NABSA/gbfs/master/systems.csv",
                          timeout=10) as response:
            csv_dict = csv.DictReader(response.content.decode('utf-8').splitlines())

        # convert the DictReader object to a list because DictReader objects are not subscriptable.
        new_dict = list(csv_dict)

        # construct the combined name for a dropdown list.
        for system in new_dict:
            system["Combined Name"] = system['Name'].lstrip(" ") + " (" + system['Location'] + ")"

        # convert iterator into list and collapse any spaces in the URL field.
        list_li = [(_["Auto-Discovery URL"].replace(" ", ""), _["Combined Name"]) for _ in new_dict]
        # =============================================================================

        # Percent-encode as much as possible.
        list_li = [(requests.utils.quote(k, safe="%:/"), v) for (k, v) in list_li]

        # Log the number of available systems.
        num_systems = len(list_li)

        self.logger.debug(f"{num_systems} bike sharing systems available.")

        return sorted(list_li, key=lambda tup: tup[1].lower())

    # =============================================================================
    def get_station_list(self, filter="", type_id=0, values_dict=None, target_id=0):  # noqa
        """
        Create a list of bike sharing stations for dropdown menus

        The get_station_list() method generates a sorted list of station names for use in device
        config dialogs.

        :param str filter:
        :param str type_id:
        :param int target_id:
        :param indigo.Dict values_dict:
        :return list:
        """
        station_information = self.system_data['station_information']['data']['stations']

        return sorted(
            [(key['station_id'], key['name']) for key
             in station_information], key=lambda x: x[-1]
        )

    # =============================================================================
    def parse_bike_data(self, dev=None):
        """
        Parse bike data for saving to custom device states

        The parse_bike_data() method takes the JSON data (contained within 'self.system_data'
        variable) and assigns values to relevant device states. In instances where the service
        provides a null string value, the plugin assigns the value of "Not provided." to alert the
        user to that fact.

        :param indigo.Device dev:
        :return:
        """
        states_list = []
        station_id = dev.pluginProps['stationName']

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

                    # Sometimes the sharing service clock is ahead of the Indigo server clock.
                    # Since the result can't be negative by definition, let's make it zero and
                    # call it a day.
                    time_diff = max(diff_time.total_seconds(), 0)
                    diff = dt.timedelta(seconds=time_diff)
                    diff_time_str = f"{diff}"

                    states_list.append(
                        {'key': 'last_reported', 'value': station.get(last_report_human, 'Unknown')}
                    )
                    states_list.append(
                        {'key': 'dataAge', 'value': station.get(diff_time_str, 'Unknown')}
                    )

                except Exception:  # noqa
                    self.logger.exception()
                    states_list.append(
                        {'key': 'dataAge', 'value': "Unknown", 'uiValue': "Unknown"}
                    )

        dev.updateStatesOnServer(states_list)

    # =============================================================================
    def process_triggers(self):
        """
        Process plugin triggers

        The process_triggers method will examine the statusValue state of each device, determine
        whether there is a trigger for any stations reported as not in service, and fire the
        corresponding trigger.

        :return:
        """
        try:
            for dev in indigo.devices.itervalues(filter='self'):

                station_name   = dev.states['stationName']
                station_status = dev.states['statusValue']
                if station_name in self.master_trigger_dict:

                    # This relies on all services reporting status value of 'In Service' when
                    # things are normal.
                    if station_status != 'In Service':
                        trigger_id = self.master_trigger_dict[station_name]

                        if indigo.triggers[trigger_id].enabled:
                            indigo.trigger.execute(trigger_id)
                            indigo.server.log(f"{dev.name} location is not in service.")

        except KeyError:
            pass

    # =============================================================================
    def refreshBikeAction(self, values_dict=None):  # noqa
        """
        The refreshBikeAction() method has been deprecated.

        Supports legacy installations.

        :param indigo.Dict values_dict:
        :return:
        """
        self.refresh_bike_action(values_dict=values_dict)

    # =============================================================================
    def refresh_bike_action(self, values_dict=None):  # noqa
        """
        Refresh bike data based on call from Indigo Action item

        The refresh_bike_action method is used to trigger a data refresh cycle (get it?) when
        requested by the user through an Indigo action.

        :param indigo.Dict values_dict:
        :return:
        """
        self.refresh_bike_data()

    # =============================================================================
    def refresh_bike_data(self):
        """
        Refresh bike data based on a call from Indigo Plugin menu

        This method refreshes bike data for all devices based on a plugin menu call. Note that this
        method does not honor the "business hours" limitation, as it is assumed that--since the
        user has requested an update--they are interested in getting one regardless of the time of
        day.
        """

        try:
            states_list = []

            self.get_bike_data()

            for dev in indigo.devices.itervalues("self"):
                dev.stateListOrDisplayStateIdChanged()

                if not dev.configured:
                    indigo.server.log(
                        f"[{dev.name}] Skipping device because it is not fully configured."
                    )
                    self.sleep(60)

                elif dev.enabled:
                    try:
                        if self.system_data:
                            self.parse_bike_data(dev)

                            if dev.states['is_renting'] == 1:
                                num_bikes = dev.states['num_bikes_available']
                                states_list.append(
                                    {'key': 'onOffState', 'value': True, 'uiValue': f"{num_bikes}"}
                                )
                                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
                            else:
                                states_list.append(
                                    {'key': 'onOffState', 'value': False, 'uiValue': "Not Renting"}
                                )
                                dev.updateStateImageOnServer(indigo.kStateImageSel.Error)

                        else:
                            dev.setErrorStateOnServer("No Comm")
                            self.logger.debug("Comm error. Sleeping until next scheduled poll.")
                            dev.updateStateImageOnServer(indigo.kStateImageSel.Error)

                    except Exception:  # noqa
                        states_list.append(
                            {
                                'key': 'onOffState',
                                'value': False,
                                'uiValue': f"{dev.states['num_bikes_available']}"
                            },
                        )
                        dev.setErrorStateOnServer("Error")
                        self.logger.exception()
                        self.logger.debug("Sleeping until next scheduled poll.")
                        dev.updateStateImageOnServer(indigo.kStateImageSel.Error)

                    states_list.append(
                        {
                            'key': 'businessHours',
                            'value': self.open_for_business,
                            'uiValue': self.open_for_business
                        }
                    )
                    self.logger.info(f"[{dev.name}] Data refreshed.")
                    dev.updateStatesOnServer(states_list)

        except Exception:  # noqa
            self.logger.exception(
                "There was a problem refreshing the data. Will try on next cycle."
            )
