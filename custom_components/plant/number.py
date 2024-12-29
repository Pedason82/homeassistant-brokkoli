"""Number platform for plant integration."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers import device_registry as dr

from .const import (
    ATTR_PLANT,
    DOMAIN,
    ATTR_FLOWERING_DURATION,
    FLOW_PLANT_INFO,
    ATTR_IS_NEW_PLANT,
    DEVICE_TYPE_CYCLE,
    DEVICE_TYPE_PLANT,
    AGGREGATION_MEAN,
    AGGREGATION_MIN,
    AGGREGATION_MAX,
)

from .plant_thresholds import (
    PlantMaxMoisture,
    PlantMinMoisture,
    PlantMaxTemperature,
    PlantMinTemperature,
    PlantMaxConductivity,
    PlantMinConductivity,
    PlantMaxIlluminance,
    PlantMinIlluminance,
    PlantMaxHumidity,
    PlantMinHumidity,
    PlantMaxDli,
    PlantMinDli,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up Number from a config entry."""
    plant = hass.data[DOMAIN][entry.entry_id][ATTR_PLANT]
    
    # Flowering Duration
    flowering_duration = FloweringDurationNumber(
        hass,
        entry,
        plant,
    )
    
    # Min/Max Thresholds
    max_moisture = PlantMaxMoisture(hass, entry, plant)
    min_moisture = PlantMinMoisture(hass, entry, plant)
    max_temperature = PlantMaxTemperature(hass, entry, plant)
    min_temperature = PlantMinTemperature(hass, entry, plant)
    max_conductivity = PlantMaxConductivity(hass, entry, plant)
    min_conductivity = PlantMinConductivity(hass, entry, plant)
    max_illuminance = PlantMaxIlluminance(hass, entry, plant)
    min_illuminance = PlantMinIlluminance(hass, entry, plant)
    max_humidity = PlantMaxHumidity(hass, entry, plant)
    min_humidity = PlantMinHumidity(hass, entry, plant)
    max_dli = PlantMaxDli(hass, entry, plant)
    min_dli = PlantMinDli(hass, entry, plant)

    entities = [
        flowering_duration,
        max_moisture,
        min_moisture,
        max_temperature,
        min_temperature,
        max_conductivity,
        min_conductivity,
        max_illuminance,
        min_illuminance,
        max_humidity,
        min_humidity,
        max_dli,
        min_dli,
    ]
    
    async_add_entities(entities)
    
    # Add entities to plant device
    plant.add_flowering_duration(flowering_duration)
    plant.add_thresholds(
        max_moisture=max_moisture,
        min_moisture=min_moisture,
        max_temperature=max_temperature,
        min_temperature=min_temperature,
        max_conductivity=max_conductivity,
        min_conductivity=min_conductivity,
        max_illuminance=max_illuminance,
        min_illuminance=min_illuminance,
        max_humidity=max_humidity,
        min_humidity=min_humidity,
        max_dli=max_dli,
        min_dli=min_dli,
    )

    return True


class FloweringDurationNumber(NumberEntity, RestoreEntity):
    """Number to track flowering duration."""

    def __init__(self, hass: HomeAssistant, config: ConfigEntry, plant_device) -> None:
        """Initialize the flowering duration number."""
        self._hass = hass
        self._config = config
        self._plant = plant_device
        self._attr_unique_id = f"{config.entry_id}_flowering_duration"
        self.entity_id = async_generate_entity_id(
            f"{Platform.NUMBER}.{{}}", f"{plant_device.name}_flowering_duration", hass=hass
        )
        self._attr_name = f"{plant_device.name} Blütedauer"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 365
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = "Tage"
        self._attr_icon = "mdi:flower"
        self._attr_entity_category = None

    @property
    def device_info(self) -> dict:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._plant.unique_id)},
        }

    async def _update_cycle_duration(self) -> None:
        """Aktualisiert die flowering_duration für Cycles basierend auf den Member Plants."""
        if self._plant.device_type != DEVICE_TYPE_CYCLE or not self._plant._member_plants:
            return

        durations = []
        for plant_id in self._plant._member_plants:
            for entry_id in self._hass.data[DOMAIN]:
                if ATTR_PLANT in self._hass.data[DOMAIN][entry_id]:
                    plant = self._hass.data[DOMAIN][entry_id][ATTR_PLANT]
                    if plant.entity_id == plant_id:
                        if plant.flowering_duration and plant.flowering_duration.native_value is not None:
                            durations.append(plant.flowering_duration.native_value)
                        break

        if not durations:
            self._attr_native_value = 0
            self.async_write_ha_state()
            return

        # Berechne aggregierten Wert
        aggregation_method = self._plant.flowering_duration_aggregation
        if aggregation_method == AGGREGATION_MEAN:
            new_duration = sum(durations) / len(durations)
        elif aggregation_method == AGGREGATION_MIN:
            new_duration = min(durations)
        elif aggregation_method == AGGREGATION_MAX:
            new_duration = max(durations)
        else:  # AGGREGATION_MEDIAN
            sorted_values = sorted(durations)
            n = len(sorted_values)
            if n % 2 == 0:
                new_duration = (sorted_values[n//2 - 1] + sorted_values[n//2]) / 2
            else:
                new_duration = sorted_values[n//2]

        self._attr_native_value = round(new_duration)
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        self._attr_native_value = value
        self.async_write_ha_state()

        # Wenn eine Plant ihre Blütedauer ändert, aktualisiere den zugehörigen Cycle
        if self._plant.device_type == DEVICE_TYPE_PLANT:
            device_registry = dr.async_get(self._hass)
            plant_device = device_registry.async_get_device(
                identifiers={(DOMAIN, self._plant.unique_id)}
            )
            
            if plant_device and plant_device.via_device_id:
                # Suche das Cycle Device
                for device in device_registry.devices.values():
                    if device.id == plant_device.via_device_id:
                        cycle_device = device
                        # Finde den zugehörigen Cycle
                        for entry_id in self._hass.data[DOMAIN]:
                            if ATTR_PLANT in self._hass.data[DOMAIN][entry_id]:
                                cycle = self._hass.data[DOMAIN][entry_id][ATTR_PLANT]
                                if (cycle.device_type == DEVICE_TYPE_CYCLE and 
                                    cycle.unique_id == next(iter(cycle_device.identifiers))[1]):
                                    # Aktualisiere die Blütedauer des Cycles
                                    if cycle.flowering_duration:
                                        await cycle.flowering_duration._update_cycle_duration()
                                    break
                        break

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        # Prüfe ob es eine Neuerstellung ist
        if self._config.data[FLOW_PLANT_INFO].get(ATTR_IS_NEW_PLANT, False):
            # Neue Plant - nutze Config Flow Werte
            self._attr_native_value = self._config.data[FLOW_PLANT_INFO].get(ATTR_FLOWERING_DURATION, 0)
        else:
            # Neustart - stelle letzten Zustand wieder her
            last_state = await self.async_get_last_state()
            if last_state is not None:
                try:
                    self._attr_native_value = float(last_state.state)
                except (TypeError, ValueError):
                    self._attr_native_value = 0


