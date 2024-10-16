### v2024.0.1
- Adds unit test for refresh bike data action.

### v2023.0.2
-  Fixes bug where a race condition may occur if pluginPrefs have not yet been written to disk when the plugin is
   first installed.

### v2023.0.1
-  Code enhancements.

### v2022.0.3
- Adds foundation for API `3.1`.
- Code cleanup.

### v2022.0.2
- Adds `_to_do_list.md` and changes changelog to markdown.
- Moves plugin environment logging to plugin menu item (log only on request).

### v2022.0.1
- Updates plugin for Indigo 2022.1 and Python 3.
- Moves "Refresh Bike Data" to Device Controls menu.
- Eliminates need for the `pandas` module.
- Reorganizes device states for better display in control page and trigger state lists.
- Adds device state reflecting whether the system is within user-defined business hours (to show that data might be
  stale).
- Standardizes Indigo method implementation.

### v2.0.09
- Implements constants.py
- Code refinements.

### v2.0.08
- Fixes bug in readme.md file where logo did not display.

### v2.0.07
- Better addresses situations where bike service doesn't fully support the standard API.

### v2.0.06
- Better integrates DLFramework.

### v2.0.05
- Improvements to device configuration validation.
- Code refinements.

### v2.0.04
- Removes all references to legacy version checking.

### v2.0.03
- For publication.

### v2.0.02
- Adds business hours feature.

### v2.0.01
- Complete rewrite of the plugin to use the standardized GBFS data sharing specification.

### v1.1.07
- Ensures that the plugin is compatible with the Indigo server version.
- Standardizes SupportURL behavior across all plugin functions.

### v1.1.06
- Synchronize self.pluginPrefs in closedPrefsConfigUi().

### v1.1.05
- Changes "En/Disable All Devices" to "En/Disable all Plugin Devices".
- Updates kDefaultPluginPrefs

### v1.1.04
- Changes Python lists to tuples where possible to improve performance.

### v1.1.03
- Adds Write Data to File option to plugin menu.
- Removes plugin update notifications.
- Code refinements.

### v1.1.02
- Fixes bug in plugin menu item to check for latest version.

### v1.1.01
- Updates to Indigo API 2.0 (Indigo 7 now required).
- Converts testStation device state from string to boolean True/False.
- Refactors 'dataAge' and 'executionTime' device states.
  - 'dataAge' now keyed to the last time the bike dock station communicated with the bike sharing service.
  - 'executionTime' now keyed to the last time the Indigo plugin communicated with the bike sharing service.
- Removes legacy device state 'renting'. Users should use the state 'isRenting'.

### v1.0.07
- Updates plist link to wiki.
- Updates plugin update checker to use curl to overcome outdated security of
  Apple's Python install.

### v1.0.06
- Moves documentation to GitHub wiki.
- IPS Configuration
- Fixes bug in info.plist (API reference)

### v1.0.05
- Code consolidation using DLFramework.
- Code consolidation using pluginConfig templates.
- Adds note to documentation that the plugin requires Internet in order to function.

### v1.0.04
- Standardizes plugin menu item styles. Menu items with an ellipsis (...) denotes that a dialog box will open. Menu
  items without an ellipsis will take immediate action.
- Fixed bug related to version control for "Check for Plugin Updates" menu action.

### v1.0.03
- Stylistic changes to Indigo Plugin Update Checker module.
- Improved exception logging.
- Code simplification.
- Adds remote debugging capability.
- Moves updater config to template.

### v1.0.02
- Adds trigger to report when a station is not in service.
- Add menu item to enable/disable all plugin devices.
- Adds Indigo UI icon indicator control:  (green = online, gray = offline/disabled/out of service, red = error/no comm)
- Moves support URL to GitHub.
- UI Refinements

### v1.0.01
- Updates version number to full release and moves the project to GitHub.

### v0.1.4
- String substitution updated for future functionality.
- Updates error trapping for future functionality.

### v0.1.3
- Adds two new states: "isRenting" and "Renting".
- Minimizes outreach to the sharing servers.
- Ensures that devices are not restarted unnecessarily.
- Implements setErrorStateOnServer() method.
- Implements error screens in config dialog.
- Further PEP8 refinements.
- Updates plugin to use Python 2.6 as default.
- Changes url for update checker to use https.
- Simplifies imports.
- UI Refinements.

### v0.1.2
- Fixes duplicate state label.
- Increases compliance with PEP8.

### v0.1.1
- Better honors device start comm/stop comm.
- Updates plugin with support URL.
- Code refinements.

### v0.1.0
- Initial plugin version worthy of public alpha.
