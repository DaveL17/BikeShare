"""
Repository of application constants

The constants.py file contains all application constants and is imported as a library. References
are denoted as constants by the use of all caps.
"""


def __init__():
    pass


DEBUG_LABELS = {
    10: "Debugging Messages",
    20: "Informational Messages",
    30: "Warning Messages",
    40: "Error Messages",
    50: "Critical Errors Only"
}

GBFS_SYSTEMS_CSV_URL = "https://raw.githubusercontent.com/NABSA/gbfs/master/systems.csv"
HTTP_TIMEOUT        = 10
TIMESTAMP_FORMAT    = "%Y-%m-%d %H:%M:%S"

# Plugin preference defaults. Defined once here and imported wherever a fallback value is needed (plugin_defaults.py,
# plugin.py) so the "real" default can't drift out of sync between call sites.
DEFAULT_DOWNLOAD_INTERVAL = 895
DEFAULT_START_TIME       = "00:00"
DEFAULT_STOP_TIME        = "23:00"
