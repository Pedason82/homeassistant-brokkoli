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
    ATTR_POT_SIZE,
    DEFAULT_POT_SIZE,
    ATTR_WATER_CAPACITY,
    DEFAULT_WATER_CAPACITY,
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
    
    # Pot Size
    pot_size = PotSizeNumber(
        hass,
        entry,
        plant,
    )
    
    # Water Capacity
    water_capacity = WaterCapacityNumber(
        hass,
        entry,
        plant,
    )
    
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
        pot_size,
        water_capacity,
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
    plant.add_pot_size(pot_size)
    plant.add_water_capacity(water_capacity)
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
        self._attr_name = f"{plant_device.name} Flowering Duration"
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

        # Wenn ein Cycle seine Blütedauer ändert, aktualisiere alle Member Plants
        if self._plant.device_type == DEVICE_TYPE_CYCLE:
            device_registry = dr.async_get(self._hass)
            
            # Finde das Cycle Device
            cycle_device = device_registry.async_get_device(
                identifiers={(DOMAIN, self._plant.unique_id)}
            )
            
            if cycle_device:
                # Finde alle zugehörigen Plant Devices
                for device_entry in device_registry.devices.values():
                    if device_entry.via_device_id == cycle_device.id:
                        # Finde die zugehörige Plant Entity
                        for entry_id in self._hass.data[DOMAIN]:
                            if ATTR_PLANT in self._hass.data[DOMAIN][entry_id]:
                                plant = self._hass.data[DOMAIN][entry_id][ATTR_PLANT]
                                if (plant.device_type != DEVICE_TYPE_CYCLE and 
                                    plant.unique_id == next(iter(device_entry.identifiers))[1]):
                                    # Aktualisiere die Blütedauer der Plant
                                    if plant.flowering_duration:
                                        await plant.flowering_duration.async_set_native_value(value)
                                    break

        # Bestehende Logik für Plant -> Cycle Update
        elif self._plant.device_type == DEVICE_TYPE_PLANT:
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


