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
