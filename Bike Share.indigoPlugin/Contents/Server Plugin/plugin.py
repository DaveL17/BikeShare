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

# TODO: add feature to only check during hours

# ================================== IMPORTS ==================================

# Built-in modules
import datetime as dt
import dateutil.parser as dup
import logging
import simplejson
import socket
import sys
import urllib2

# Third-party modules
from DLFramework import indigoPluginUpdateChecker
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
__title__     = 'Bike Share Plugin for Indigo Home Control'
__version__   = '1.1.04'

# =============================================================================

kDefaultPluginPrefs = {
    u'bikeSharingService': "",
    u'downloadInterval'    : 900,    # Frequency of updates.
    u'showDebugInfo'       : False,  # Verbose debug logging?
    u'showDebugLevel'      : "30",   # Default logging level
    }


class Plugin(indigo.PluginBase):
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        self.pluginIsInitializing = True
        self.pluginIsShuttingDown = False

        self.downloadInterval  = int(self.pluginPrefs.get('downloadInterval', 900))
        self.masterTriggerDict = {}

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

        self.pluginIsInitializing = False

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
            if self.debugLevel != int(valuesDict['showDebugLevel']):
                self.indigo_log_handler.setLevel(int(valuesDict['showDebugLevel']))

    # =============================================================================
    def deviceStartComm(self, dev):

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

        try:
            if int(plugin_prefs.get('showDebugLevel', "30")) < 4:
                plugin_prefs['showDebugLevel'] = '30'

        except ValueError:
            plugin_prefs['showDebugLevel'] = '30'

        return plugin_prefs

    # =============================================================================
    def runConcurrentThread(self):

        self.logger.debug(u"runConcurrentThread initiated. Sleeping for 5 seconds to allow the Indigo Server to finish.")
        self.sleep(5)

        try:
            while True:
                self.downloadInterval = int(self.pluginPrefs.get('downloadInterval', 900))
                self.refresh_bike_data()
                self.process_triggers()
                self.sleep(self.downloadInterval)

        except self.StopThread:
            self.logger.debug(u"Stopping concurrent thread.")

    # =============================================================================
    def shutdown(self):

        self.pluginIsShuttingDown = True

    # =============================================================================
    def startup(self):

        pass

    # =============================================================================
    def triggerStartProcessing(self, trigger):

        self.masterTriggerDict[trigger.pluginProps['listOfStations']] = trigger.id

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
    # ============================= BikeShare Methods ==============================
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

        parsed_simplejson = self.get_bike_data()

        with open(file_name, 'w') as out_file:
            out_file.write(u"Bike Share Plugin Data\n")
            out_file.write(u"{0}\n".format(time_stamp))
            out_file.write(u"{0}".format(parsed_simplejson))

        self.indigo_log_handler.setLevel(20)
        self.logger.info(u"Data written to {0}".format(file_name))
        self.indigo_log_handler.setLevel(debug_level)

    # =============================================================================
    def get_bike_data(self):
        """
        Download the necessary JSON data from the bike sharing service

        The get_bike_data action reaches out to the bike share server and downloads the
        JSON needed data.

        -----

        :return dict parsed_simplejson:
        """

        try:
            # Get the selected service from the plugin config dict.
            # =================================================================
            url = self.pluginPrefs.get('bikeSharingService')

            # Go and get the data from the bike sharing service.
            # =================================================================
            socket.setdefaulttimeout(15)
            f = urllib2.urlopen(url)
            simplejson_string = f.read()
            parsed_simplejson = simplejson.loads(simplejson_string)
            f.close()

        # ======================== Communication Error Handling ========================
        except urllib2.HTTPError as error:
            parsed_simplejson = {}
            self.logger.warning(u"Unable to contact sharing service. Will continue to try.")
            self.logger.debug(u"HTTPError - {0}".format(error))

        except urllib2.URLError as error:
            parsed_simplejson = {}
            self.logger.warning(u"Unable to contact sharing service. Will continue to try.")
            self.logger.debug(u"URLError - {0}".format(error))

        except Exception as error:
            parsed_simplejson = {}
            if "invalid literal for int() with base 16: ''" in error:
                self.logger.warning(u"Congratulations! You have discovered a somewhat obscure bug in Python2.5. "
                                    u"This problem should clear up on its own, but may come back periodically.")

            else:
                self.logger.critical(u"Plugin exception. Line: {0} Error: {1}.".format(sys.exc_traceback.tb_lineno, error))

        return parsed_simplejson

    # =============================================================================
    def get_station_list(self, filter="", typeId=0, valuesDict=None, targetId=0):
        """
        Create a list of bike sharing stations for dropdown menus

        The get_station_list() method generates a sorted list of station names for use in
        device config dialogs.

        -----

        :param str filter:
        :param str typeId
        :param int targetId:
        :param indigo.Dict valuesDict:
        :return list:

        """
        parsed_simplejson = self.get_bike_data()

        return sorted([dock['stationName'] for dock in parsed_simplejson['stationBeanList']])

    # =============================================================================
    def parse_bike_data(self, dev, parsed_simplejson):
        """
        Parse bike data for saving to custom device states

        The parse_bike_data() method takes the JSON data (contained within
        'parsed_simplejson' variable) and assigns values to relevant device states. In
        instances where the service provides a null string value, the plugin assigns
        the value of "Not provided." to alert the user to that fact.

        -----

        :param indigo.device dev:
        :param dict parsed_simplejson:

        """

        states_list = []
        states_list.append({'key': 'executionTime', 'value': parsed_simplejson['executionTime']})

        for dock in parsed_simplejson['stationBeanList']:
            if dev.pluginProps['stationName'] == dock['stationName']:

                for key in (
                        'altitude',
                        'availableBikes',
                        'availableDocks',
                        'city',
                        'landMark',
                        'lastCommunicationTime',
                        'latitude',
                        'location',
                        'longitude',
                        'postalCode',
                        # 'renting',
                        'stAddress1',
                        'stAddress2',
                        'stationName',
                        'statusKey',
                        'statusValue',
                        'totalDocks',
                ):

                    if key not in dock.keys() or dock[key] == "":
                        dock[key] = u"Not provided"
                    states_list.append({'key': key, 'value': dock[key], 'uiValue': u"{0}".format(dock[key])})

                if 'is_renting' not in dock.keys() or dock['is_renting'] == "":
                    dock['is_renting'] = u"Not provided"
                states_list.append({'key': 'isRenting', 'value': dock['is_renting'], 'uiValue': u"{0}".format(dock['is_renting'])})

                if 'id' not in dock.keys() or dock['id'] == "":
                    dock['id'] = u"Not provided"
                states_list.append({'key': 'stationID', 'value': dock['id'], 'uiValue': u"{0}".format(dock['id'])})

                # Convert ['Test Station'] string value to boolean. Assumes False.
                if dock['testStation']:
                    states_list.append({'key': 'testStation', 'value': True})
                else:
                    states_list.append({'key': 'testStation', 'value': False})

                # ================================== Data Age ==================================
                try:

                    diff_time = dt.datetime.now() - dup.parse(dock['lastCommunicationTime'])

                    # Sometimes the sharing service clock is ahead of the Indigo server clock. Since the
                    # result can't be negative by definition, let's make it zero and call it a day.
                    # =========================================================
                    if diff_time.total_seconds() < 0:
                        diff_time = 0
                    diff_time_str = u"{0}".format(dt.timedelta(seconds=diff_time.total_seconds()))
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
                if station_name in self.masterTriggerDict.keys():

                    if station_status != 'In Service':  # This relies on all services reporting status value of 'In Service' when things are normal.
                        trigger_id = self.masterTriggerDict[station_name]

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
        Note that the code in this method is generally the same as
        runConcurrentThread(). Changes reflected there may need to be added here as
        well.

        -----

        """

        try:
            parsed_simplejson = self.get_bike_data()
            states_list       = []

            for dev in indigo.devices.itervalues("self"):
                dev.stateListOrDisplayStateIdChanged()

                if not dev.configured:
                    indigo.server.log(u"[{0}] Skipping device because it is not fully configured.".format(dev.name))
                    self.sleep(60)

                elif dev.enabled:

                    try:
                        if parsed_simplejson != {}:
                            self.parse_bike_data(dev, parsed_simplejson)

                            if dev.states['statusValue'] == 'In Service':
                                states_list.append({'key': 'onOffState', 'value': False, 'uiValue': u"{0}".format(dev.states['availableBikes'])})
                                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
                            else:
                                states_list.append({'key': 'onOffState', 'value': False, 'uiValue': u"{0}".format(dev.states['statusValue'])})
                                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                        elif parsed_simplejson == {}:
                            dev.setErrorStateOnServer(u"No Comm")
                            self.logger.debug(u"Comm error. Sleeping until next scheduled poll.")
                            dev.updateStateImageOnServer(indigo.kStateImageSel.Error)

                    except Exception as error:
                        states_list.append({'key': 'onOffState', 'value': False, 'uiValue': u"{0}".format(dev.states['availableBikes'])})
                        dev.setErrorStateOnServer(u"Error")
                        self.logger.debug(u"Exception Line: {0} Error: {1}.".format(sys.exc_traceback.tb_lineno, error))
                        self.logger.debug(u"Sleeping until next scheduled poll.")
                        dev.updateStateImageOnServer(indigo.kStateImageSel.Error)

                dev.updateStatesOnServer(states_list)

            self.logger.info(u"Data refreshed.")
            parsed_simplejson = {}

        except Exception as error:
            self.logger.warning(u"There was a problem refreshing the data.  Will try on next cycle.")
            self.logger.debug(u"Exception Line: {0} Error: {1}.".format(sys.exc_traceback.tb_lineno, error))
    # =============================================================================
