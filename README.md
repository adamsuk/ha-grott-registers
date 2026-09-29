# Grott Registers

Home Assistant integration for the [grottserver](https://github.com/johanmeijer/grott/wiki/Grottserver) register API. It shows the battery-first and grid-first schedules on the device page and can change them. Any other inverter or datalogger register can be read or written from Developer Tools.

The MQTT feed Grott already publishes is live production data (power, energy, SOC). It does not contain these holding registers. This integration uses the HTTP API on port **5782**.

## Install with HACS

HACS installs from a Git repository.

1. Push this folder to GitHub. The repository root must contain `hacs.json` and `custom_components/grott_registers`.
2. In HACS, open **Integrations**, choose **Custom repositories**, paste the repository URL, and set the category to **Integration**.
3. Download **Grott Registers** and restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → Grott Registers**.
5. Enter the grottserver host and port `5782`. Pick the inverter it lists.

## Install without GitHub

Copy `custom_components/grott_registers` into your Home Assistant `config/custom_components/` directory, restart, then add the integration as above.

## What appears on the device

A refresh reads the registers one at a time. The default interval is 15 minutes. Use **Refresh registers** when you want them now. The first refresh after startup takes about a minute.

| Entity | Register | What a change does |
|---|---|---|
| Priority | 1044 | Read only. The inverter sets this from the window that is active right now. |
| Battery charge power | 1090 | Single write, 0–100%. |
| Battery charge stop | 1091 | SOC at which battery-first charging stops. |
| AC charge | 1092 | When on, battery first may charge from the grid. |
| Grid discharge power | 1070 | Single write, 0–100%. |
| Grid discharge stop | 1071 | SOC at which grid-first discharge stops. |
| Battery first 1–3 | 1100–1108 | Start, end, and enabled. |
| Grid first 1–3 | 1080–1088 | Start, end, and enabled. |
| Datalogger time | 31 | Read only. The logger clock the schedule follows. |
| Sync datalogger time | 31 | Writes the grott server's local time into the logger. |

Slots 4–6 (registers 1017–1034) are off by default. Turn them on under **Configure** on the integration entry. On some firmware, grid-first slot 4’s enable register is not a plain on/off value. Leave that option off unless you know the extra block is real on your inverter.

Each entity’s attributes include the register number and the raw hex word.

## How a slot is written

Growatt stores a window as three registers and ignores a write to only one of them. Changing a start time, end time, or enable switch sends all three together. The integration then reads them back. grottserver often answers `OK` even when the inverter kept the old value.

The inverter also rejects a window that contains the current time. That time is the datalogger clock, not the Home Assistant clock. Change the overnight slot during the day.

Times are not decimal `HHMM`. The high byte is the hour and the low byte is the minute, so 05:30 is hex `051e`.

## Datalogger clock

Battery-first and grid-first windows are judged against the datalogger clock (register 31). **Datalogger time** shows that clock as the logger reports it.

**Sync datalogger time** calls grottserver's `datetime` command. That command stamps the local time of the machine running grottserver. It does not send Home Assistant's clock, and it does not take a time you choose. After the write, the integration reads register 31 again and shows whatever the logger stored.

Daylight saving follows the timezone of the grott process. If that host, or its container, is on UTC or has stale timezone data, a 00:00–05:30 window fires at the wrong wall time even when Home Assistant is correct. Check **Datalogger time** against the grott host after the clocks change.

grottserver also writes this clock when the logger connects. The sensor is how you see which time stuck. The same action is `grott_registers.sync_datalogger_time`.

## Any other register

**Developer Tools → Actions**:

- `grott_registers.read_register` — one inverter or datalogger register. Inverter reads default to hex (the reply includes that word and its decimal value). Datalogger reads default to text.
- `grott_registers.write_register` — one register that is **not** part of a time slot.
- `grott_registers.write_slot` — a whole battery-first or grid-first window.
- `grott_registers.write_registers` — a contiguous run, as concatenated 4-digit hex words. `0000051e0001` from register 1100 through 1102 is 00:00–05:30, enabled.
- `grott_registers.refresh` — read the schedule again.
- `grott_registers.sync_datalogger_time` — set the datalogger clock from the grott server's local time, then read it back.

Pass `inverter_id` only when more than one inverter is configured.

Datalogger registers worth knowing:

| Register | Meaning |
|---|---|
| 4 | Update interval |
| 31 | Datalogger clock. The device page reads this and can set it from the grott server clock. |
| 17 | Server address the logger sends data to |
| 18 | Server port |

Writing datalogger register 17 or 18 points the logger at a different server. That can undo a local-only setup and start sending data to Growatt again.

The device page’s **Download diagnostics** dumps every schedule register from the last refresh.

## Options

- **Update interval**: 5 to 240 minutes. A full read is slow, so faster than 15 minutes is rarely useful.
- **Include slots 4–6**: adds the extra SPH windows.

Changing either option reloads the entry.
