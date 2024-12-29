"""Services for plant integration."""
import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.const import ATTR_NAME

from .const import (
    DOMAIN,
    ATTR_PLANT,
    ATTR_SENSORS,
    FLOW_PLANT_INFO,
    SERVICE_REPLACE_SENSOR,
    SERVICE_REMOVE_PLANT,
    SERVICE_CREATE_PLANT,
    SERVICE_CREATE_CYCLE,
    SERVICE_MOVE_TO_CYCLE,
    SERVICE_REMOVE_CYCLE,
    ATTR_STRAIN,
    ATTR_BREEDER,
    DEFAULT_GROWTH_PHASE,
    FLOW_SENSOR_TEMPERATURE,
    FLOW_SENSOR_MOISTURE,
    FLOW_SENSOR_CONDUCTIVITY,
    FLOW_SENSOR_ILLUMINANCE,
    FLOW_SENSOR_HUMIDITY,
    DEVICE_TYPE_CYCLE,
)

_LOGGER = logging.getLogger(__name__)

# Service Schemas
REPLACE_SENSOR_SCHEMA = vol.Schema({
    vol.Required("meter_entity"): cv.string,
    vol.Optional("new_sensor"): cv.string,
})

CREATE_PLANT_SCHEMA = vol.Schema({
    vol.Required(ATTR_NAME): cv.string,
    vol.Required(ATTR_STRAIN): cv.string,
    vol.Optional(ATTR_BREEDER): cv.string,
    vol.Optional("growth_phase", default=DEFAULT_GROWTH_PHASE): cv.string,
    vol.Optional("plant_emoji", default="🌿"): cv.string,
    vol.Optional(FLOW_SENSOR_TEMPERATURE): cv.string,
    vol.Optional(FLOW_SENSOR_MOISTURE): cv.string,
    vol.Optional(FLOW_SENSOR_CONDUCTIVITY): cv.string,
    vol.Optional(FLOW_SENSOR_ILLUMINANCE): cv.string,
    vol.Optional(FLOW_SENSOR_HUMIDITY): cv.string,
})

