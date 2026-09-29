"""Shared entity base."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import GrottCoordinator


class GrottEntity(CoordinatorEntity[GrottCoordinator]):
    """An entity attached to the inverter device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GrottCoordinator, key: str, name: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.inverter_id}_{key}"
        self._attr_name = name
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        return super().available
