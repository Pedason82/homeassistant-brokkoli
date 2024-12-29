"""Select entities for plant growth phases."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.core import callback

from .const import (
    ATTR_PLANT,
    DEFAULT_GROWTH_PHASE,
    DOMAIN,
    GROWTH_PHASES,
    GROWTH_PHASE_GERMINATION,
    GROWTH_PHASE_ROOTING,
    GROWTH_PHASE_GROWING,
    GROWTH_PHASE_FLOWERING,
    GROWTH_PHASE_REMOVED,
    GROWTH_PHASE_HARVESTED,
    FLOW_PLANT_INFO,
    ATTR_IS_NEW_PLANT,
    DEVICE_TYPE_PLANT,
    DEVICE_TYPE_CYCLE,
    CYCLE_DOMAIN,
    SERVICE_MOVE_TO_CYCLE,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the plant growth phase select entity."""
    plant = hass.data[DOMAIN][entry.entry_id][ATTR_PLANT]
    entities = []
    
    # Growth Phase Select für alle Devices
    growth_phase_select = PlantGrowthPhaseSelect(hass, entry, plant)
    entities.append(growth_phase_select)
    plant.add_growth_phase_select(growth_phase_select)

    # Cycle Select nur für Plants, nicht für Cycles
    if plant.device_type == DEVICE_TYPE_PLANT:
        cycle_select = PlantCycleSelect(hass, entry, plant)
        entities.append(cycle_select)
    
    async_add_entities(entities)

