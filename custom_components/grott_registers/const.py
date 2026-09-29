"""Constants for the Grott Registers integration."""

DOMAIN = "grott_registers"
VERSION = "0.1.0"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_INVERTER = "inverter_id"
CONF_DATALOGGER = "datalogger_id"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_EXTENDED = "extended_slots"

DEFAULT_PORT = 5782
DEFAULT_SCAN_INTERVAL = 15
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 240

PLATFORMS = ["sensor", "number", "switch", "time", "button"]

SERVICE_READ = "read_register"
SERVICE_WRITE = "write_register"
SERVICE_WRITE_SLOT = "write_slot"
SERVICE_WRITE_MULTI = "write_registers"
SERVICE_REFRESH = "refresh"
