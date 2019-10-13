#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

"""
Bike Share Indigo Plugin
Author: DaveL17
Update Checker by: berkinet (with additional features by Travis Cook)

The Bike Share Plugin takes JSON data provided by services and makes it
available in Indigo. Users create individual devices that represent
bike dock stations. The plugin makes 100% of the data available--
however, some sharing services don't currently populate 100% of the
fields that the system provides. Any service that uses the "Station
Bean List" format should be compatible with this plugin. If there are
stations that support this format which are not included in this plugin,
please feel free to post to the Bike Share Plugin forum on the Indigo
community forums.
"""

# =================================== TO DO ===================================

# TODO: Move system choice from plugin config to device (then users can manage
#       multiple systems).
# TODO: What happens when a system goes away?

# ================================== IMPORTS ==================================

# Built-in modules
import datetime as dt
import logging
import pandas as pd
import requests
import sys

# Third-party modules
try:
    import indigo
except ImportError:
    pass

try:
    import pydevd
except ImportError:
    pass

# My modules
import DLFramework.DLFramework as Dave

# =================================== HEADER ==================================

__author__    = Dave.__author__
__copyright__ = Dave.__copyright__
__license__   = Dave.__license__
__build__     = Dave.__build__
__title__     = 'Bike Share Plugin for Indigo'
__version__   = '2.0.03'

# =============================================================================

kDefaultPluginPrefs = {
    u'bikeSharingService' : "",
    u'downloadInterval'   : 895,    # Frequency of updates.
    u'showDebugLevel'     : "30",   # Default logging level
    }