class PlantGrowthPhaseSelect(SelectEntity, RestoreEntity):
    """Representation of a plant growth phase selector."""

    # Mapping für Phasen zu Datums-Attributen
    date_mapping = {
        GROWTH_PHASE_GERMINATION: "keimen_beginn",
        GROWTH_PHASE_ROOTING: "wurzeln_beginn",
        GROWTH_PHASE_GROWING: "wachstum_beginn",
        GROWTH_PHASE_FLOWERING: "blüte_beginn",
        GROWTH_PHASE_REMOVED: "entfernt",
        GROWTH_PHASE_HARVESTED: "geerntet"
    }

    def __init__(self, hass: HomeAssistant, config: ConfigEntry, plant_device) -> None:
        """Initialize the growth phase select entity."""
        self._attr_options = GROWTH_PHASES
        initial_phase = config.data[FLOW_PLANT_INFO].get("growth_phase", DEFAULT_GROWTH_PHASE)
        self._attr_current_option = initial_phase
        self._config = config
        self._hass = hass
        self._plant = plant_device
        self._attr_name = f"{plant_device.name} Growth Phase"
        self._attr_unique_id = f"{config.entry_id}-growth-phase"
        
        # Ordinal Mapping für die Phasen (ohne REMOVED)
        self.phase_order = {
            GROWTH_PHASE_GERMINATION: 0,
            GROWTH_PHASE_ROOTING: 1, 
            GROWTH_PHASE_GROWING: 2,
            GROWTH_PHASE_FLOWERING: 3,
            GROWTH_PHASE_HARVESTED: 4
        }
        
        # Initialize date attributes
        current_date = datetime.now().strftime("%Y-%m-%d")
        self._attr_extra_state_attributes = {
            "friendly_name": self._attr_name,
            "keimen_beginn": None,
            "wurzeln_beginn": None,
            "wachstum_beginn": None,
            "blüte_beginn": None,
            "entfernt": None,
            "geerntet": None,
            "aggregation_method": config.data[FLOW_PLANT_INFO].get("growth_phase_aggregation", "min")
        }
        
        # Setze das initiale Datum für die Startphase
        if initial_phase in self.date_mapping:
            self._attr_extra_state_attributes[self.date_mapping[initial_phase]] = current_date

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        # Prüfe ob es eine Neuerstellung ist
        if self._config.data[FLOW_PLANT_INFO].get(ATTR_IS_NEW_PLANT, False):
            # Neue Plant - nutze Config Flow Werte
            self._attr_current_option = self._config.data[FLOW_PLANT_INFO].get("growth_phase", DEFAULT_GROWTH_PHASE)
            current_date = datetime.now().strftime("%Y-%m-%d")
            if self._attr_current_option in self.date_mapping:
                self._attr_extra_state_attributes[self.date_mapping[self._attr_current_option]] = current_date
        else:
            # Neustart - stelle letzten Zustand wieder her
            last_state = await self.async_get_last_state()
            if last_state:
                self._attr_current_option = last_state.state
                if last_state.attributes:
                    self._attr_extra_state_attributes.update(last_state.attributes)

    async def _update_cycle_phase(self, _now=None):
        """Aktualisiere die Growth Phase für Cycles basierend auf den Member Plants."""
        if not self._plant._member_plants:
            _LOGGER.debug("No member plants for cycle %s", self._plant.entity_id)
            return

        # Sammle die Phasen aller Member Plants
        member_phases = []
        for plant_id in self._plant._member_plants:
            # Suche die Plant Entity
            for entry_id in self._hass.data[DOMAIN]:
                if ATTR_PLANT in self._hass.data[DOMAIN][entry_id]:
                    plant = self._hass.data[DOMAIN][entry_id][ATTR_PLANT]
                    if plant.entity_id == plant_id:
                        if plant.growth_phase_select:
                            phase = plant.growth_phase_select.current_option
                            if phase != GROWTH_PHASE_REMOVED:  # Ignoriere "Entfernt"
                                member_phases.append(phase)
                                _LOGGER.debug("Added phase %s from plant %s", phase, plant_id)
                        break

        if not member_phases:
            _LOGGER.debug("No valid phases found for cycle %s", self._plant.entity_id)
            return

        # Bestimme die aggregierte Phase
        aggregation_method = self._attr_extra_state_attributes.get("aggregation_method", "min")
        _LOGGER.debug(
            "Calculating aggregated phase for cycle %s using method %s from phases: %s",
            self._plant.entity_id,
            aggregation_method,
            member_phases
        )
        
        if aggregation_method == "min":
            # Finde die niedrigste Phase (früheste im Zyklus)
            new_phase = min(member_phases, key=lambda x: self.phase_order.get(x, 999))
        else:
            # Finde die höchste Phase (späteste im Zyklus)
            new_phase = max(member_phases, key=lambda x: self.phase_order.get(x, -1))

        _LOGGER.debug(
            "New phase for cycle %s: %s (current: %s)", 
            self._plant.entity_id, 
            new_phase, 
            self._attr_current_option
        )

        # Aktualisiere die Phase wenn sie sich geändert hat
        if new_phase != self._attr_current_option:
            self._attr_current_option = new_phase
            current_date = datetime.now().strftime("%Y-%m-%d")
            if new_phase in self.date_mapping:
                self._attr_extra_state_attributes[self.date_mapping[new_phase]] = current_date
            self.async_write_ha_state()
            _LOGGER.debug("Updated cycle %s phase to %s", self._plant.entity_id, new_phase)

    @property
    def extra_state_attributes(self):
        """Return entity specific state attributes."""
        attrs = self._attr_extra_state_attributes.copy()
        
        # Füge Member Plants für Cycles hinzu
        if self._plant.device_type == DEVICE_TYPE_CYCLE:
            attrs["member_plants"] = self._plant._member_plants
            
        return attrs

    @property
    def device_info(self) -> dict:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._plant.unique_id)},
        }

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        _LOGGER.debug(
            "%s: Changing growth phase to %s (device_type: %s)", 
            self._plant.entity_id,
            option,
            self._plant.device_type
        )
        
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        if option in self.date_mapping:
            self._attr_extra_state_attributes[self.date_mapping[option]] = current_date
            
        self._attr_current_option = option
        self.async_write_ha_state()

        # Wenn eine Plant ihre Phase ändert, aktualisiere den zugehörigen Cycle
        if self._plant.device_type == DEVICE_TYPE_PLANT:
            device_registry = dr.async_get(self._hass)
            plant_device = device_registry.async_get_device(
                identifiers={(DOMAIN, self._plant.unique_id)}
            )
            
            _LOGGER.debug(
                "%s: Plant device: %s, via_device_id: %s",
                self._plant.entity_id,
                plant_device,
                plant_device.via_device_id if plant_device else None
            )
            
            if plant_device and plant_device.via_device_id:
                # Finde das Cycle Device direkt über die ID
                for device in device_registry.devices.values():
                    if device.id == plant_device.via_device_id:
                        cycle_device = device
                        _LOGGER.debug(
                            "%s: Found cycle device: %s",
                            self._plant.entity_id,
                            cycle_device
                        )
                        
                        # Finde den Cycle und aktualisiere seine Phase
                        for entry_id in self._hass.data[DOMAIN]:
                            if ATTR_PLANT in self._hass.data[DOMAIN][entry_id]:
                                cycle = self._hass.data[DOMAIN][entry_id][ATTR_PLANT]
                                _LOGGER.debug(
                                    "%s: Checking cycle %s (type: %s, unique_id: %s vs %s)",
                                    self._plant.entity_id,
                                    cycle.entity_id,
                                    cycle.device_type,
                                    cycle.unique_id,
                                    next(iter(cycle_device.identifiers))[1]
                                )
                                
                                if (cycle.device_type == DEVICE_TYPE_CYCLE and 
                                    cycle.unique_id == next(iter(cycle_device.identifiers))[1]):
                                    if cycle.growth_phase_select:
                                        _LOGGER.debug(
                                            "%s: Found matching cycle, updating phase",
                                            self._plant.entity_id
                                        )
                                        await cycle.growth_phase_select._update_cycle_phase()
                                    break
                        break