class PotSizeNumber(NumberEntity, RestoreEntity):
    """Number to track pot size in liters."""

    def __init__(self, hass: HomeAssistant, config: ConfigEntry, plant_device) -> None:
        """Initialize the pot size number."""
        self._hass = hass
        self._config = config
        self._plant = plant_device
        self._attr_unique_id = f"{config.entry_id}_pot_size"
        self.entity_id = async_generate_entity_id(
            f"{Platform.NUMBER}.{{}}", f"{plant_device.name}_pot_size", hass=hass
        )
        self._attr_name = f"{plant_device.name} Pot Size"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 100
        self._attr_native_step = 0.1
        self._attr_native_unit_of_measurement = "L"
        self._attr_icon = "mdi:cup"
        self._attr_entity_category = None
        self._attr_mode = "box"
        
        # Setze den initialen Wert aus der Config Entry
        self._attr_native_value = self._config.data[FLOW_PLANT_INFO].get(ATTR_POT_SIZE, DEFAULT_POT_SIZE)

    @property
    def device_info(self) -> dict:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._plant.unique_id)},
        }

    async def _update_cycle_pot_size(self) -> None:
        """Aktualisiert die pot_size für Cycles basierend auf den Member Plants."""
        if self._plant.device_type != DEVICE_TYPE_CYCLE or not self._plant._member_plants:
            return

        pot_sizes = []
        for plant_id in self._plant._member_plants:
            for entry_id in self._hass.data[DOMAIN]:
                if ATTR_PLANT in self._hass.data[DOMAIN][entry_id]:
                    plant = self._hass.data[DOMAIN][entry_id][ATTR_PLANT]
                    if plant.entity_id == plant_id:
                        if plant.pot_size and plant.pot_size.native_value is not None:
                            pot_sizes.append(plant.pot_size.native_value)
                        break

        if not pot_sizes:
            self._attr_native_value = 0
            self.async_write_ha_state()
            return

        # Berechne aggregierten Wert
        aggregation_method = self._plant.pot_size_aggregation
        if aggregation_method == AGGREGATION_MEAN:
            new_size = sum(pot_sizes) / len(pot_sizes)
        elif aggregation_method == AGGREGATION_MIN:
            new_size = min(pot_sizes)
        elif aggregation_method == AGGREGATION_MAX:
            new_size = max(pot_sizes)
        else:  # AGGREGATION_MEDIAN
            sorted_values = sorted(pot_sizes)
            n = len(sorted_values)
            if n % 2 == 0:
                new_size = (sorted_values[n//2 - 1] + sorted_values[n//2]) / 2
            else:
                new_size = sorted_values[n//2]

        self._attr_native_value = round(new_size, 1)
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        self._attr_native_value = value
        self.async_write_ha_state()

        # Wenn ein Cycle seine Topfgröße ändert, aktualisiere alle Member Plants
        if self._plant.device_type == DEVICE_TYPE_CYCLE:
            device_registry = dr.async_get(self._hass)
            
            # Finde das Cycle Device
            cycle_device = device_registry.async_get_device(
                identifiers={(DOMAIN, self._plant.unique_id)}
            )
            
            if cycle_device:
                # Finde alle zugehörigen Plant Devices
                for device_entry in device_registry.devices.values():
                    if device_entry.via_device_id == cycle_device.id:
                        # Finde die zugehörige Plant Entity
                        for entry_id in self._hass.data[DOMAIN]:
                            if ATTR_PLANT in self._hass.data[DOMAIN][entry_id]:
                                plant = self._hass.data[DOMAIN][entry_id][ATTR_PLANT]
                                if (plant.device_type != DEVICE_TYPE_CYCLE and 
                                    plant.unique_id == next(iter(device_entry.identifiers))[1]):
                                    # Aktualisiere die Topfgröße der Plant
                                    if plant.pot_size:
                                        await plant.pot_size.async_set_native_value(value)
                                    break

        # Bestehende Logik für Plant -> Cycle Update
        elif self._plant.device_type == DEVICE_TYPE_PLANT:
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
                                    # Aktualisiere die Topfgröße des Cycles
                                    if cycle.pot_size:
                                        await cycle.pot_size._update_cycle_pot_size()
                                    break
                        break

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        # Prüfe ob es eine Neuerstellung ist
        if self._config.data[FLOW_PLANT_INFO].get(ATTR_IS_NEW_PLANT, False):
            # Neue Plant - nutze Config Flow Werte
            self._attr_native_value = self._config.data[FLOW_PLANT_INFO].get(ATTR_POT_SIZE, DEFAULT_POT_SIZE)
        else:
            # Neustart - stelle letzten Zustand wieder her
            last_state = await self.async_get_last_state()
            if last_state is not None:
                try:
                    self._attr_native_value = float(last_state.state)
                except (TypeError, ValueError):
                    self._attr_native_value = DEFAULT_POT_SIZE


class WaterCapacityNumber(NumberEntity, RestoreEntity):
    """Number to track water capacity in percent."""

    def __init__(self, hass: HomeAssistant, config: ConfigEntry, plant_device) -> None:
        """Initialize the water capacity number."""
        self._hass = hass
        self._config = config
        self._plant = plant_device
        self._attr_unique_id = f"{config.entry_id}_water_capacity"
        self.entity_id = async_generate_entity_id(
            f"{Platform.NUMBER}.{{}}", f"{plant_device.name}_water_capacity", hass=hass
        )
        self._attr_name = f"{plant_device.name} Water Capacity"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 100
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = "%"
        self._attr_icon = "mdi:water-percent"
        self._attr_entity_category = None
        self._attr_mode = "box"
        
        # Setze den initialen Wert aus der Config Entry
        self._attr_native_value = self._config.data[FLOW_PLANT_INFO].get(ATTR_WATER_CAPACITY, DEFAULT_WATER_CAPACITY)

    @property
    def device_info(self) -> dict:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._plant.unique_id)},
        }

    async def _update_cycle_water_capacity(self) -> None:
        """Aktualisiert die water_capacity für Cycles basierend auf den Member Plants."""
        if self._plant.device_type != DEVICE_TYPE_CYCLE or not self._plant._member_plants:
            return

        capacities = []
        for plant_id in self._plant._member_plants:
            for entry_id in self._hass.data[DOMAIN]:
                if ATTR_PLANT in self._hass.data[DOMAIN][entry_id]:
                    plant = self._hass.data[DOMAIN][entry_id][ATTR_PLANT]
                    if plant.entity_id == plant_id:
                        if plant.water_capacity and plant.water_capacity.native_value is not None:
                            capacities.append(plant.water_capacity.native_value)
                        break

        if not capacities:
            self._attr_native_value = DEFAULT_WATER_CAPACITY
            self.async_write_ha_state()
            return

        # Berechne aggregierten Wert
        aggregation_method = self._plant.pot_size_aggregation  # Nutze die gleiche Aggregationsmethode wie für pot_size
        if aggregation_method == AGGREGATION_MEAN:
            new_capacity = sum(capacities) / len(capacities)
        elif aggregation_method == AGGREGATION_MIN:
            new_capacity = min(capacities)
        elif aggregation_method == AGGREGATION_MAX:
            new_capacity = max(capacities)
        else:  # AGGREGATION_MEDIAN
            sorted_values = sorted(capacities)
            n = len(sorted_values)
            if n % 2 == 0:
                new_capacity = (sorted_values[n//2 - 1] + sorted_values[n//2]) / 2
            else:
                new_capacity = sorted_values[n//2]

        self._attr_native_value = round(new_capacity)
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        self._attr_native_value = value
        self.async_write_ha_state()

        # Wenn ein Cycle seine Wasserkapazität ändert, aktualisiere alle Member Plants
        if self._plant.device_type == DEVICE_TYPE_CYCLE:
            device_registry = dr.async_get(self._hass)
            
            # Finde das Cycle Device
            cycle_device = device_registry.async_get_device(
                identifiers={(DOMAIN, self._plant.unique_id)}
            )
            
            if cycle_device:
                # Finde alle zugehörigen Plant Devices
                for device_entry in device_registry.devices.values():
                    if device_entry.via_device_id == cycle_device.id:
                        # Finde die zugehörige Plant Entity
                        for entry_id in self._hass.data[DOMAIN]:
                            if ATTR_PLANT in self._hass.data[DOMAIN][entry_id]:
                                plant = self._hass.data[DOMAIN][entry_id][ATTR_PLANT]
                                if (plant.device_type != DEVICE_TYPE_CYCLE and 
                                    plant.unique_id == next(iter(device_entry.identifiers))[1]):
                                    # Aktualisiere die Wasserkapazität der Plant
                                    if plant.water_capacity:
                                        await plant.water_capacity.async_set_native_value(value)
                                    break

        # Bestehende Logik für Plant -> Cycle Update
        elif self._plant.device_type == DEVICE_TYPE_PLANT:
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
                                    # Aktualisiere die Wasserkapazität des Cycles
                                    if cycle.water_capacity:
                                        await cycle.water_capacity._update_cycle_water_capacity()
                                    break
                        break

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        # Prüfe ob es eine Neuerstellung ist
        if self._config.data[FLOW_PLANT_INFO].get(ATTR_IS_NEW_PLANT, False):
            # Neue Plant - nutze Config Flow Werte
            self._attr_native_value = self._config.data[FLOW_PLANT_INFO].get(ATTR_WATER_CAPACITY, DEFAULT_WATER_CAPACITY)
        else:
            # Neustart - stelle letzten Zustand wieder her
            last_state = await self.async_get_last_state()
            if last_state is not None:
                try:
                    self._attr_native_value = float(last_state.state)
                except (TypeError, ValueError):
                    self._attr_native_value = DEFAULT_WATER_CAPACITY