async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for plant integration."""

    async def replace_sensor(call: ServiceCall) -> None:
        """Replace a sensor entity within a plant device"""
        meter_entity = call.data.get("meter_entity")
        new_sensor = call.data.get("new_sensor")
        found = False
        for entry_id in hass.data[DOMAIN]:
            if ATTR_SENSORS in hass.data[DOMAIN][entry_id]:
                for sensor in hass.data[DOMAIN][entry_id][ATTR_SENSORS]:
                    if sensor.entity_id == meter_entity:
                        found = True
                        break
        if not found:
            _LOGGER.warning(
                "Refuse to update non-%s entities: %s", DOMAIN, meter_entity
            )
            return False
        if new_sensor and new_sensor != "" and not new_sensor.startswith("sensor."):
            _LOGGER.warning("%s is not a sensor", new_sensor)
            return False

        try:
            meter = hass.states.get(meter_entity)
        except AttributeError:
            _LOGGER.error("Meter entity %s not found", meter_entity)
            return False
        if meter is None:
            _LOGGER.error("Meter entity %s not found", meter_entity)
            return False

        if new_sensor and new_sensor != "":
            try:
                test = hass.states.get(new_sensor)
            except AttributeError:
                _LOGGER.error("New sensor entity %s not found", meter_entity)
                return False
            if test is None:
                _LOGGER.error("New sensor entity %s not found", meter_entity)
                return False
        else:
            new_sensor = None

        _LOGGER.info(
            "Going to replace the external sensor for %s with %s",
            meter_entity,
            new_sensor,
        )
        for key in hass.data[DOMAIN]:
            if ATTR_SENSORS in hass.data[DOMAIN][key]:
                meters = hass.data[DOMAIN][key][ATTR_SENSORS]
                for meter in meters:
                    if meter.entity_id == meter_entity:
                        meter.replace_external_sensor(new_sensor)
        return

    async def remove_plant(call: ServiceCall) -> None:
        """Remove a plant entity and all its associated entities."""
        plant_entity = call.data.get("plant_entity")

        found = False
        target_entry_id = None
        target_plant = None
        for entry_id in hass.data[DOMAIN]:
            if ATTR_PLANT in hass.data[DOMAIN][entry_id]:
                plant = hass.data[DOMAIN][entry_id][ATTR_PLANT]
                if plant.entity_id == plant_entity:
                    found = True
                    target_entry_id = entry_id
                    target_plant = plant
                    break

        if not found:
            _LOGGER.warning(
                "Refuse to remove non-%s entity: %s", DOMAIN, plant_entity
            )
            return False

        # Prüfe ob die Plant einem Cycle zugeordnet ist und aktualisiere dessen Phase
        device_registry = dr.async_get(hass)
        plant_device = device_registry.async_get_device(
            identifiers={(DOMAIN, target_plant.unique_id)}
        )
        
        if plant_device and plant_device.via_device_id:
            # Suche das Cycle Device
            for device in device_registry.devices.values():
                if device.id == plant_device.via_device_id:
                    cycle_device = device
                    # Finde den zugehörigen Cycle
                    for entry_id in hass.data[DOMAIN]:
                        if ATTR_PLANT in hass.data[DOMAIN][entry_id]:
                            cycle = hass.data[DOMAIN][entry_id][ATTR_PLANT]
                            if (cycle.device_type == DEVICE_TYPE_CYCLE and 
                                cycle.unique_id == next(iter(cycle_device.identifiers))[1]):
                                # Entferne die Plant aus dem Cycle
                                cycle.remove_member_plant(plant_entity)
                                # Aktualisiere Flowering Duration
                                if cycle.flowering_duration:
                                    await cycle.flowering_duration._update_cycle_duration()
                                break
                    break

        # Entferne die Config Entry
        await hass.config_entries.async_remove(target_entry_id)
        return True

    async def create_plant(call: ServiceCall) -> None:
        """Create a new plant via service call."""
        user_input = {
            ATTR_NAME: call.data.get(ATTR_NAME),
            ATTR_STRAIN: call.data.get(ATTR_STRAIN),
            ATTR_BREEDER: call.data.get(ATTR_BREEDER, ""),
            "growth_phase": call.data.get("growth_phase", DEFAULT_GROWTH_PHASE),
            "plant_emoji": call.data.get("plant_emoji", "🌿"),
            FLOW_SENSOR_TEMPERATURE: call.data.get(FLOW_SENSOR_TEMPERATURE),
            FLOW_SENSOR_MOISTURE: call.data.get(FLOW_SENSOR_MOISTURE),
            FLOW_SENSOR_CONDUCTIVITY: call.data.get(FLOW_SENSOR_CONDUCTIVITY),
            FLOW_SENSOR_ILLUMINANCE: call.data.get(FLOW_SENSOR_ILLUMINANCE),
            FLOW_SENSOR_HUMIDITY: call.data.get(FLOW_SENSOR_HUMIDITY),
        }

        _LOGGER.debug("Creating plant with data: %s", user_input)

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "user", "source_type": "service"},
            data=user_input
        )

        if result["type"] not in ["create_entry", "abort"]:
            _LOGGER.error(
                "Failed to create plant %s: %s",
                call.data.get(ATTR_NAME),
                result.get("reason", "unknown error"),
            )
            return False

        return True

    async def create_cycle(call: ServiceCall) -> None:
        """Create a new cycle via service call."""
        user_input = {
            ATTR_NAME: call.data.get(ATTR_NAME),
            "device_type": DEVICE_TYPE_CYCLE,
            "plant_emoji": call.data.get("plant_emoji", "🔄"),
        }

        _LOGGER.debug("Creating cycle with data: %s", user_input)

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "user", "source_type": "service"},
            data=user_input
        )

        if result["type"] not in ["create_entry", "abort"]:
            _LOGGER.error(
                "Failed to create cycle %s: %s",
                call.data.get(ATTR_NAME),
                result.get("reason", "unknown error"),
            )
            return False

        # Aktualisiere alle Plant Cycle Selects
        for entry_id in hass.data[DOMAIN]:
            if ATTR_PLANT in hass.data[DOMAIN][entry_id]:
                plant = hass.data[DOMAIN][entry_id][ATTR_PLANT]
                if plant.device_type == DEVICE_TYPE_PLANT and plant.cycle_select:
                    plant.cycle_select._update_cycle_options()
                    plant.cycle_select.async_write_ha_state()

        return True

    async def move_to_cycle(call: ServiceCall) -> None:
        """Move plants to a cycle or remove them from cycle."""
        plant_entity_ids = call.data.get("plant_entity")
        cycle_entity_id = call.data.get("cycle_entity")

        # Convert to list if single string
        if isinstance(plant_entity_ids, str):
            plant_entity_ids = [plant_entity_ids]

        device_registry = dr.async_get(hass)
        entity_registry = er.async_get(hass)

        # Get cycle device if specified
        cycle_device = None
        cycle = None
        if cycle_entity_id:
            cycle_entity = entity_registry.async_get(cycle_entity_id)
            if not cycle_entity:
                _LOGGER.error(f"Cycle entity {cycle_entity_id} not found")
                return
            
            # Finde zuerst das Cycle Objekt
            for entry_id in hass.data[DOMAIN]:
                if ATTR_PLANT in hass.data[DOMAIN][entry_id]:
                    if hass.data[DOMAIN][entry_id][ATTR_PLANT].entity_id == cycle_entity_id:
                        cycle = hass.data[DOMAIN][entry_id][ATTR_PLANT]
                        break

            if not cycle:
                _LOGGER.error(f"Cycle object for {cycle_entity_id} not found")
                return

            # Hole das cycle device über die unique_id des Cycles
            cycle_device = device_registry.async_get_device(
                identifiers={(DOMAIN, cycle.unique_id)}
            )
            if not cycle_device:
                _LOGGER.error(f"Cycle device for {cycle_entity_id} not found")
                return

        # Process each plant entity
        for plant_entity_id in plant_entity_ids:
            plant_entity = entity_registry.async_get(plant_entity_id)
            if not plant_entity:
                _LOGGER.error(f"Plant entity {plant_entity_id} not found")
                continue

            plant_device = device_registry.async_get_device(
                identifiers={(DOMAIN, plant_entity.unique_id)}
            )
            if not plant_device:
                _LOGGER.error(f"Plant device for {plant_entity_id} not found")
                continue

            # Wenn die Plant bereits einem Cycle zugeordnet ist, entferne sie dort
            if plant_device.via_device_id:
                # Suche das alte Cycle Device über alle Devices
                old_cycle_device = None
                for device in device_registry.devices.values():
                    if device.id == plant_device.via_device_id:
                        old_cycle_device = device
                        break

                if old_cycle_device:
                    old_cycle = None
                    for entry_id in hass.data[DOMAIN]:
                        if ATTR_PLANT in hass.data[DOMAIN][entry_id]:
                            device = hass.data[DOMAIN][entry_id][ATTR_PLANT]
                            if device.device_type == DEVICE_TYPE_CYCLE and device.device_id == old_cycle_device.id:
                                old_cycle = device
                                break
                    
                    if old_cycle:
                        old_cycle.remove_member_plant(plant_entity_id)

            # Update device registry
            device_registry.async_update_device(
                plant_device.id,
                via_device_id=cycle_device.id if cycle_device else None
            )

            # Add plant to new cycle
            if cycle:
                cycle.add_member_plant(plant_entity_id)
                # Aktualisiere Flowering Duration
                if cycle.flowering_duration:
                    await cycle.flowering_duration._update_cycle_duration()

            if cycle_device:
                _LOGGER.info(
                    f"Plant {plant_entity_id} successfully assigned to cycle {cycle_entity_id}"
                )
            else:
                _LOGGER.info(
                    f"Plant {plant_entity_id} successfully removed from cycle"
                )

    async def remove_cycle(call: ServiceCall) -> None:
        """Remove a cycle entity and all its associated entities."""
        cycle_entity = call.data.get("cycle_entity")

        found = False
        target_entry_id = None
        for entry_id in hass.data[DOMAIN]:
            if ATTR_PLANT in hass.data[DOMAIN][entry_id]:
                device = hass.data[DOMAIN][entry_id][ATTR_PLANT]
                if device.entity_id == cycle_entity and device.device_type == DEVICE_TYPE_CYCLE:
                    found = True
                    target_entry_id = entry_id
                    break

        if not found:
            _LOGGER.warning(
                "Refuse to remove non-cycle entity: %s", cycle_entity
            )
            return False

        await hass.config_entries.async_remove(target_entry_id)

        # Aktualisiere alle Plant Cycle Selects
        for entry_id in hass.data[DOMAIN]:
            if ATTR_PLANT in hass.data[DOMAIN][entry_id]:
                plant = hass.data[DOMAIN][entry_id][ATTR_PLANT]
                if plant.device_type == DEVICE_TYPE_PLANT and plant.cycle_select:
                    plant.cycle_select._update_cycle_options()
                    plant.cycle_select.async_write_ha_state()

        return True

    # Register services
    hass.services.async_register(
        DOMAIN, 
        SERVICE_REPLACE_SENSOR, 
        replace_sensor, 
        schema=REPLACE_SENSOR_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_REMOVE_PLANT, remove_plant)
    hass.services.async_register(
        DOMAIN, 
        SERVICE_CREATE_PLANT, 
        create_plant,
        schema=CREATE_PLANT_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_CREATE_CYCLE, create_cycle)
    hass.services.async_register(DOMAIN, SERVICE_MOVE_TO_CYCLE, move_to_cycle)
    hass.services.async_register(DOMAIN, SERVICE_REMOVE_CYCLE, remove_cycle)

async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload Plant services."""
    hass.services.async_remove(DOMAIN, SERVICE_REPLACE_SENSOR)
    hass.services.async_remove(DOMAIN, SERVICE_REMOVE_PLANT)
    hass.services.async_remove(DOMAIN, SERVICE_CREATE_PLANT)
    hass.services.async_remove(DOMAIN, SERVICE_CREATE_CYCLE)
    hass.services.async_remove(DOMAIN, SERVICE_MOVE_TO_CYCLE)
    hass.services.async_remove(DOMAIN, SERVICE_REMOVE_CYCLE) 