class Plugin(indigo.PluginBase):
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        self.plugin_is_initializing = True
        self.plugin_is_shutting_down = False
        self.system_data = {}

        self.downloadInterval = int(self.pluginPrefs.get('downloadInterval', 900))
        self.master_trigger_dict = {}

        # ================================= Debugging ==================================
        self.plugin_file_handler.setFormatter(logging.Formatter('%(asctime)s.%(msecs)03d\t%(levelname)-10s\t%(name)s.%(funcName)-28s %(msg)s', datefmt='%Y-%m-%d %H:%M:%S'))
        self.debugLevel = int(self.pluginPrefs.get('showDebugLevel', "30"))

        # Convert debugLevel scale to new scale
        try:
            self.debugLevel = int(self.pluginPrefs.get('showDebugLevel', 30))
            if self.debugLevel < 4:
                self.debugLevel *= 10
        except ValueError:
            self.debugLevel = 30

        self.indigo_log_handler.setLevel(self.debugLevel)

        # ====================== Initialize DLFramework =======================

        self.Fogbert = Dave.Fogbert(self)

        # Log pluginEnvironment information when plugin is first started
        self.Fogbert.pluginEnvironment()

        # try:
        #     pydevd.settrace('localhost', port=5678, stdoutToServer=True, stderrToServer=True, suspend=False)
        # except:
        #     pass

        # Update system data
        self.get_bike_data()

        self.plugin_is_initializing = False

    def __del__(self):
        indigo.PluginBase.__del__(self)

    # =============================================================================
    # =============================== Indigo Methods ===============================
    # =============================================================================
    def actionControlDevice(self, actionId):

        indigo.server.log(u"\n{0}".format(actionId))

    # =============================================================================
    def closedPrefsConfigUi(self, valuesDict, userCancelled):

        if not userCancelled:

            # Ensure that self.pluginPrefs includes any recent changes.
            for k in valuesDict:
                self.pluginPrefs[k] = valuesDict[k]

            self.debugLevel = int(valuesDict['showDebugLevel'])
            self.indigo_log_handler.setLevel(self.debugLevel)

            self.logger.debug(u"User prefs saved.")

        else:

            self.logger.debug(u"User prefs cancelled.")

    # =============================================================================
    def deviceStartComm(self, dev):

        self.parse_bike_data(dev)
        dev.updateStateOnServer('onOffState', value=False, uiValue=u"Enabled")

    # =============================================================================
    def deviceStopComm(self, dev):

        dev.updateStateOnServer('onOffState', value=False, uiValue=u"Disabled")
        dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    # =============================================================================
    def didDeviceCommPropertyChange(self, origDev, newDev):

        # if origDev.pluginProps['address'] != newDev.pluginProps['address']:
        #     return True

        return False

    # =============================================================================
    def getPrefsConfigUiValues(self):

        plugin_prefs = self.pluginPrefs

        # Default choices for dynamic menus
        if plugin_prefs.get('start_time', "") == "":
            plugin_prefs['start_time'] = u"00:00"

        if plugin_prefs.get('stop_time', "") == "":
            plugin_prefs['stop_time'] = u"24:00"

        if int(plugin_prefs.get('showDebugLevel', "30")) < 4:
            plugin_prefs['showDebugLevel'] = '30'

        return plugin_prefs

    # =============================================================================
    def runConcurrentThread(self):

        self.logger.debug(u"runConcurrentThread initiated. Sleeping for 5 seconds to allow the Indigo Server to finish.")
        self.sleep(5)

        try:
            while True:
                if self.business_hours():
                    self.downloadInterval = int(self.pluginPrefs.get('downloadInterval', 900))
                    self.refresh_bike_data()
                    self.process_triggers()
                self.sleep(self.downloadInterval)

        except self.StopThread:
            self.logger.debug(u"Stopping concurrent thread.")

    # =============================================================================
    def sendDevicePing(self, dev_id=0, suppress_logging=False):

        indigo.server.log(u"Bikeshare Plugin devices do not support the ping function.")
        return {'result': 'Failure'}

    # =============================================================================
    def shutdown(self):

        self.plugin_is_shutting_down = True

    # =============================================================================
    def startup(self):

        # =========================== Audit Indigo Version ============================
        self.Fogbert.audit_server_version(min_ver=7)

    # =============================================================================
    def triggerStartProcessing(self, trigger):

        self.master_trigger_dict[trigger.pluginProps['listOfStations']] = trigger.id

    # =============================================================================
    def triggerStopProcessing(self, trigger):

        pass

    # =============================================================================
    def validatePrefsConfigUi(self, valuesDict):

        return True, valuesDict

    # =============================================================================
    def validateDeviceConfigUi(self, valuesDict, typeID, devId):

        return True, valuesDict

    # =============================================================================
    # ============================ BikeShare Methods ==============================
    # =============================================================================
    def business_hours(self):
        """
        Test to see if current time is within plugin operation hours

        The business_hours() method tests to see if the current time is within the
        operation hours set within the plugin configuration dialog.  It returns
        True if it is within business hours, otherwise returns False.

        ---

        :return:
        """
        now = dt.datetime.now()
        start_updating = self.pluginPrefs.get('start_time', "00:00")
        stop_updating  = self.pluginPrefs.get('stop_time', "24:00")

        # If there is no time limit boundary.
        if start_updating == "00:00" and stop_updating == "24:00":
            return True

        # Otherwise, let's check to see if we're open for business.
        if stop_updating == "24:00":
            stop_updating = "23:59"

        start_time = now.replace(hour=int(start_updating[0:2]), minute=int(start_updating[3:5]))
        stop_time  = now.replace(hour=int(stop_updating[0:2]), minute=int(start_updating[3:5]))

        if start_time < now < stop_time:
            return True
        else:
            self.logger.info(u"Closed for business.")
            return False

    # =============================================================================
    def commsKillAll(self):
        """
        The commsKillAll() method has been deprecated.

        Supports legacy installations.

        -----

        """
        self.comms_kill_all()

    # =============================================================================
    def comms_kill_all(self):
        """
        Disable all plugin devices in Indigo

        comms_kill_all() sets the enabled status of all plugin devices to false.

        -----

        """

        for dev in indigo.devices.itervalues("self"):

            try:
                indigo.device.enable(dev, value=False)

            except Exception as error:
                self.logger.debug(u"Exception when trying to kill all comms. Line {1}: Error: {0}".format(sys.exc_traceback.tb_lineno, error))

    # =============================================================================
    def commsUnkillAll(self):
        """
        The commsUnkillAll() method has been deprecated.

        Supports legacy installations.

        -----

        """
        self.comms_unkill_all()

    # =============================================================================
    def comms_unkill_all(self):
        """
        Enable all plugin devices in Indigo

        comms_unkill_all() sets the enabled status of all plugin devices to true.

        -----

        """

        for dev in indigo.devices.itervalues("self"):

            try:
                indigo.device.enable(dev, value=True)

            except Exception as error:
                self.logger.debug(u"Exception when trying to unkill all comms. Line: {1} Error: {0}".format(sys.exc_traceback.tb_lineno, error))

    # =============================================================================
    def dump_bike_data(self):
        """

        -----

        :return:
        """

        debug_level = int(self.pluginPrefs.get('showDebugLevel', "30"))
        time_stamp        = dt.datetime.now().strftime("%Y-%m-%d %H.%M")
        file_name         = u"{0}/com.fogbert.indigoplugin.bikeShare/{1} Bike Share data.txt".format(indigo.server.getLogsFolderPath(), time_stamp)

        with open(file_name, 'w') as out_file:
            out_file.write(u"Bike Share Plugin Data\n")
            out_file.write(u"{0}\n".format(time_stamp))
            out_file.write(u"{0}".format(self.system_data))

        self.indigo_log_handler.setLevel(20)
        self.logger.info(u"Data written to {0}".format(file_name))
        self.indigo_log_handler.setLevel(debug_level)

    # =============================================================================
    def generator_time(self, filter="", valuesDict=None, typeId="", targetId=0):
        """
        List of hours generator

        Creates a list of times for use in setting the desired time for weather
        forecast emails to be sent.

        -----
        :param str filter:
        :param indigo.Dict valuesDict:
        :param str typeId:
        :param int targetId:
        """

        return [(u"{0:02.0f}:00".format(hour), u"{0:02.0f}:00".format(hour)) for hour in range(0, 25)]

    # =============================================================================
    def get_bike_data(self):
        """
        Download the necessary JSON data from the bike sharing service

        The get_bike_data action reaches out to the bike share server and downloads the
        JSON needed data.

        -----

        :return dict self.system_data:
        """
        self.system_data = {}

        try:
            # Get the selected service from the plugin config dict.
            # =================================================================
            lang = self.pluginPrefs.get('language')
            auto_discovery_url = self.pluginPrefs.get('bike_system')
            self.logger.debug(u"Auto-discovery URL: {0}".format(auto_discovery_url))

            # Go and get the data from the bike sharing service.
            # =================================================================
            r = requests.get(auto_discovery_url, timeout=15)
            for feed in r.json()['data'][lang]['feeds']:
                self.system_data[feed['name']] = requests.get(feed['url']).json()
            return self.system_data

        # ======================== Communication Error Handling ========================
        except requests.exceptions.ConnectionError:
            self.logger.critical(u"Connection Error. Will attempt again later.")

        except Exception as error:
            self.logger.critical(u"Plugin exception. Line: {0} Error: {1}.".format(sys.exc_traceback.tb_lineno, error))

    # =============================================================================
    def get_system_list(self, filter="", typeId=0, valuesDict=None, targetId=0):
        """

        :param filter:
        :param typeId:
        :param valuesDict:
        :param targetId:
        :return:
        """
        # Download the latest systems list from GitHub and create a pandas dataframe.
        df = pd.read_csv("https://raw.githubusercontent.com/NABSA/gbfs/master/systems.csv")

        # Make minor changes to the provided data for proper display.
        df['Name'] = [n.lstrip(" ") for n in df['Name']]

        # Create a new field: Name (Location)
        df['Combined Name'] = df['Name'] + " (" + df['Location'] + ")"

        # Create a list of tuples for dropdown menu.
        li = zip(list(df['Auto-Discovery URL']), list(df['Combined Name']))

        # Log the number of available systems.
        self.logger.debug(u"{0} bike sharing systems available.".format(len(li)))

        return sorted(li, key=lambda tup: tup[1].lower())

    # =============================================================================
    def get_station_list(self, filter="", typeId=0, valuesDict=None, targetId=0):
        """
        Create a list of bike sharing stations for dropdown menus

        The get_station_list() method generates a sorted list of station names for use in
        device config dialogs.

        -----

        :param str filter:
        :param str typeId:
        :param int targetId:
        :param indigo.Dict valuesDict:
        :return list:

        """
        station_information = self.system_data['station_information']['data']['stations']

        return sorted([(key['station_id'], key['name']) for key in station_information], key=lambda x: x[-1])

    # =============================================================================
    def parse_bike_data(self, dev):
        """
        Parse bike data for saving to custom device states

        The parse_bike_data() method takes the JSON data (contained within
        'self.system_data' variable) and assigns values to relevant device states. In
        instances where the service provides a null string value, the plugin assigns
        the value of "Not provided." to alert the user to that fact.

        -----

        :param indigo.device dev:

        """

        states_list = []
        station_id = dev.pluginProps['stationName']

        # Station information
        for station in self.system_data['station_information']['data']['stations']:
            if station['station_id'] == station_id:
                for key in ('capacity', 'lat', 'lon', 'name',):
                    states_list.append({'key': key, 'value': station[key]})

        # Station Status
        for station in self.system_data['station_status']['data']['stations']:
            if station['station_id'] == station_id:
                for key in ('is_renting', 'is_returning', 'num_bikes_available', 'num_bikes_disabled',
                            'num_docks_available', 'num_docks_disabled', 'num_ebikes_available',):

                    # Coerce select entries to bool
                    for _ in ('is_renting', 'is_returning'):
                        if station[_] == 1:
                            station[_] = True
                        else:
                            station[_] = False

                    states_list.append({'key': key, 'value': station[key]})

                # ================================== Data Age ==================================
                try:
                    last_report = int(station['last_reported'])
                    last_report_human = dt.datetime.fromtimestamp(last_report).strftime("%Y-%m-%d %H:%M:%S")

                    diff_time = dt.datetime.now() - dt.datetime.fromtimestamp(last_report)

                    # Sometimes the sharing service clock is ahead of the Indigo server clock. Since the
                    # result can't be negative by definition, let's make it zero and call it a day.
                    # =========================================================
                    if diff_time.total_seconds() < 0:
                        diff_time = 0
                    diff_time_str = u"{0}".format(dt.timedelta(seconds=diff_time.total_seconds()))

                    states_list.append({'key': 'last_reported', 'value': last_report_human})
                    states_list.append({'key': 'dataAge', 'value': diff_time_str, 'uiValue': diff_time_str})

                except Exception as e:
                    self.logger.critical(u"{0}".format(e))
                    states_list.append({'key': 'dataAge', 'value': u"Unknown", 'uiValue': u"Unknown"})

        dev.updateStatesOnServer(states_list)
        return

    # =============================================================================
    def process_triggers(self):
        """
        Process plugin triggers

        The process_triggers method will examine the statusValue state of each
        device, determine whether there is a trigger for any stations reported as not
        in service, and fire the corresponding trigger.

        -----

        """

        try:
            for dev in indigo.devices.itervalues(filter='self'):

                station_name   = dev.states['stationName']
                station_status = dev.states['statusValue']
                if station_name in self.master_trigger_dict.keys():

                    if station_status != 'In Service':  # This relies on all services reporting status value of 'In Service' when things are normal.
                        trigger_id = self.master_trigger_dict[station_name]

                        if indigo.triggers[trigger_id].enabled:
                            indigo.trigger.execute(trigger_id)
                            indigo.server.log(u"{0} location is not in service.".format(dev.name))

        except KeyError:
            pass

    # =============================================================================
    def refreshBikeAction(self, valuesDict):
        """
        The refreshBikeAction() method has been deprecated.

        Supports legacy installations.

        -----

        :param valuesDict:
        """

        self.refresh_bike_action(valuesDict)

    # =============================================================================
    def refresh_bike_action(self, valuesDict):
        """
        Refresh bike data based on call from Indigo Action item

        The refresh_bike_action method is used to trigger a data refresh cycle (get it?)
        when requested by the user through an Indigo action.

        -----

        :param indigo.dict valuesDict:

        """
        self.refresh_bike_data()

    # =============================================================================
    def refresh_bike_data(self):
        """
        Refresh bike data based on a call from Indigo Plugin menu

        This method refreshes bike data for all devices based on a plugin menu call.
        Note that this method does not honor the business hours limitation, as it is
        assumed that--since the user has requested an update--they are interested in
        getting one regardless of the time of day.
        -----

        """

        try:
            states_list = []

            self.get_bike_data()

            for dev in indigo.devices.itervalues("self"):
                dev.stateListOrDisplayStateIdChanged()

                if not dev.configured:
                    indigo.server.log(u"[{0}] Skipping device because it is not fully configured.".format(dev.name))
                    self.sleep(60)

                elif dev.enabled:

                    try:
                        if self.system_data != {}:
                            self.parse_bike_data(dev)

                            if dev.states['is_renting'] == 1:
                                states_list.append({'key': 'onOffState', 'value': True, 'uiValue': u"{0}".format(dev.states['num_bikes_available'])})
                                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
                            else:
                                states_list.append({'key': 'onOffState', 'value': False, 'uiValue': u"Not Renting"})
                                dev.updateStateImageOnServer(indigo.kStateImageSel.Error)

                        elif self.system_data == {}:
                            dev.setErrorStateOnServer(u"No Comm")
                            self.logger.debug(u"Comm error. Sleeping until next scheduled poll.")
                            dev.updateStateImageOnServer(indigo.kStateImageSel.Error)

                    except Exception as error:
                        states_list.append({'key': 'onOffState', 'value': False, 'uiValue': u"{0}".format(dev.states['num_bikes_available'])})
                        dev.setErrorStateOnServer(u"Error")
                        self.logger.debug(u"Exception Line: {0} Error: {1}.".format(sys.exc_traceback.tb_lineno, error))
                        self.logger.debug(u"Sleeping until next scheduled poll.")
                        dev.updateStateImageOnServer(indigo.kStateImageSel.Error)

                    self.logger.info(u"[{0}] Data refreshed.".format(dev.name))
                    dev.updateStatesOnServer(states_list)

        except Exception as error:
            self.logger.warning(u"There was a problem refreshing the data.  Will try on next cycle.")
            self.logger.debug(u"Exception Line: {0} Error: {1}.".format(sys.exc_traceback.tb_lineno, error))
    # =============================================================================
