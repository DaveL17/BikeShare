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

import datetime as dt
import socket
import time
import urllib2

import simplejson

import indigoPluginUpdateChecker

try:
    import indigo
except:
    pass

__author__    = "DaveL17"
__build__     = ""
__copyright__ = 'Copyright 2017 DaveL17'
__license__   = "MIT"
__title__     = 'Bike Share Plugin for Indigo Home Control'
__version__   = '1.0.02'

kDefaultPluginPrefs = {
    u'bikeSharingService': "",
    u'downloadInterval'    : 900,    # Frequency of updates.
    u'showDebugInfo'       : False,  # Verbose debug logging?
    u'showDebugLevel'      : "Low",  # Low, Medium or High debug output.
    u'updaterEmail'        : "",     # Email to notify of plugin updates.
    u'updaterEmailsEnabled': False   # Notification of plugin updates wanted.
    }


# noinspection PyPep8Naming
class Plugin(indigo.PluginBase):
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        self.debugLog(u"Plugin initialization called.")

        self.debug                = self.pluginPrefs.get('showDebugInfo', False)
        self.debugLevel           = self.pluginPrefs.get('showDebugLevel', "Low")
        self.downloadInterval     = int(self.pluginPrefs.get('downloadInterval', 900))
        updater_url = "https://davel17.github.io/BikeShare/bikeShare_version.html"
        self.updater              = indigoPluginUpdateChecker.updateChecker(self, updater_url)
        self.updaterEmail         = self.pluginPrefs.get('updaterEmail', "")
        self.updaterEmailsEnabled = self.pluginPrefs.get(u"updaterEmailsEnabled", "false")

        if self.pluginPrefs['showDebugLevel'] == "High":
            self.debugLog(u"======================================================================")
            self.debugLog(u"Caution! Debug set to high. This results in a lot of output to the log")
            self.debugLog(u"======================================================================")
            self.sleep(3)
        else:
            self.debugLog(u"Debug level set to: {0}".format(self.pluginPrefs['showDebugLevel']))

        if self.pluginPrefs['showDebugInfo'] and self.pluginPrefs['showDebugLevel'] == "High":
            self.debugLog(u"{0}".format(pluginPrefs))
        else:
            self.debugLog(u"Plugin preferences suppressed. Set debug level to [High] to write them to the log.")

    def __del__(self):
        indigo.PluginBase.__del__(self)

    def startup(self):
        self.debugLog(u"Startup called.")

        try:
            self.updater.checkVersionPoll()
        except Exception as e:
            self.errorLog(u"Update checker error: {0}".format(e))

    def shutdown(self):
        self.debugLog(u"Shutdown() method called.")

    def deviceStartComm(self, dev):
        self.debugLog(u"Starting Bike Share device: {0}".format(dev.name))
        dev.updateStateOnServer('onOffState', value=False, uiValue=u"Enabled")

    def deviceStopComm(self, dev):
        self.debugLog(u"Stopping Bike Share device: {0}".format(dev.name))
        dev.updateStateOnServer('onOffState', value=False, uiValue=u"Disabled")

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

            if self.pluginPrefs['showDebugInfo'] and self.pluginPrefs['showDebugLevel'] == "High":
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

        if self.pluginPrefs['showDebugInfo'] and self.pluginPrefs['showDebugLevel'] == "High":
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
        self.debugLevel       = self.pluginPrefs.get('showDebugLevel', "Low")
        self.downloadInterval = int(self.pluginPrefs.get('downloadInterval', 900))
        self.updater          = indigoPluginUpdateChecker.updateChecker(self, "https://dl.dropboxusercontent.com/u/2796881/bikeShare_version.html")
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
        except urllib2.HTTPError as e:
            parsed_simplejson = {}
            self.errorLog(u"Unable to reach sharing service. Reason: HTTPError - {0}".format(e))

        except urllib2.URLError as e:
            parsed_simplejson = {}
            self.errorLog(u"Unable to reach sharing service. Reason: URLError - {0}".format(e))

        except Exception as e:
            parsed_simplejson = {}
            if "invalid literal for int() with base 16: ''" in e:
                self.errorLog(u"Congratulations! You have discovered a somewhat obscure bug in Python2.5. "
                              u"This problem should clear up on its own, but may come back periodically.")
            else:
                self.errorLog(u"Unable to reach sharing service. Reason: Exception - {0}".format(e))

        return parsed_simplejson

    def getStationList(self, filter="", typeId=0, valuesDict=None, targetId=0):
        """ The getStationList() method generates a sorted list of station
        names for use in device config dialogs.
        """
        self.debugLog(u"getStationList() method called.")

        station_list = []
        parsed_simplejson = self.getBikeData()

        for dock in parsed_simplejson['stationBeanList']:
            station_list.append(dock['stationName'])

        return sorted(station_list)

    def parseBikeData(self, dev, parsed_simplejson):
        """ The parseBikeData() method takes the JSON data (contained
        within 'parsed_simplejson' variable) and assigns values to
        relevant device states. In instances where the service provides
        a null string value, the plugin assigns the value of "Not
        provided." to alert the user to that fact."""
        self.debugLog(u"parseBikeData() method called.")

        for dock in parsed_simplejson['stationBeanList']:
            if dev.pluginProps['stationName'] == dock['stationName']:

                if 'altitude' not in dock.keys() or dock['altitude'] == "":
                    dock['altitude'] = u"Not provided"
                dev.updateStateOnServer('altitude', value=dock['altitude'], uiValue=u"{0}".format(dock['altitude']))

                if 'availableBikes' not in dock.keys() or dock['availableBikes'] == "":
                    dock['availableBikes'] = u"Not provided"
                dev.updateStateOnServer('availableBikes', value=int(dock['availableBikes']), uiValue=u"{0}".format(dock['availableBikes']))

                if 'availableDocks' not in dock.keys() or dock['availableDocks'] == "":
                    dock['availableDocks'] = u"Not provided"
                dev.updateStateOnServer('availableDocks', value=int(dock['availableDocks']), uiValue=u"{0}".format(dock['availableDocks']))

                if 'city' not in dock.keys() or dock['city'] == "":
                    dock['city'] = u"Not provided"
                dev.updateStateOnServer('city', value=dock['city'], uiValue=u"{0}".format(dock['city']))

                if 'executionTime' not in dock.keys() or dock['executionTime'] == "":
                    parsed_simplejson['executionTime'] = u"Not provided"
                dev.updateStateOnServer('executionTime', value=parsed_simplejson['executionTime'], uiValue=u"{0}".format(parsed_simplejson['executionTime']))

                if 'is_renting' not in dock.keys() or dock['is_renting'] == "":
                    dock['is_renting'] = u"Not provided"
                dev.updateStateOnServer('isRenting', value=dock['is_renting'], uiValue=u"{0}".format(dock['is_renting']))

                if 'landMark' not in dock.keys() or dock['landMark'] == "":
                    dock['landMark'] = u"Not provided"
                dev.updateStateOnServer('landMark', value=dock['landMark'], uiValue=u"{0}".format(dock['landMark']))

                if 'lastCommunicationTime' not in dock.keys() or dock['lastCommunicationTime'] == "":
                    dock['lastCommunicationTime'] = u"Not provided"
                dev.updateStateOnServer('lastCommunicationTime', value=u"{0}".format(dock['lastCommunicationTime']), uiValue=u"{0}".format(dock['lastCommunicationTime']))

                if 'latitude' not in dock.keys() or dock['latitude'] == "":
                    dock['latitude'] = u"Not provided"
                dev.updateStateOnServer('latitude', value=u"{0}".format(dock['latitude']), uiValue=u"{0}".format(dock['latitude']))

                if 'location' not in dock.keys() or dock['location'] == "":
                    dock['location'] = u"Not provided"
                dev.updateStateOnServer('location', value=dock['location'], uiValue=u"{0}".format(dock['location']))

                if 'longitude' not in dock.keys() or dock['longitude'] == "":
                    dock['longitude'] = u"Not provided"
                dev.updateStateOnServer('longitude', value=u"{0}".format(dock['longitude']), uiValue=u"{0}".format(dock['longitude']))

                if 'postalCode' not in dock.keys() or dock['postalCode'] == "":
                    dock['postalCode'] = u"Not provided"
                dev.updateStateOnServer('postalCode', value=dock['postalCode'], uiValue=u"{0}".format(dock['postalCode']))

                if 'renting' not in dock.keys() or dock['renting'] == "":
                    dock['renting'] = u"Not provided"
                dev.updateStateOnServer('renting', value=dock['renting'], uiValue=u"{0}".format(dock['renting']))

                if 'stAddress1' not in dock.keys() or dock['stAddress1'] == "":
                    dock['stAddress1'] = u"Not provided"
                dev.updateStateOnServer('stAddress1', value=dock['stAddress1'], uiValue=u"{0}".format(dock['stAddress1']))

                if 'stAddress2' not in dock.keys() or dock['stAddress2'] == "":
                    dock['stAddress2'] = u"Not provided"
                dev.updateStateOnServer('stAddress2', value=dock['stAddress2'], uiValue=u"{0}".format(dock['stAddress2']))

                if 'id' not in dock.keys() or dock['id'] == "":
                    dock['id'] = u"Not provided"
                dev.updateStateOnServer('stationID', value=dock['id'], uiValue=u"{0}".format(dock['id']))

                if 'stationName' not in dock.keys() or dock['stationName'] == "":
                    dock['stationName'] = u"Not provided"
                dev.updateStateOnServer('stationName', value=dock['stationName'], uiValue=u"{0}".format(dock['stationName']))

                if 'statusKey' not in dock.keys() or dock['statusKey'] == "":
                    dock['statusKey'] = u"Not provided"
                dev.updateStateOnServer('statusKey', value=bool(dock['statusKey']), uiValue=u"{0}".format(dock['statusKey']))

                if 'statusValue' not in dock.keys() or dock['statusValue'] == "":
                    dock['statusValue'] = u"Not provided"
                dev.updateStateOnServer('statusValue', value=dock['statusValue'], uiValue=u"{0}".format(dock['statusValue']))

                if 'totalDocks' not in dock.keys() or dock['totalDocks'] == "":
                    dock['totalDocks'] = u"Not provided"
                dev.updateStateOnServer('totalDocks', value=int(dock['totalDocks']), uiValue=u"{0}".format(dock['totalDocks']))

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
            if self.pluginPrefs['showDebugInfo'] and self.pluginPrefs['showDebugLevel'] == "High":
                self.debugLog(u"{0}".format(parsed_simplejson))
            else:
                self.debugLog(u"Device preferences suppressed. Set debug level to [High] to write JSON to the log.")

            for dev in indigo.devices.itervalues("self"):
                dev.stateListOrDisplayStateIdChanged()

                if not dev:
                    indigo.server.log(u"There aren't any devices to poll yet. Sleeping.")
                    self.sleep(self.downloadInterval)

                elif not dev.configured:
                    indigo.server.log(u"A device has been created, but is not fully configured. Sleeping for a minute while you finish.")
                    self.sleep(60)

                elif not dev.enabled:
                    self.sleep(self.downloadInterval)

                elif dev.enabled:
                    self.getGlobalProps(dev)

                    try:
                        if parsed_simplejson != {}:
                            self.parseBikeData(dev, parsed_simplejson)
                            dev.updateStateOnServer('onOffState', value=False, uiValue=u"{0}".format(dev.states['availableBikes']))
                        elif parsed_simplejson == {}:
                            dev.setErrorStateOnServer(u"No Comm")
                            self.debugLog(u"Comm error. Sleeping until next scheduled poll.")
                    except Exception as e:
                        dev.updateStateOnServer('onOffState', value=False, uiValue=u"{0}".format(dev.states['availableBikes']))
                        dev.setErrorStateOnServer(u"Error")
                        self.debugLog(u"Exception error: {0}. Sleeping until next scheduled poll.".format(e))

            self.debugLog(u"Data refreshed.")
            parsed_simplejson = {}

        except Exception as e:
            self.errorLog(u"There was a problem refreshing the data.  Will try on next cycle.")
            self.errorLog(u"{0}".format(e))

    def runConcurrentThread(self):
        self.debugLog(u"runConcurrentThread initiated. Sleeping for 5 seconds to allow the Indigo Server to finish.")
        self.sleep(5)

        try:
            while True:

                self.updater.checkVersionPoll()
                self.refreshBikeData()
                self.sleep(int(self.pluginPrefs.get('downloadInterval', 900)))

        except self.StopThread:
            self.debugLog(u"StopThread() method called.")