class PlantCycleSelect(SelectEntity, RestoreEntity):
    """Select entity to assign a plant to a cycle."""

    def __init__(self, hass: HomeAssistant, config: ConfigEntry, plant_device) -> None:
        """Initialize the cycle select entity."""
        self._hass = hass
        self._config = config
        self._plant = plant_device
        self._attr_name = f"{plant_device.name} Cycle"
        self._attr_unique_id = f"{config.entry_id}-cycle-select"
        self._attr_options = []
        self._cycle_mapping = {}
        self._attr_current_option = None
        self._update_cycle_options()  # Initial update

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
            # Neue Plant - initialisiere ohne Cycle
            self._attr_current_option = ""
        else:
            # Neustart - stelle letzten Zustand wieder her
            last_state = await self.async_get_last_state()
            if last_state:
                # Prüfe ob die letzte Option noch verfügbar ist
                if last_state.state in self._attr_options:
                    self._attr_current_option = last_state.state
                else:
                    # Setze auf aktuellen Cycle basierend auf Device Registry
                    self._attr_current_option = self.current_option or ""

        # Füge den Select zum Plant Device hinzu
        self._plant.add_cycle_select(self)

    @property
    def current_option(self) -> str | None:
        """Return the current selected cycle."""
        device_registry = dr.async_get(self._hass)
        plant_device = device_registry.async_get_device(
            identifiers={(DOMAIN, self._plant.unique_id)}
        )
        
        if plant_device and plant_device.via_device_id:
            # Suche das Cycle Device über alle Devices
            for device in device_registry.devices.values():
                if device.id == plant_device.via_device_id:
                    # Finde den Cycle Namen anhand der Seriennummer
                    for option in self._attr_options:
                        if option.endswith(f"({device.serial_number})"):
                            return option
                    break
        return None

    def _update_cycle_options(self) -> None:
        """Update the list of available cycles."""
        _LOGGER.debug("_update_cycle_options called for %s", self.entity_id)
        
        device_registry = dr.async_get(self._hass)
        entity_registry = er.async_get(self._hass)
        
        cycles = []
        # Finde alle Cycle Devices
        for device in device_registry.devices.values():
            for identifier in device.identifiers:
                if identifier[0] == DOMAIN:
                    # Prüfe ob es ein Cycle ist
                    for entity_entry in entity_registry.entities.values():
                        if (entity_entry.device_id == device.id and 
                            entity_entry.domain == CYCLE_DOMAIN):
                            cycles.append((
                                device.name.replace(" 🔄", ""),  # Entferne Emoji
                                device.serial_number or "",
                                entity_entry.entity_id
                            ))
                            _LOGGER.debug("Found cycle: %s", device.name)
                            break

        # Sortiere nach Seriennummer und erstelle Optionen
        cycles.sort(key=lambda x: x[1])
        self._attr_options = [""] + [f"{name} ({serial})" for name, serial, _ in cycles]
        self._cycle_mapping = {
            f"{name} ({serial})": entity_id for name, serial, entity_id in cycles
        }
        _LOGGER.debug("Updated options to: %s", self._attr_options)

    async def async_select_option(self, option: str) -> None:
        """Handle cycle selection."""
        if option == self.current_option:
            return

        # Hole cycle_entity_id aus dem Mapping
        cycle_entity_id = self._cycle_mapping.get(option)

        # Rufe move_to_cycle Service auf
        await self._hass.services.async_call(
            DOMAIN,
            SERVICE_MOVE_TO_CYCLE,
            {
                "plant_entity": self._plant.entity_id,
                "cycle_entity": cycle_entity_id if option else None
            },
            blocking=True
        )

        # Flowering Duration wird automatisch im move_to_cycle Service aktualisiert
