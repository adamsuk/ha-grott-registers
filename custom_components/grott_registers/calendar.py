"""Read-only calendars for the battery, grid, and load-first day."""

from __future__ import annotations

from datetime import datetime, time as dt_time, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .codec import ScheduleBlock, schedule_blocks
from .const import DOMAIN
from .coordinator import GrottCoordinator
from .entity import GrottEntity

_CALENDARS = (
    ("battery", "battery_first_schedule", "Battery first", "#E09F3E", "mdi:battery-clock"),
    ("grid", "grid_first_schedule", "Grid first", "#4C78C8", "mdi:transmission-tower"),
    ("load", "load_first_schedule", "Load first", "#3D9A6A", "mdi:home-lightning-bolt"),
)
_SUMMARY = {"battery": "Battery first", "grid": "Grid first", "load": "Load first"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GrottCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        GrottScheduleCalendar(coordinator, mode, key, name, color, icon)
        for mode, key, name, color, icon in _CALENDARS
    )


class GrottScheduleCalendar(GrottEntity, CalendarEntity):
    """One mode, repeated every day. Editing stays on the time and switch entities."""

    def __init__(
        self,
        coordinator: GrottCoordinator,
        mode: str,
        key: str,
        name: str,
        color: str,
        icon: str,
    ) -> None:
        super().__init__(coordinator, key, name)
        self._mode = mode
        self._attr_icon = icon
        self._attr_initial_color = color

    @property
    def available(self) -> bool:
        return super().available and bool(self.coordinator.data)

    @property
    def event(self) -> CalendarEvent | None:
        if not self.coordinator.data:
            return None
        now = dt_util.now()
        events = self._events_between(now, now + timedelta(days=2))
        for item in events:
            if item.start_datetime_local <= now < item.end_datetime_local:
                return item
        upcoming = [item for item in events if item.start_datetime_local > now]
        if not upcoming:
            return None
        return min(upcoming, key=lambda item: item.start_datetime_local)

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        return self._events_between(start_date, end_date)

    def _events_between(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        blocks = [
            block
            for block in schedule_blocks(self.coordinator.data or {}, self.coordinator.extended)
            if block.mode == self._mode
        ]
        if not blocks:
            return []
        start_local = dt_util.as_local(start)
        end_local = dt_util.as_local(end)
        zone = dt_util.get_default_time_zone()
        events: list[CalendarEvent] = []
        day = start_local.date() - timedelta(days=1)
        last = end_local.date()
        while day <= last:
            for block in blocks:
                event_start = _at(day, block.start_minute, zone)
                event_end = _at(day, block.end_minute, zone)
                if event_end <= start_local or event_start >= end_local:
                    continue
                events.append(
                    CalendarEvent(
                        start=event_start,
                        end=event_end,
                        summary=_summary(block),
                        description=_description(block),
                        uid=(
                            f"{self.coordinator.inverter_id}-{block.mode}-"
                            f"{day.isoformat()}-{block.start_minute}-{block.slot or 0}"
                        ),
                    )
                )
            day += timedelta(days=1)
        return events


def _at(day, minute: int, zone) -> datetime:
    if minute >= 1440:
        day = day + timedelta(days=1)
        minute = 0
    hour, mins = divmod(minute, 60)
    return datetime.combine(day, dt_time(hour, mins), tzinfo=zone)


def _summary(block: ScheduleBlock) -> str:
    label = _SUMMARY[block.mode]
    if block.slot is None:
        return label
    return f"{label} {block.slot}"


def _description(block: ScheduleBlock) -> str:
    if block.start_register is None:
        return "No enabled battery-first or grid-first window covers this time."
    end_register = block.start_register + 2
    return f"Slot {block.slot}, registers {block.start_register}–{end_register}."
