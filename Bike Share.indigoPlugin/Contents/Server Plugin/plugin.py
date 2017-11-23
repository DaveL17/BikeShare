#!/usr/bin/env python2.6
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

# TODO: allow each device to update independently.

# ================================== IMPORTS ==================================

# Built-in modules
import datetime as dt
import simplejson
import socket
import sys
import time
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
__version__   = '1.0.06'

# =============================================================================

kDefaultPluginPrefs = {
    u'bikeSharingService': "",
    u'downloadInterval'    : 900,    # Frequency of updates.
    u'showDebugInfo'       : False,  # Verbose debug logging?
    u'showDebugLevel'      : "1",    # Low (1), Medium (2) or High (3) debug output.
    u'updaterEmail'        : "",     # Email to notify of plugin updates.
    u'updaterEmailsEnabled': False   # Notification of plugin updates wanted.
    }


class Plugin(indigo.PluginBase):
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        self.debug                = self.pluginPrefs.get('showDebugInfo', False)
        self.debugLevel           = int(self.pluginPrefs.get('showDebugLevel', "1"))
        self.downloadInterval     = int(self.pluginPrefs.get('downloadInterval', 900))
        self.masterTriggerDict    = {}
        self.updater              = indigoPluginUpdateChecker.updateChecker(self, "http://davel17.github.io/BikeShare/bikeShare_version.html")
        self.updaterEmail         = self.pluginPrefs.get('updaterEmail', "")
        self.updaterEmailsEnabled = self.pluginPrefs.get(u"updaterEmailsEnabled", "false")

        # ====================== Initialize DLFramework =======================

        self.Fogbert = Dave.Fogbert(self)

        # Log pluginEnvironment information when plugin is first started
        self.Fogbert.pluginEnvironment()

        # Convert old debugLevel scale (low, medium, high) to new scale (1, 2, 3).
        if not 0 < self.pluginPrefs.get('showDebugLevel', 1) <= 3:
            self.pluginPrefs['showDebugLevel'] = self.Fogbert.convertDebugLevel(self.pluginPrefs['showDebugLevel'])

        # =====================================================================

        if self.pluginPrefs['showDebugLevel'] >= 3:
            self.debugLog(u"======================================================================")
            self.debugLog(u"Caution! Debug set to high. This results in a lot of output to the log")
            self.debugLog(u"======================================================================")
            self.sleep(3)
        else:
            self.debugLog(u"Debug level set to: {0}".format(self.pluginPrefs.get('showDebugLevel', 1)))

        if self.pluginPrefs['showDebugInfo'] and self.pluginPrefs['showDebugLevel'] >= 3:
            self.debugLog(u"{0}".format(pluginPrefs))
        else:
            self.debugLog(u"Plugin preferences suppressed. Set debug level to [High] to write them to the log.")

        # try:
        #     pydevd.settrace('localhost', port=5678, stdoutToServer=True, stderrToServer=True, suspend=False)
        # except:
        #     pass

    def __del__(self):
        indigo.PluginBase.__del__(self)

    def startup(self):
        self.debugLog(u"Startup called.")

        try:
            self.updater.checkVersionPoll()
        except Exception as error:
            self.errorLog(u"Update checker error: Line: {0} Error: {1}.".format(sys.exc_traceback.tb_lineno, error))

    def shutdown(self):
        self.debugLog(u"Shutdown() method called.")

    def deviceStartComm(self, dev):
        self.debugLog(u"Starting Bike Share device: {0}".format(dev.name))
        dev.updateStateOnServer('onOffState', value=False, uiValue=u"Enabled")

    def deviceStopComm(self, dev):
        self.debugLog(u"Stopping Bike Share device: {0}".format(dev.name))
        dev.updateStateOnServer('onOffState', value=False, uiValue=u"Disabled")
        dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    def didDeviceCommPropertyChange(self, origDev, newDev):
        """This method tells Indigo whether it should call deviceStopComm/deviceStartComm
        after the device's props have been updated. We don't need to stop/start the
        device unless comm-related settings change."""
        #        if origDev.pluginProps['address'] != newDev.pluginProps['address']:
        #            return True
        return False

    def validatePrefsConfigUi(self, valuesDict):
        """The validatePrefsConfigUi method is called
        when the user closes the plugin configuration dialog
        and tests the settings are appropriately applied."""
        self.debugLog(u"validatePrefsConfigUi() method called.")

        error_msg_dict = indigo.Dict()
        update_email   = valuesDict['updaterEmail']
        update_wanted  = valuesDict['updaterEmailsEnabled']

        try:
            if update_wanted and not update_email:
                error_msg_dict['updaterEmail'] = u"If you want to be notified of updates, you must supply an email address."
                error_msg_dict['showAlertText'] = u"Notifications require a valid email address."
                return False, valuesDict, error_msg_dict
            elif update_wanted and "@" not in update_email:
                error_msg_dict['updaterEmail'] = u"Valid email addresses have at least one @ symbol in them (foo@bar.com)."
                error_msg_dict['showAlertText'] = u"Notifications require a valid email address."
                return False, valuesDict, error_msg_dict
        except:
            pass

        return True, valuesDict

    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        """The closedPrefsConfigUi method is called when the user
        closes the plugin config dialog."""
        self.debugLog(u"closedPrefsConfigUi() method called.")

        if userCancelled:
            self.debugLog(u"  User prefs dialog cancelled.")

        if not userCancelled:
            self.debugLog(u"  User prefs saved.")
            self.debugLog(u"============ Plugin Prefs ============")

            if self.pluginPrefs['showDebugInfo'] and self.pluginPrefs['showDebugLevel'] >= 3:
                self.debugLog(u"{0}".format(valuesDict))
            else:
                self.debugLog(u"Plugin preferences suppressed. Set debug level to [High] to write them to the log.")

            if self.debug:
                self.debugLog(u"Debugging on -- level set to: {0}".format(self.pluginPrefs['showDebugLevel']))
            else:
                self.debugLog(u"Debugging off.")

    def validateDeviceConfigUi(self, valuesDict, typeID, devId):
        """The validateDeviceConfigUi method is called to determine whether
        the device is properly configured. Presently, there is no danger that
        the plugin is mis-configured as there is only one setting that is
        controlled by the plugin."""
        self.debugLog(u"validateDeviceConfigUi() method called.")
        self.debugLog(u"============ Device dict ============")

        if self.pluginPrefs['showDebugInfo'] and self.pluginPrefs['showDebugLevel'] >= 3:
            self.debugLog(u"{0}".format(valuesDict))
        else:
            self.debugLog(u"Device preferences suppressed. Set debug level to [High] to write them to the log.")

        return True, valuesDict

    def toggleDebugEnabled(self):
        """The toggleDebugEnabled method is a simple toggle to enable or
        disable plugin debugging from the Indigo Plugin menu."""
        self.debugLog(u"toggleDebugEnabled() method called.")
        if not self.debug:
            self.debug = True
            self.pluginPrefs['showDebugInfo'] = True
            indigo.server.log(u"Debugging on.")
            self.debugLog(u"Debug level: {0}".format(self.debugLevel))
        else:
            self.debug = False
            self.pluginPrefs['showDebugInfo'] = False
            indigo.server.log(u"Debugging off.")

    def checkVersionNow(self):
        """The checkVersionNow method reaches out to check and see if the
        user as the most current version of the plugin installed."""
        self.debugLog(u"checkVersionNow() method called.")
        self.updater.checkVersionNow()

    def getGlobalProps(self, dev):
        """The getGlobalProps method sets up global values
        for each device as we iterate through them (as they
        may have changed.)"""
        self.debugLog(u"getGlobalProps() method called.")

        self.debug            = self.pluginPrefs.get('showDebugInfo', False)
        self.downloadInterval = int(self.pluginPrefs.get('downloadInterval', 900))
        self.updater          = indigoPluginUpdateChecker.updateChecker(self, "http://davel17.github.io/BikeShare/bikeShare_version.html")
        self.updaterEmail     = self.pluginPrefs.get('updaterEmail', "")

    def getBikeData(self):
        """The getBikeData action reaches out to the bike share server and
        downloads the JSON needed data."""
        self.debugLog(u"getBikeData() method called.")

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

        # Communication error handling:
        # =====================================================================
        except urllib2.HTTPError as error:
            parsed_simplejson = {}
            self.errorLog(u"Unable to reach sharing service. Reason: HTTPError - {0}".format(error))

        except urllib2.URLError as error:
            parsed_simplejson = {}
            self.errorLog(u"Unable to reach sharing service. Reason: URLError - {0}".format(error))

        except Exception as error:
            parsed_simplejson = {}
            if "invalid literal for int() with base 16: ''" in error:
                self.errorLog(u"Congratulations! You have discovered a somewhat obscure bug in Python2.5. "
                              u"This problem should clear up on its own, but may come back periodically.")
            else:
                self.errorLog(u"Unable to reach sharing service. Line: {0} Error: {1}.".format(sys.exc_traceback.tb_lineno, error))

        return parsed_simplejson

    def getStationList(self, filter="", typeId=0, valuesDict=None, targetId=0):
        """ The getStationList() method generates a sorted list of station
        names for use in device config dialogs.
        """
        self.debugLog(u"getStationList() method called.")
        parsed_simplejson = self.getBikeData()

        return sorted([dock['stationName'] for dock in parsed_simplejson['stationBeanList']])

    def killAllComms(self):
        """ killAllComms() sets the enabled status of all plugin devices to
        false. """

        for dev in indigo.devices.itervalues("self"):
            try:
                indigo.device.enable(dev, value=False)
            except Exception as error:
                self.debugLog(u"Exception when trying to kill all comms. Line {1}: Error: {0}".format(sys.exc_traceback.tb_lineno, error))

    def unkillAllComms(self):
        """ unkillAllComms() sets the enabled status of all plugin devices to
        true. """

        for dev in indigo.devices.itervalues("self"):
            try:
                indigo.device.enable(dev, value=True)
            except Exception as error:
                self.debugLog(u"Exception when trying to unkill all comms. Line: {1} Error: {0}".format(sys.exc_traceback.tb_lineno, error))

    def parseBikeData(self, dev, parsed_simplejson):
        """ The parseBikeData() method takes the JSON data (contained
        within 'parsed_simplejson' variable) and assigns values to
        relevant device states. In instances where the service provides
        a null string value, the plugin assigns the value of "Not
        provided." to alert the user to that fact."""
        self.debugLog(u"parseBikeData() method called.")

        for dock in parsed_simplejson['stationBeanList']:
            if dev.pluginProps['stationName'] == dock['stationName']:

                for key in [
                    'altitude',
                    'availableBikes',
                    'availableDocks',
                    'city',
                    'executionTime',
                    'landMark',
                    'lastCommunicationTime',
                    'latitude',
                    'location',
                    'longitude',
                    'postalCode',
                    'renting',
                    'stAddress1',
                    'stAddress2',
                    'stationName',
                    'statusKey',
                    'statusValue',
                    'totalDocks',
                ]:

                    if key not in dock.keys() or dock[key] == "":
                        dock[key] = u"Not provided"
                    dev.updateStateOnServer(key, value=dock[key], uiValue=u"{0}".format(dock[key]))

                if 'is_renting' not in dock.keys() or dock['is_renting'] == "":
                    dock['is_renting'] = u"Not provided"
                dev.updateStateOnServer('isRenting', value=dock['is_renting'], uiValue=u"{0}".format(dock['is_renting']))

                if 'id' not in dock.keys() or dock['id'] == "":
                    dock['id'] = u"Not provided"
                dev.updateStateOnServer('stationID', value=dock['id'], uiValue=u"{0}".format(dock['id']))

                # Convert ['Test Station'] string value to boolean. Assumes false.
                # =============================================================
                if dock['testStation']:
                    dev.updateStateOnServer('testStation', value='true')
                else:
                    dev.updateStateOnServer('testStation', value='false')

                # How old is the data?
                # =============================================================
                try:
                    self.debugLog(u"{0} last changed: {1} and data last updated: {2}".format(dev.name, dev.lastChanged, parsed_simplejson['executionTime']))

                    device_time = time.strptime(str(dev.lastChanged), "%Y-%m-%d %H:%M:%S")
                    bike_time   = time.strptime(parsed_simplejson['executionTime'], "%Y-%m-%d %I:%M:%S %p")
                    diff_time   = time.mktime(device_time) - time.mktime(bike_time)

                    # Sometimes the sharing service clock is ahead of the  Indigo server clock. Since the result can't be negative  by definition, let's make it zero and call it a day.
                    # =========================================================
                    if diff_time < 0:
                        diff_time = 0
                    diff_time_str = u"{0}".format(dt.timedelta(seconds=diff_time))
                    dev.updateStateOnServer('dataAge', value=diff_time_str, uiValue=diff_time_str)

                except:
                    dev.updateStateOnServer('dataAge', value=u"Unknown", uiValue=u"Unknown")

        return

    def refreshBikeAction(self, valuesDict):
        """The refreshBikeAction method is used to trigger a data refresh
        cycle when requested by the user through an Indigo action."""
        self.debugLog(u"refreshBikeAction() method called.")

        self.refreshBikeData()

    def refreshBikeData(self):
        """This method refreshes bike data for all devices based on a
        plugin menu call. Note that the code in this method is
        generally the same as runConcurrentThread(). Changes reflected
        there may need to be added here as well."""

        try:
            parsed_simplejson = self.getBikeData()
            if self.pluginPrefs['showDebugInfo'] and self.pluginPrefs['showDebugLevel'] >= 3:
                self.debugLog(u"{0}".format(parsed_simplejson))
            else:
                self.debugLog(u"Device preferences suppressed. Set debug level to [High] to write JSON to the log.")

            for dev in indigo.devices.itervalues("self"):
                dev.stateListOrDisplayStateIdChanged()

                if not dev:
                    indigo.server.log(u"There aren't any devices to poll yet. Sleeping.")
                    self.sleep(self.downloadInterval)

                elif not dev.configured:
                    indigo.server.log(u"[{0}] Skipping device because it is not fully configured.".format(dev.name))
                    self.sleep(60)

                elif dev.enabled:
                    self.getGlobalProps(dev)

                    try:
                        if parsed_simplejson != {}:
                            self.parseBikeData(dev, parsed_simplejson)

                            if dev.states['statusValue'] == 'In Service':
                                dev.updateStateOnServer('onOffState', value=False, uiValue=u"{0}".format(dev.states['availableBikes']))
                                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
                            else:
                                dev.updateStateOnServer('onOffState', value=False, uiValue=u"{0}".format(dev.states['statusValue']))
                                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                        elif parsed_simplejson == {}:
                            dev.setErrorStateOnServer(u"No Comm")
                            self.debugLog(u"Comm error. Sleeping until next scheduled poll.")
                            dev.updateStateImageOnServer(indigo.kStateImageSel.Error)
                    except Exception as error:
                        dev.updateStateOnServer('onOffState', value=False, uiValue=u"{0}".format(dev.states['availableBikes']))
                        dev.setErrorStateOnServer(u"Error")
                        self.debugLog(u"Exception Line: {0} Error: {1}.".format(sys.exc_traceback.tb_lineno, error))
                        self.debugLog(u"Sleeping until next scheduled poll.")
                        dev.updateStateImageOnServer(indigo.kStateImageSel.Error)

            self.debugLog(u"Data refreshed.")
            parsed_simplejson = {}

        except Exception as error:
            self.errorLog(u"There was a problem refreshing the data.  Will try on next cycle.")
            self.errorLog(u"Exception Line: {0} Error: {1}.".format(sys.exc_traceback.tb_lineno, error))

    def runConcurrentThread(self):
        self.debugLog(u"runConcurrentThread initiated. Sleeping for 5 seconds to allow the Indigo Server to finish.")
        self.sleep(5)

        try:
            while True:

                self.updater.checkVersionPoll()
                self.refreshBikeData()
                self.processTriggers()
                self.sleep(int(self.pluginPrefs.get('downloadInterval', 900)))

        except self.StopThread:
            self.debugLog(u"StopThread() method called.")

    def triggerStartProcessing(self, trigger):
        """ triggerStartProcessing is called when the plugin is started. The
        method builds a global dict: {dev.id: (delay, trigger.id) """

        self.masterTriggerDict[trigger.pluginProps['listOfStations']] = trigger.id

    def triggerStopProcessing(self, trigger):
        """"""
        pass

    def processTriggers(self):
        """ The fireOfflineDeviceTriggers method will examine the statusValue
        state of each device, determine whether there is a trigger for any
        stations reported as not in service, and fire the corresponding
        trigger.
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
