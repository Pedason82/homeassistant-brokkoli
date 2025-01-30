"""Text entities for plant journals."""
from __future__ import annotations

import logging

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers import device_registry as dr
from homeassistant.const import Platform

from .const import (
    ATTR_PLANT,
    DOMAIN,
    FLOW_PLANT_INFO,
    ATTR_IS_NEW_PLANT,
    DEVICE_TYPE_PLANT,
    DEVICE_TYPE_CYCLE,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the plant journal text entity."""
    plant = hass.data[DOMAIN][entry.entry_id][ATTR_PLANT]
    
    # Journal Text für alle Devices
    journal = PlantJournal(hass, entry, plant)
    async_add_entities([journal])
    plant.add_journal(journal)

class PlantJournal(TextEntity, RestoreEntity):
    """Representation of a plant journal text entity."""

    def __init__(self, hass: HomeAssistant, config: ConfigEntry, plant_device) -> None:
        """Initialize the journal text entity."""
        self._hass = hass
        self._config = config
        self._plant = plant_device
        self._attr_name = f"{plant_device.name} Journal"
        self._attr_unique_id = f"{config.entry_id}-journal"
        self.entity_id = async_generate_entity_id(
            f"{Platform.TEXT}.{{}}", f"{plant_device.name}_journal", hass=hass
        )
        self._attr_icon = "mdi:notebook"
        self._attr_native_max = 2000  # Maximale Textlänge
        self._attr_mode = "text"  # Mehrzeiliger Text erlaubt
        self._attr_native_value = ""  # Leerer Text als Standard

    @property
    def device_info(self) -> dict:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._plant.unique_id)},
        }

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        # Prüfe ob es eine Neuerstellung ist
        if self._config.data[FLOW_PLANT_INFO].get(ATTR_IS_NEW_PLANT, False):
            # Neue Plant - initialisiere mit leerem Text
            self._attr_native_value = ""
        else:
            # Neustart - stelle letzten Zustand wieder her
            last_state = await self.async_get_last_state()
            if last_state is not None:
                self._attr_native_value = last_state.state

    async def async_set_value(self, value: str) -> None:
        """Update the current value."""
        self._attr_native_value = value
        self.async_write_ha_state() 