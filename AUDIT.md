# BikeShare Plugin — Code Audit

Date: 2026-09-24
Scope: `Bike Share.indigoPlugin/Contents/Server Plugin/` (plugin.py, constants.py,
plugin_defaults.py, XML config), `tests/`, and repo hygiene. `DLFramework/` was not
reviewed (off-limits, shared across plugins).

Context: `_changelog.md` shows a long run of releases (v2025.1.0 → v2025.2.3) each
fixing silent-failure logic bugs (inverted conditions, undefined state access, swallowed
exceptions, off-by-one comparisons).

All findings from this audit have been fixed as of v2025.2.4 (see `_changelog.md`),
including adding a `tests/unit/` suite that exercises `parse_bike_data()`,
`business_hours()`, `process_triggers()`, `get_system_list()`, `get_bike_data()`, and
`refresh_bike_data()` offline, with regression coverage for the bugs found here.

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
