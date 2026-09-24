# BikeShare Plugin — Code Audit

Date: 2026-09-24
Scope: `Bike Share.indigoPlugin/Contents/Server Plugin/` (plugin.py, constants.py,
plugin_defaults.py, XML config), `tests/`, and repo hygiene. `DLFramework/` was not
reviewed (off-limits, shared across plugins).

Context: `_changelog.md` shows a long run of releases (v2025.1.0 → v2025.2.3) each
fixing silent-failure logic bugs (inverted conditions, undefined state access, swallowed
exceptions, off-by-one comparisons). Several findings below are the same *class* of bug,
still present elsewhere in the code, and the "High" section is ordered to address the
root cause (no unit coverage of the logic that keeps producing these).

## High priority

### 1. No unit tests exist for the plugin's actual logic
`tests/test_plugin.py` and `tests/test_xml.py` are entirely integration tests — every
test requires a live Indigo server, the plugin installed and enabled, and real device/
trigger IDs from `tests/.env`. There is no test that imports `plugin.py` directly and
exercises `parse_bike_data()`, `business_hours()`, `get_system_list()`'s CSV parsing, or
`process_triggers()` against mocked `indigo`/`httpx` data.

Every bug fixed across v2025.1.0–v2025.2.3 (inverted refresh logic, wrong dict key,
`== 1` vs `bool`, stale state bleed between devices, off-by-one on `"24:00"`) was in
exactly this untested logic, and would have been caught by a handful of mocked unit
tests with fixture GBFS JSON. Recommend a `tests/unit/` suite (separate from the
Indigo-server-dependent tests) that stubs `indigo`/`httpx` and feeds `parse_bike_data()`
and `business_hours()` synthetic data, including edge cases already found once
(missing keys, `"24:00"` stop time, empty station lists).

### 2. Per-device error handler in `refresh_bike_data()` can itself raise, aborting the whole refresh
`plugin.py:587-597`:
```python
except Exception:  # noqa
    states_list.append({
        'key': 'onOffState',
        'value': False,
        'uiValue': f"{dev.states['num_bikes_available']}"
        },
    )
```
This handler assumes `num_bikes_available` is already populated on `dev.states`. If the
original exception happened *because* `parse_bike_data()` failed before that state was
ever set (new device, partial/malformed feed data), this line raises a fresh `KeyError`
from inside the `except` block. That isn't caught locally — it propagates to the outer
`try/except` at line 608, which logs a generic message and **stops iterating the
`for dev in indigo.devices.iter(...)` loop entirely**, so every device after the failing
one in that cycle silently gets no update. This is the same failure mode already fixed
once in v2025.2.1 ("remaining devices skipped"), reintroduced via a different code path.
Fix: use `dev.states.get('num_bikes_available', 'Unknown')`.

### 3. Duplicated default literals have drifted out of sync
- `downloadInterval` fallback is hardcoded as `900` in three places
  (`plugin.py:58`, `116`, `180`), but `plugin_defaults.kDefaultPluginPrefs` defines the
  real default as `895`. A fourth call site, `plugin.py:548`
  (`int(self.pluginPrefs['downloadInterval'])`), uses no fallback at all and will raise
  `KeyError` if the pref is ever absent.
- `stop_time` has **three different literal defaults** depending on code path:
  `"23:00"` (`plugin_defaults.py`, `PluginConfig.xml`), `"24:00"`
  (`get_prefs_config_ui_values()`, `plugin.py:163`), and `"23:59"`
  (`business_hours()`, `plugin.py:243`).

None of these are wired to a single constant, so a future edit to "the" default (as
happened in v2025.2.2/v2025.2.3, per the changelog) is easy to apply in one spot and
miss the others. Recommend defining `DEFAULT_DOWNLOAD_INTERVAL` and `DEFAULT_STOP_TIME`
(etc.) once in `constants.py` and importing them everywhere instead of retyping literals.

### 4. `dump_bike_data()` has no error handling and can permanently wedge the log level
`plugin.py:296-310`:
```python
self.indigo_log_handler.setLevel(20)
self.logger.info("Data written to %s" % file_name)
self.indigo_log_handler.setLevel(debug_level)
```
The `open(file_name, 'w')`/write above this isn't wrapped in `try/except`, and the level
restore isn't in a `finally`. If the write fails (target subfolder doesn't exist yet,
permissions, disk full), the exception propagates unhandled **and** the log handler is
left stuck at level 20 (Informational) instead of the user's configured debug level,
until the plugin restarts. Wrap the write in `try/except`, and put the `setLevel`
restore in a `finally`.

## Medium priority

### 5. Inconsistent HTTP error handling between the two fetch methods
`get_system_list()` calls `response.raise_for_status()` before parsing; `get_bike_data()`
(`plugin.py:352-354`) does not, for either the auto-discovery request or the per-feed
requests. An HTTP error that still returns a JSON body (common for API gateways) will
silently proceed with the wrong shape and fail later with a less obvious `KeyError`
instead of a clear `HTTPStatusError`. Add `raise_for_status()` in `get_bike_data()` too.

### 6. Redundant exception types mask intent
Both `get_bike_data()` and `get_system_list()` catch
`(httpx.HTTPStatusError, httpx.RequestError, Exception)`. Since `Exception` is a
superclass of the other two, listing them adds nothing — this reads as "catch httpx
errors specifically" but actually catches everything, including bugs like `TypeError`/
`AttributeError` that probably shouldn't be silently logged as "communication error."
Either catch `Exception` alone and say so, or catch the httpx-specific types with their
own (more specific) log message and let unexpected exceptions surface normally.

### 7. `business_hours()` doesn't support a window that spans midnight
`plugin.py:232-259` compares `start_time <= now <= stop_time` on the same calendar day.
A schedule like start `22:00` / stop `06:00` (a plausible "overnight" business-hours
config) is never true. Either document that overnight windows aren't supported (a
`tooltip` on `start_time`/`stop_time` in `PluginConfig.xml` would do it) or handle the
wraparound explicitly.

## Not flagged (reviewed, judged fine)
- `DLFramework/` — out of scope per `CLAUDE.md`, not reviewed.
- `plugin.py:301`'s hardcoded `"com.fogbert.indigoplugin.bikeShare"` in the
  `dump_bike_data()` log path — not an issue. Indigo creates each plugin's log folder
  using its `Info.plist` bundle id, and the plugin is simply pointing at that
  already-existing path; it isn't a redundant/driftable copy.
- Deprecated camelCase wrapper methods (`commsKillAll`, `commsUnkillAll`,
  `refreshBikeAction`) — intentional back-compat shims for action groups saved under
  old callback names; current `Actions.xml`/`MenuItems.xml` correctly reference the new
  snake_case callbacks.
- `tests/shared` being read-only/submodule-managed — respected, not touched.
