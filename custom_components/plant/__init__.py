"""Support for monitoring plants."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.utility_meter.const import (
    DATA_TARIFF_SENSORS,
    DATA_UTILITY,
)
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import (
    Platform,
    ATTR_ENTITY_PICTURE,
    ATTR_NAME,
    ATTR_UNIT_OF_MEASUREMENT,
    ATTR_ICON,
    STATE_OK,
    STATE_PROBLEM,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.entity import Entity, async_generate_entity_id
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.storage import Store
from homeassistant.helpers.event import async_call_later

from .const import (
    ATTR_CONDUCTIVITY,
    ATTR_CURRENT,
    ATTR_DLI,
    ATTR_HUMIDITY,
    ATTR_ILLUMINANCE,
    ATTR_LIMITS,
    ATTR_MAX,
    ATTR_METERS,
    ATTR_MIN,
    ATTR_MOISTURE,
    ATTR_PLANT,
    ATTR_SENSOR,
    ATTR_SENSORS,
    ATTR_STRAIN,
    ATTR_TEMPERATURE,
    ATTR_THRESHOLDS,
    DATA_SOURCE,
    DOMAIN,
    DOMAIN_PLANTBOOK,
    FLOW_CONDUCTIVITY_TRIGGER,
    FLOW_DLI_TRIGGER,
    FLOW_HUMIDITY_TRIGGER,
    FLOW_ILLUMINANCE_TRIGGER,
    FLOW_MOISTURE_TRIGGER,
    FLOW_PLANT_INFO,
    FLOW_TEMPERATURE_TRIGGER,
    OPB_DISPLAY_PID,
    READING_CONDUCTIVITY,
    READING_DLI,
    READING_HUMIDITY,
    READING_ILLUMINANCE,
    READING_MOISTURE,
    READING_TEMPERATURE,
    STATE_HIGH,
    STATE_LOW,
    ATTR_FLOWERING_DURATION,
    ATTR_BREEDER,
    ATTR_PID,
    ATTR_PHENOTYPE,
    ATTR_HUNGER,
    ATTR_GROWTH_STRETCH,
    ATTR_FLOWER_STRETCH,
    ATTR_MOLD_RESISTANCE,
    ATTR_DIFFICULTY,
    ATTR_YIELD,
    ATTR_NOTES,
    ATTR_IS_NEW_PLANT,
    FLOW_SENSOR_TEMPERATURE,
    FLOW_SENSOR_MOISTURE,
    FLOW_SENSOR_CONDUCTIVITY,
    FLOW_SENSOR_ILLUMINANCE,
    FLOW_SENSOR_HUMIDITY,
    DEFAULT_GROWTH_PHASE,
    DEVICE_TYPE_PLANT,
    DEVICE_TYPE_CYCLE,
    ATTR_DEVICE_TYPE,
    ICON_DEVICE_PLANT,
    ICON_DEVICE_CYCLE,
    CYCLE_DOMAIN,
    AGGREGATION_MEDIAN,
    AGGREGATION_MEAN,
    AGGREGATION_MIN,
    AGGREGATION_MAX,
    AGGREGATION_ORIGINAL,
    DEFAULT_AGGREGATIONS,
)
from .plant_helpers import PlantHelper
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.NUMBER, Platform.SENSOR, Platform.SELECT]

# Use this during testing to generate some dummy-sensors
# to provide random readings for temperature, moisture etc.
SETUP_DUMMY_SENSORS = False
USE_DUMMY_SENSORS = False

@callback
def _async_find_matching_config_entry(hass: HomeAssistant) -> ConfigEntry | None:
    """Check if there are migrated entities"""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.source == SOURCE_IMPORT:
            return entry

async def _get_next_id(hass: HomeAssistant, device_type: str) -> str:
    """Get next ID from storage based on device type."""
    store = Store(hass, version=1, key=f"{DOMAIN}_{device_type}_counter")
    data = await store.async_load() or {"counter": 0}
    
    next_id = data["counter"] + 1
    await store.async_save({"counter": next_id})
    
    return f"{next_id:04d}"  # Formatiert als 4-stellige Nummer mit führenden Nullen

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Plant from a config entry."""
    
    # Wenn dies ein Konfigurationsknoten ist, keine Entities erstellen
    if entry.data.get("is_config", False):
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
            "config": entry.data[FLOW_PLANT_INFO]
        }
        # Keine Platforms laden für den Konfigurationsknoten
        return True

    # Normale Plant/Cycle Initialisierung fortsetzen
    plant_data = entry.data[FLOW_PLANT_INFO]
    
    hass.data.setdefault(DOMAIN, {})
    if FLOW_PLANT_INFO not in entry.data:
        return True

    hass.data[DOMAIN].setdefault(entry.entry_id, {})
    _LOGGER.debug("Setting up config entry %s: %s", entry.entry_id, entry)

    # Erstelle PlantDevice und hole oder generiere ID
    plant = PlantDevice(hass, entry)
    
    # Prüfe ob bereits eine ID existiert
    device_type = entry.data[FLOW_PLANT_INFO].get(ATTR_DEVICE_TYPE, DEVICE_TYPE_PLANT)
    id_key = f"{device_type}_id"
    
    if id_key not in entry.data[FLOW_PLANT_INFO]:
        # Generiere neue ID nur wenn keine existiert
        new_id = await _get_next_id(hass, device_type)
        # Speichere ID in der Config Entry
        data = dict(entry.data)
        data[FLOW_PLANT_INFO][id_key] = new_id
        hass.config_entries.async_update_entry(entry, data=data)
    
    # Setze die ID (entweder die existierende oder neue)
    plant._plant_id = entry.data[FLOW_PLANT_INFO].get(id_key)

    # Korrekte Device-Registrierung
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        **plant.device_info
    )

    hass.data[DOMAIN][entry.entry_id][ATTR_PLANT] = plant

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    plant_entities = [
        plant,
    ]

    # Add all the entities to Hass
    component = EntityComponent(_LOGGER, plant.device_type, hass)
    await component.async_add_entities(plant_entities)

    # Add the rest of the entities to device registry together with plant
    device_id = plant.device_id
    await _plant_add_to_device_registry(hass, plant_entities, device_id)
    await _plant_add_to_device_registry(hass, plant.integral_entities, device_id)
    await _plant_add_to_device_registry(hass, plant.threshold_entities, device_id)
    await _plant_add_to_device_registry(hass, plant.meter_entities, device_id)

    #
    # Set up utility sensor
    hass.data.setdefault(DATA_UTILITY, {})
    hass.data[DATA_UTILITY].setdefault(entry.entry_id, {})
    hass.data[DATA_UTILITY][entry.entry_id].setdefault(DATA_TARIFF_SENSORS, [])
    hass.data[DATA_UTILITY][entry.entry_id][DATA_TARIFF_SENSORS].append(plant.dli)

    # Service Setup auslagern - ersetze den alten Service-Code durch:
    await async_setup_services(hass)
    
    websocket_api.async_register_command(hass, ws_get_info)
    plant.async_schedule_update_ha_state(True)

    # Lets add the dummy sensors automatically if we are testing stuff
    if USE_DUMMY_SENSORS is True:
        for sensor in plant.meter_entities:
            if sensor.external_sensor is None:
                await hass.services.async_call(
                    domain=DOMAIN,
                    service=SERVICE_REPLACE_SENSOR,
                    service_data={
                        "meter_entity": sensor.entity_id,
                        "new_sensor": sensor.entity_id.replace(
                            "sensor.", "sensor.dummy_"
                        ),
                    },
                    blocking=False,
                    limit=30,
                )

    # Setze das Flag zurück nach vollständigem Setup
    if entry.data[FLOW_PLANT_INFO].get(ATTR_IS_NEW_PLANT, False):
        data = dict(entry.data)
        data[FLOW_PLANT_INFO][ATTR_IS_NEW_PLANT] = False
        hass.config_entries.async_update_entry(entry, data=data)

    # Für Cycles: Stelle Member Plants wieder her
    if plant.device_type == DEVICE_TYPE_CYCLE:
        async def restore_member_plants(_now=None):
            """Stelle die Member Plants wieder her nachdem alle Entities initialisiert sind."""
            device_registry = dr.async_get(hass)
            entity_registry = er.async_get(hass)
            
            # Finde alle Plants die diesem Cycle zugeordnet sind
            cycle_device = device_registry.async_get_device(
                identifiers={(DOMAIN, plant.unique_id)}
            )
            
            if cycle_device:
                # Finde alle Devices die dieses Cycle als via_device haben
                for device_entry in device_registry.devices.values():
                    if device_entry.via_device_id == cycle_device.id:
                        # Finde die zugehörige Plant Entity
                        for entity_entry in entity_registry.entities.values():
                            if entity_entry.device_id == device_entry.id:
                                # Prüfe ob die Plant Entity und ihre Sensoren bereits existieren
                                plant_state = hass.states.get(entity_entry.entity_id)
                                if plant_state is not None:
                                    # Prüfe ob die wichtigsten Sensoren existieren
                                    base_name = entity_entry.entity_id.replace(f"{DOMAIN}.", "")
                                    required_entities = [
                                        f"sensor.{base_name}_air_humidity",
                                        f"sensor.{base_name}_ppfd_mol",
                                        f"sensor.{base_name}_total_ppfd_mol_integral",
                                        f"sensor.{base_name}_dli",
                                        f"select.{base_name}_growth_phase"
                                    ]
                                    
                                    all_entities_exist = all(
                                        hass.states.get(entity_id) is not None 
                                        for entity_id in required_entities
                                    )
                                    
                                    if all_entities_exist:
                                        plant.add_member_plant(entity_entry.entity_id)
                                        _LOGGER.debug(
                                            "Restored plant %s to cycle %s",
                                            entity_entry.entity_id,
                                            plant.entity_id
                                        )
                                    else:
                                        _LOGGER.debug(
                                            "Not all required entities exist yet for plant %s",
                                            entity_entry.entity_id
                                        )

        # Verzögere die Wiederherstellung um 30 Sekunden
        async_call_later(hass, 30, restore_member_plants)

    # Wenn ein neuer Cycle erstellt wurde, aktualisiere alle Plant Cycle Selects
    if plant.device_type == DEVICE_TYPE_CYCLE:
        for entry_id in hass.data[DOMAIN]:
            if ATTR_PLANT in hass.data[DOMAIN][entry_id]:
                other_plant = hass.data[DOMAIN][entry_id][ATTR_PLANT]
                if other_plant.device_type == DEVICE_TYPE_PLANT and other_plant.cycle_select:
                    other_plant.cycle_select._update_cycle_options()
                    other_plant.cycle_select.async_write_ha_state()

    return True


async def _plant_add_to_device_registry(
    hass: HomeAssistant, plant_entities: list[Entity], device_id: str
) -> None:
    """Add all related entities to the correct device_id"""

    # There must be a better way to do this, but I just can't find a way to set the
    # device_id when adding the entities.
    erreg = er.async_get(hass)
    for entity in plant_entities:
        if entity is not None and hasattr(entity, 'registry_entry') and entity.registry_entry is not None:
            erreg.async_update_entity(entity.registry_entry.entity_id, device_id=device_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    
    # Wenn dies ein Konfigurationsknoten ist, einfach die Daten entfernen
    if entry.data.get("is_config", False):
        hass.data[DOMAIN].pop(entry.entry_id, None)
        return True

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Entferne zuerst die Daten
        hass.data[DOMAIN].pop(entry.entry_id)
        hass.data[DATA_UTILITY].pop(entry.entry_id)
        
        # Wenn ein Cycle entfernt wird, aktualisiere alle Plant Cycle Selects
        if FLOW_PLANT_INFO in entry.data and entry.data[FLOW_PLANT_INFO].get("device_type") == DEVICE_TYPE_CYCLE:
            _LOGGER.debug("Unloading cycle entry, updating cycle selects")
            
            async def update_cycle_selects(_now=None):
                for entry_id in hass.data[DOMAIN]:
                    if ATTR_PLANT in hass.data[DOMAIN][entry_id]:
                        plant = hass.data[DOMAIN][entry_id][ATTR_PLANT]
                        if plant.device_type == DEVICE_TYPE_PLANT and plant.cycle_select:
                            plant.cycle_select._update_cycle_options()
                            plant.cycle_select.async_write_ha_state()
            
            # Verzögere die Aktualisierung um 1 Sekunde
            async_call_later(hass, 1, update_cycle_selects)

        # Rest der Cleanup-Logik
        for entry_id in list(hass.data[DOMAIN].keys()):
            if len(hass.data[DOMAIN][entry_id]) == 0:
                _LOGGER.info("Removing entry %s", entry_id)
                del hass.data[DOMAIN][entry_id]
        if len(hass.data[DOMAIN]) == 0:
            _LOGGER.info("Removing domain %s", DOMAIN)
            await async_unload_services(hass)
            del hass.data[DOMAIN]
            
    return unload_ok


@websocket_api.websocket_command(
    {
        vol.Required("type"): "plant/get_info",
        vol.Required("entity_id"): str,
    }
)
@callback
def ws_get_info(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Handle the websocket command."""
    # _LOGGER.debug("Got websocket request: %s", msg)

    if DOMAIN not in hass.data:
        connection.send_error(
            msg["id"], "domain_not_found", f"Domain {DOMAIN} not found"
        )
        return

    for key in hass.data[DOMAIN]:
        if not ATTR_PLANT in hass.data[DOMAIN][key]:
            continue
        plant_entity = hass.data[DOMAIN][key][ATTR_PLANT]
        if plant_entity.entity_id == msg["entity_id"]:
            # _LOGGER.debug("Sending websocket response: %s", plant_entity.websocket_info)
            try:
                connection.send_result(
                    msg["id"], {"result": plant_entity.websocket_info}
                )
            except ValueError as e:
                _LOGGER.warning(e)
            return
    connection.send_error(
        msg["id"], "entity_not_found", f"Entity {msg['entity_id']} not found"
    )
    return


class PlantDevice(Entity):
    """Base device for plants"""

    def __init__(self, hass: HomeAssistant, config: ConfigEntry) -> None:
        """Initialize the Plant/Cycle component."""
        self._config = config
        self._hass = hass
        self._attr_name = config.data[FLOW_PLANT_INFO][ATTR_NAME]
        self._config_entries = []
        self._data_source = config.data[FLOW_PLANT_INFO].get(DATA_SOURCE)
        self._plant_id = None  # Neue Property für die ID
        
        # Get data from config - nur einmal initialisieren
        self._plant_info = config.data.get(FLOW_PLANT_INFO, {})
        
        # Get entity_picture from options or from initial config
        self._attr_entity_picture = self._config.options.get(
            ATTR_ENTITY_PICTURE,
            self._plant_info.get(ATTR_ENTITY_PICTURE),
        )
        
        # Get display_strain from options or from initial config
        self.display_strain = (
            self._config.options.get(
                OPB_DISPLAY_PID, self._plant_info.get(OPB_DISPLAY_PID)
            )
            or self.pid
        )
        
        self._attr_unique_id = self._config.entry_id

        self.device_type = config.data[FLOW_PLANT_INFO].get(ATTR_DEVICE_TYPE, DEVICE_TYPE_PLANT)
        
        # Generiere Entity ID basierend auf Device Type
        domain = DOMAIN if self.device_type == DEVICE_TYPE_PLANT else CYCLE_DOMAIN
        self.entity_id = async_generate_entity_id(
            f"{domain}.{{}}", self.name, current_ids={}
        )

        self.plant_complete = False
        self._device_id = None

        self._check_days = None

        self.max_moisture = None
        self.min_moisture = None
        self.max_temperature = None
        self.min_temperature = None
        self.max_conductivity = None
        self.min_conductivity = None
        self.max_illuminance = None
        self.min_illuminance = None
        self.max_humidity = None
        self.min_humidity = None
        self.max_dli = None
        self.min_dli = None

        self.sensor_moisture = None
        self.sensor_temperature = None
        self.sensor_conductivity = None
        self.sensor_illuminance = None
        self.sensor_humidity = None

        self.dli = None
        self.micro_dli = None
        self.ppfd = None
        self.total_integral = None

        self.conductivity_status = None
        self.illuminance_status = None
        self.moisture_status = None
        self.temperature_status = None
        self.humidity_status = None
        self.dli_status = None

        self.flowering_duration = None

        # Neue Attribute hinzufügen
        self.website = self._plant_info.get("website", "")
        self.effects = self._plant_info.get("effects", "")
        self.smell = self._plant_info.get("smell", "")
        self.taste = self._plant_info.get("taste", "")
        self.lineage = self._plant_info.get("lineage", "")

        # Diese Attribute nur für Plants setzen
        if self.device_type == DEVICE_TYPE_PLANT:
            self.infotext1 = self._plant_info.get("infotext1", "")
            self.infotext2 = self._plant_info.get("infotext2", "")

        # Benutzerdefinierte Attribute
        self.phenotype = self._plant_info.get(ATTR_PHENOTYPE, "")
        self.hunger = self._plant_info.get(ATTR_HUNGER, "")
        self.growth_stretch = self._plant_info.get(ATTR_GROWTH_STRETCH, "")
        self.flower_stretch = self._plant_info.get(ATTR_FLOWER_STRETCH, "")
        self.mold_resistance = self._plant_info.get(ATTR_MOLD_RESISTANCE, "")
        self.difficulty = self._plant_info.get(ATTR_DIFFICULTY, "")
        self.yield_info = self._plant_info.get(ATTR_YIELD, "")  # yield ist ein Python keyword
        self.notes = self._plant_info.get(ATTR_NOTES, "")

        # Liste der zugehörigen Plants (nur für Cycles)
        self._member_plants = []
        
        # Median Sensoren (nur für Cycles) 
        self._median_sensors = {}

        self.cycle_select = None  # Neue Property

        # Aggregationsmethode für flowering_duration
        self.flowering_duration_aggregation = (
            self._config.options.get("flowering_duration_aggregation") or
            self._plant_info.get("flowering_duration_aggregation", "mean")
        )
        
        # Aggregationsmethode für pot_size
        self.pot_size_aggregation = (
            self._config.options.get("pot_size_aggregation") or
            self._plant_info.get("pot_size_aggregation", "mean")
        )

        # Aggregationsmethode für water_capacity
        self.water_capacity_aggregation = (
            self._config.options.get("water_capacity_aggregation") or
            self._plant_info.get("water_capacity_aggregation", "mean")
        )

        # Neue Property für pot_size
        self.pot_size = None

        # Neue Property für water_capacity
        self.water_capacity = None

    @property
    def entity_category(self) -> None:
        """The plant device itself does not have a category"""
        return None

    @property
    def device_class(self):
        """Return the device class."""
        return self.device_type  # Nutzt direkt den device_type (plant oder cycle)

    @property
    def device_id(self) -> str:
        """The device ID used for all the entities"""
        return self._device_id

    @property
    def device_info(self) -> dict:
        """Return device info."""
        device_type = self.device_type
        
        # Basis device_info
        info = {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": self.name,
            "serial_number": self._plant_id,
        }
        
        # Spezifische Attribute je nach Device Type
        if device_type == DEVICE_TYPE_PLANT:
            info.update({
                "manufacturer": self._plant_info.get(ATTR_BREEDER, "Unknown"),
                "model": self._plant_info.get(ATTR_STRAIN, ""),
                "model_id": self._plant_info.get("sorte", ""),
            })
        else:  # DEVICE_TYPE_CYCLE
            info.update({
                "manufacturer": "Home Assistant",
                "model": "Cycle",
                "model_id": self._plant_info.get("sorte", ""),
            })
        
        # Optional website hinzufügen wenn vorhanden
        if self.website:
            info["configuration_url"] = self.website
        
        return info

    @property
    def illuminance_trigger(self) -> bool:
        """Whether we will generate alarms based on illuminance"""
        return self._config.options.get(FLOW_ILLUMINANCE_TRIGGER, True)

    @property
    def humidity_trigger(self) -> bool:
        """Whether we will generate alarms based on humidity"""
        return self._config.options.get(FLOW_HUMIDITY_TRIGGER, True)

    @property
    def temperature_trigger(self) -> bool:
        """Whether we will generate alarms based on temperature"""
        return self._config.options.get(FLOW_TEMPERATURE_TRIGGER, True)

    @property
    def dli_trigger(self) -> bool:
        """Whether we will generate alarms based on dli"""
        return self._config.options.get(FLOW_DLI_TRIGGER, True)

    @property
    def moisture_trigger(self) -> bool:
        """Whether we will generate alarms based on moisture"""
        return self._config.options.get(FLOW_MOISTURE_TRIGGER, True)

    @property
    def conductivity_trigger(self) -> bool:
        """Whether we will generate alarms based on conductivity"""
        return self._config.options.get(FLOW_CONDUCTIVITY_TRIGGER, True)

    @property
    def breeder(self) -> str:
        """Return the breeder."""
        return self._plant_info.get(ATTR_BREEDER, "")

    @property
    def sorte(self) -> str:
        """Return the sorte."""
        return self._plant_info.get("sorte", "")

    @property
    def feminized(self) -> str:
        """Return the feminized status."""
        return self._plant_info.get("feminized", "")

    @property
    def timestamp(self) -> str:
        """Return the timestamp."""
        return self._plant_info.get("timestamp", "")

    @property
    def pid(self) -> str:
        """Return the pid."""
        return self._plant_info.get(ATTR_PID, "")

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = {
            "strain": self._plant_info.get(ATTR_STRAIN, ""),
            "breeder": self._plant_info.get(ATTR_BREEDER, ""),
            "flowering_duration": self.flowering_duration.native_value if self.flowering_duration else None,
            "moisture_status": self.moisture_status,
            "temperature_status": self.temperature_status,
            "conductivity_status": self.conductivity_status,
            "illuminance_status": self.illuminance_status,
            "humidity_status": self.humidity_status,
            "dli_status": self.dli_status,
            "pid": self.pid,
            "sorte": self._plant_info.get("sorte", ""),
            "feminized": self._plant_info.get("feminized", ""),
            "timestamp": self._plant_info.get("timestamp", ""),
            "effects": self._plant_info.get("effects", ""),
            "smell": self._plant_info.get("smell", ""),
            "taste": self._plant_info.get("taste", ""),
            "phenotype": self._plant_info.get(ATTR_PHENOTYPE, ""),
            "hunger": self._plant_info.get(ATTR_HUNGER, ""),
            "growth_stretch": self._plant_info.get(ATTR_GROWTH_STRETCH, ""),
            "flower_stretch": self._plant_info.get(ATTR_FLOWER_STRETCH, ""),
            "mold_resistance": self._plant_info.get(ATTR_MOLD_RESISTANCE, ""),
            "difficulty": self._plant_info.get(ATTR_DIFFICULTY, ""),
            "yield": self._plant_info.get(ATTR_YIELD, ""),
            "notes": self._plant_info.get(ATTR_NOTES, ""),
            "website": self._plant_info.get("website", ""),
        }

        # Füge Plant-spezifische Attribute nur für Plants hinzu
        if self.device_type == DEVICE_TYPE_PLANT:
            attrs.update({
                "infotext1": self._plant_info.get("infotext1", ""),
                "infotext2": self._plant_info.get("infotext2", ""),
                "lineage": self._plant_info.get("lineage", ""),
            })

        return attrs

    @property
    def websocket_info(self) -> dict:
        """Wesocket response"""
        if not self.plant_complete:
            # We are not fully set up, so we just return an empty dict for now
            return {}

        response = {
            ATTR_TEMPERATURE: {
                ATTR_MAX: self.max_temperature.state,
                ATTR_MIN: self.min_temperature.state,
                ATTR_CURRENT: self.sensor_temperature.state or STATE_UNAVAILABLE,
                ATTR_ICON: self.sensor_temperature.icon,
                ATTR_UNIT_OF_MEASUREMENT: self.sensor_temperature.unit_of_measurement,
                ATTR_SENSOR: self.sensor_temperature.entity_id,
            },
            ATTR_ILLUMINANCE: {
                ATTR_MAX: self.max_illuminance.state,
                ATTR_MIN: self.min_illuminance.state,
                ATTR_CURRENT: self.sensor_illuminance.state or STATE_UNAVAILABLE,
                ATTR_ICON: self.sensor_illuminance.icon,
                ATTR_UNIT_OF_MEASUREMENT: self.sensor_illuminance.unit_of_measurement,
                ATTR_SENSOR: self.sensor_illuminance.entity_id,
            },
            ATTR_MOISTURE: {
                ATTR_MAX: self.max_moisture.state,
                ATTR_MIN: self.min_moisture.state,
                ATTR_CURRENT: self.sensor_moisture.state or STATE_UNAVAILABLE,
                ATTR_ICON: self.sensor_moisture.icon,
                ATTR_UNIT_OF_MEASUREMENT: self.sensor_moisture.unit_of_measurement,
                ATTR_SENSOR: self.sensor_moisture.entity_id,
            },
            ATTR_CONDUCTIVITY: {
                ATTR_MAX: self.max_conductivity.state,
                ATTR_MIN: self.min_conductivity.state,
                ATTR_CURRENT: self.sensor_conductivity.state or STATE_UNAVAILABLE,
                ATTR_ICON: self.sensor_conductivity.icon,
                ATTR_UNIT_OF_MEASUREMENT: self.sensor_conductivity.unit_of_measurement,
                ATTR_SENSOR: self.sensor_conductivity.entity_id,
            },
            ATTR_HUMIDITY: {
                ATTR_MAX: self.max_humidity.state,
                ATTR_MIN: self.min_humidity.state,
                ATTR_CURRENT: self.sensor_humidity.state or STATE_UNAVAILABLE,
                ATTR_ICON: self.sensor_humidity.icon,
                ATTR_UNIT_OF_MEASUREMENT: self.sensor_humidity.unit_of_measurement,
                ATTR_SENSOR: self.sensor_humidity.entity_id,
            },
            ATTR_DLI: {
                ATTR_MAX: self.max_dli.state,
                ATTR_MIN: self.min_dli.state,
                ATTR_CURRENT: STATE_UNAVAILABLE,
                ATTR_ICON: self.dli.icon,
                ATTR_UNIT_OF_MEASUREMENT: self.dli.unit_of_measurement,
                ATTR_SENSOR: self.dli.entity_id,
            },
        }

        if self.dli.state and self.dli.state != STATE_UNKNOWN:
            response[ATTR_DLI][ATTR_CURRENT] = float(self.dli.state)

        return response

    @property
    def threshold_entities(self) -> list[Entity]:
        """List all threshold entities"""
        return [
            self.max_conductivity,
            self.max_dli,
            self.max_humidity,
            self.max_illuminance,
            self.max_moisture,
            self.max_temperature,
            self.min_conductivity,
            self.min_dli,
            self.min_humidity,
            self.min_illuminance,
            self.min_moisture,
            self.min_temperature,
        ]

    @property
    def meter_entities(self) -> list[Entity]:
        """List all meter (sensor) entities"""
        return [
            self.sensor_conductivity,
            self.sensor_humidity,
            self.sensor_illuminance,
            self.sensor_moisture,
            self.sensor_temperature,
        ]

    @property
    def integral_entities(self) -> list(Entity):
        """List all integral entities"""
        return [
            self.dli,
            self.ppfd,
            self.total_integral,
            self.moisture_consumption,
            self.fertilizer_consumption,
        ]

    def add_image(self, image_url: str | None) -> None:
        """Set new entity_picture"""
        self._attr_entity_picture = image_url
        options = self._config.options.copy()
        options[ATTR_ENTITY_PICTURE] = image_url
        self._hass.config_entries.async_update_entry(self._config, options=options)

    def add_strain(self, strain: Entity | None) -> None:
        """Set new strain"""
        self.pid = strain

    def add_thresholds(
        self,
        max_moisture: Entity | None,
        min_moisture: Entity | None,
        max_temperature: Entity | None,
        min_temperature: Entity | None,
        max_conductivity: Entity | None,
        min_conductivity: Entity | None,
        max_illuminance: Entity | None,
        min_illuminance: Entity | None,
        max_humidity: Entity | None,
        min_humidity: Entity | None,
        max_dli: Entity | None,
        min_dli: Entity | None,
    ) -> None:
        """Add the threshold entities"""
        self.max_moisture = max_moisture
        self.min_moisture = min_moisture
        self.max_temperature = max_temperature
        self.min_temperature = min_temperature
        self.max_conductivity = max_conductivity
        self.min_conductivity = min_conductivity
        self.max_illuminance = max_illuminance
        self.min_illuminance = min_illuminance
        self.max_humidity = max_humidity
        self.min_humidity = min_humidity
        self.max_dli = max_dli
        self.min_dli = min_dli

    def add_sensors(
        self,
        moisture: Entity | None,
        temperature: Entity | None,
        conductivity: Entity | None,
        illuminance: Entity | None,
        humidity: Entity | None,
    ) -> None:
        """Add the sensor entities"""
        self.sensor_moisture = moisture
        self.sensor_temperature = temperature
        self.sensor_conductivity = conductivity
        self.sensor_illuminance = illuminance
        self.sensor_humidity = humidity

    def add_dli(
        self,
        dli: Entity | None,
    ) -> None:
        """Add the DLI-utility sensors"""
        self.dli = dli
        self.plant_complete = True

    def add_calculations(self, ppfd: Entity, total_integral: Entity, moisture_consumption: Entity, fertilizer_consumption: Entity) -> None:
        """Add the intermediate calculation entities"""
        self.ppfd = ppfd
        self.total_integral = total_integral
        self.moisture_consumption = moisture_consumption
        self.fertilizer_consumption = fertilizer_consumption

    def add_growth_phase_select(self, growth_phase_select: Entity) -> None:
        """Add the growth phase select entity."""
        self.growth_phase_select = growth_phase_select

    def add_flowering_duration(self, flowering_duration: Entity) -> None:
        """Füge die Blütedauer Number Entity hinzu."""
        self.flowering_duration = flowering_duration

    def update(self) -> None:
        """Run on every update of the entities"""
        new_state = STATE_OK
        known_state = False

        if self.device_type == DEVICE_TYPE_CYCLE:
            # Cycle-Update-Logik
            if self.sensor_temperature is not None:
                temperature = self._median_sensors.get('temperature')
                if temperature is not None:
                    known_state = True
                    if float(temperature) < float(self.min_temperature.state):
                        self.temperature_status = STATE_LOW
                        if self.temperature_trigger:
                            new_state = STATE_PROBLEM
                    elif float(temperature) > float(self.max_temperature.state):
                        self.temperature_status = STATE_HIGH
                        if self.temperature_trigger:
                            new_state = STATE_PROBLEM
                    else:
                        self.temperature_status = STATE_OK

            if self.sensor_moisture is not None:
                moisture = self._median_sensors.get('moisture')
                if moisture is not None:
                    known_state = True
                    if float(moisture) < float(self.min_moisture.state):
                        self.moisture_status = STATE_LOW
                        if self.moisture_trigger:
                            new_state = STATE_PROBLEM
                    elif float(moisture) > float(self.max_moisture.state):
                        self.moisture_status = STATE_HIGH
                        if self.moisture_trigger:
                            new_state = STATE_PROBLEM
                    else:
                        self.moisture_status = STATE_OK

            if self.sensor_conductivity is not None:
                conductivity = self._median_sensors.get('conductivity')
                if conductivity is not None:
                    known_state = True
                    if float(conductivity) < float(self.min_conductivity.state):
                        self.conductivity_status = STATE_LOW
                        if self.conductivity_trigger:
                            new_state = STATE_PROBLEM
                    elif float(conductivity) > float(self.max_conductivity.state):
                        self.conductivity_status = STATE_HIGH
                        if self.conductivity_trigger:
                            new_state = STATE_PROBLEM
                    else:
                        self.conductivity_status = STATE_OK

            if self.sensor_illuminance is not None:
                illuminance = self._median_sensors.get('illuminance')
                if illuminance is not None:
                    known_state = True
                    if float(illuminance) < float(self.min_illuminance.state):
                        self.illuminance_status = STATE_LOW
                        if self.illuminance_trigger:
                            new_state = STATE_PROBLEM
                    elif float(illuminance) > float(self.max_illuminance.state):
                        self.illuminance_status = STATE_HIGH
                        if self.illuminance_trigger:
                            new_state = STATE_PROBLEM
                    else:
                        self.illuminance_status = STATE_OK

            if self.sensor_humidity is not None:
                humidity = self._median_sensors.get('humidity')
                if humidity is not None:
                    known_state = True
                    if float(humidity) < float(self.min_humidity.state):
                        self.humidity_status = STATE_LOW
                        if self.humidity_trigger:
                            new_state = STATE_PROBLEM
                    elif float(humidity) > float(self.max_humidity.state):
                        self.humidity_status = STATE_HIGH
                        if self.humidity_trigger:
                            new_state = STATE_PROBLEM
                    else:
                        self.humidity_status = STATE_OK

            if self.dli is not None:
                dli = self._median_sensors.get('dli')
                if dli is not None:
                    known_state = True
                    if float(dli) < float(self.min_dli.state):
                        self.dli_status = STATE_LOW
                        if self.dli_trigger:
                            new_state = STATE_PROBLEM
                    elif float(dli) > float(self.max_dli.state):
                        self.dli_status = STATE_HIGH
                        if self.dli_trigger:
                            new_state = STATE_PROBLEM
                    else:
                        self.dli_status = STATE_OK

        else:
            # Plant-Update-Logik
            if self.sensor_moisture is not None:
                moisture = self.sensor_moisture.state
                if moisture is not None and moisture != STATE_UNAVAILABLE and moisture != STATE_UNKNOWN:
                    known_state = True
                    if float(moisture) < float(self.min_moisture.state):
                        self.moisture_status = STATE_LOW
                        if self.moisture_trigger:
                            new_state = STATE_PROBLEM
                    elif float(moisture) > float(self.max_moisture.state):
                        self.moisture_status = STATE_HIGH
                        if self.moisture_trigger:
                            new_state = STATE_PROBLEM
                    else:
                        self.moisture_status = STATE_OK

            if self.sensor_conductivity is not None:
                conductivity = self.sensor_conductivity.state
                if conductivity is not None and conductivity != STATE_UNAVAILABLE and conductivity != STATE_UNKNOWN:
                    known_state = True
                    if float(conductivity) < float(self.min_conductivity.state):
                        self.conductivity_status = STATE_LOW
                        if self.conductivity_trigger:
                            new_state = STATE_PROBLEM
                    elif float(conductivity) > float(self.max_conductivity.state):
                        self.conductivity_status = STATE_HIGH
                        if self.conductivity_trigger:
                            new_state = STATE_PROBLEM
                    else:
                        self.conductivity_status = STATE_OK

            # Füge die fehlenden Sensor-Prüfungen hinzu
            if self.sensor_temperature is not None:
                temperature = self.sensor_temperature.state
                if temperature is not None and temperature != STATE_UNAVAILABLE and temperature != STATE_UNKNOWN:
                    known_state = True
                    if float(temperature) < float(self.min_temperature.state):
                        self.temperature_status = STATE_LOW
                        if self.temperature_trigger:
                            new_state = STATE_PROBLEM
                    elif float(temperature) > float(self.max_temperature.state):
                        self.temperature_status = STATE_HIGH
                        if self.temperature_trigger:
                            new_state = STATE_PROBLEM
                    else:
                        self.temperature_status = STATE_OK

            if self.sensor_illuminance is not None:
                illuminance = self.sensor_illuminance.state
                if illuminance is not None and illuminance != STATE_UNAVAILABLE and illuminance != STATE_UNKNOWN:
                    known_state = True
                    if float(illuminance) < float(self.min_illuminance.state):
                        self.illuminance_status = STATE_LOW
                        if self.illuminance_trigger:
                            new_state = STATE_PROBLEM
                    elif float(illuminance) > float(self.max_illuminance.state):
                        self.illuminance_status = STATE_HIGH
                        if self.illuminance_trigger:
                            new_state = STATE_PROBLEM
                    else:
                        self.illuminance_status = STATE_OK

            if self.dli is not None:
                dli = self.dli.state
                if dli is not None and dli != STATE_UNAVAILABLE and dli != STATE_UNKNOWN:
                    known_state = True
                    if float(dli) < float(self.min_dli.state):
                        self.dli_status = STATE_LOW
                        if self.dli_trigger:
                            new_state = STATE_PROBLEM
                    elif float(dli) > float(self.max_dli.state):
                        self.dli_status = STATE_HIGH
                        if self.dli_trigger:
                            new_state = STATE_PROBLEM
                    else:
                        self.dli_status = STATE_OK

        if not known_state:
            new_state = STATE_UNKNOWN

        self._attr_state = new_state
        self.update_registry()

    @property
    def data_source(self) -> str | None:
        """Currently unused. For future use"""
        return None

    def update_registry(self) -> None:
        """Update registry with correct data"""
        if self._device_id is None:
            device_registry = dr.async_get(self._hass)
            device = device_registry.async_get_device(
                identifiers={(DOMAIN, self.unique_id)}
            )
            if device:
                self._device_id = device.id

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        self.update_registry()

    @property
    def icon(self) -> str:
        """Return the icon."""
        if self.device_type == DEVICE_TYPE_CYCLE:
            return ICON_DEVICE_CYCLE
        return ICON_DEVICE_PLANT

    def add_member_plant(self, plant_entity_id: str) -> None:
        """Add a plant to the cycle."""
        if plant_entity_id not in self._member_plants:
            self._member_plants.append(plant_entity_id)
            self._update_cycle_attributes()
            self._update_median_sensors()
            
            # Aktualisiere Growth Phase sofort
            if self.growth_phase_select:
                self._hass.async_create_task(
                    self.growth_phase_select._update_cycle_phase()
                )
            
            # Aktualisiere die Flowering Duration
            if self.flowering_duration:
                self._hass.async_create_task(
                    self.flowering_duration._update_cycle_duration()
                )
                
            # Aktualisiere die Topfgröße
            if self.pot_size:
                self._hass.async_create_task(
                    self.pot_size._update_cycle_pot_size()
                )

    def remove_member_plant(self, plant_entity_id: str) -> None:
        """Remove a plant from the cycle."""
        if plant_entity_id in self._member_plants:
            _LOGGER.debug("Removing plant %s from cycle %s", plant_entity_id, self.entity_id)
            self._member_plants.remove(plant_entity_id)
            self._update_cycle_attributes()
            self._update_median_sensors()

            # Aktualisiere Growth Phase sofort
            if self.growth_phase_select:
                self._hass.async_create_task(
                    self.growth_phase_select._update_cycle_phase()
                )
                
            # Aktualisiere die Flowering Duration
            if self.flowering_duration:
                self._hass.async_create_task(
                    self.flowering_duration._update_cycle_duration()
                )
                
            # Aktualisiere die Topfgröße
            if self.pot_size:
                self._hass.async_create_task(
                    self.pot_size._update_cycle_pot_size()
                )

    def _update_median_sensors(self) -> None:
        """Aktualisiere die Median-Werte für alle Sensoren."""
        if not self._member_plants:
            return

        # Dictionary für die Sensor-Werte
        sensor_values = {
            'temperature': [], 
            'moisture': [],
            'conductivity': [], 
            'illuminance': [],
            'humidity': [],
            'ppfd': [],
            'dli': [],
            'total_integral': [],
            'moisture_consumption': [],
            'fertilizer_consumption': []
        }

        for plant_id in self._member_plants:
            plant = None
            # Suche die Plant Entity
            for entry_id in self._hass.data[DOMAIN]:
                if ATTR_PLANT in self._hass.data[DOMAIN][entry_id]:
                    if self._hass.data[DOMAIN][entry_id][ATTR_PLANT].entity_id == plant_id:
                        plant = self._hass.data[DOMAIN][entry_id][ATTR_PLANT]
                        break

            if not plant:
                _LOGGER.warning("Could not find plant %s", plant_id)
                continue

            # Sammle die Sensor-Werte für alle Sensor-Typen
            sensors_to_check = {
                'temperature': plant.sensor_temperature,
                'moisture': plant.sensor_moisture,
                'conductivity': plant.sensor_conductivity,
                'illuminance': plant.sensor_illuminance,
                'humidity': plant.sensor_humidity,
                'ppfd': plant.ppfd,
                'dli': plant.dli,
                'total_integral': plant.total_integral,
                'moisture_consumption': plant.moisture_consumption,
                'fertilizer_consumption': plant.fertilizer_consumption,
            }

            for sensor_type, sensor in sensors_to_check.items():
                if sensor and hasattr(sensor, 'state') and sensor.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE, None):
                    try:
                        # Für DLI/PPFD/total_integral/consumption speichern wir auch den Sensor selbst
                        if sensor_type in ['ppfd', 'dli', 'total_integral', 
                                         'moisture_consumption', 'fertilizer_consumption']:
                            sensor_values[sensor_type].append((float(sensor.state), sensor))
                        else:
                            sensor_values[sensor_type].append(float(sensor.state))
                        _LOGGER.debug("Added %s value %s from plant %s", 
                                    sensor_type, sensor.state, plant_id)
                    except (TypeError, ValueError) as ex:
                        _LOGGER.debug("Could not convert %s value %s: %s",
                                    sensor_type, sensor.state, ex)
                        continue

        # Berechne Aggregate
        for sensor_type, values in sensor_values.items():
            if values:
                aggregation_method = self._plant_info.get('aggregations', {}).get(
                    sensor_type, DEFAULT_AGGREGATIONS.get(sensor_type, AGGREGATION_MEDIAN)
                )
                
                # Spezielle Behandlung für Sensoren mit Original-Berechnung
                if sensor_type in ['ppfd', 'dli', 'total_integral', 
                                 'moisture_consumption', 'fertilizer_consumption'] and aggregation_method == AGGREGATION_ORIGINAL:
                    # Bei Original-Berechnung nehmen wir den ersten gültigen Sensor
                    if values:
                        self._median_sensors[sensor_type] = values[0] if isinstance(values[0], (int, float)) else values[0][0]
                        _LOGGER.debug("Using original calculation for %s from first valid sensor", sensor_type)
                    continue

                # Für alle anderen Fälle extrahieren wir nur die Werte
                if sensor_type in ['ppfd', 'dli', 'total_integral', 
                                 'moisture_consumption', 'fertilizer_consumption']:
                    values = [v[0] for v in values]  # Extrahiere nur die Werte, nicht die Sensoren

                if aggregation_method == AGGREGATION_MEAN:
                    self._median_sensors[sensor_type] = sum(values) / len(values)
                elif aggregation_method == AGGREGATION_MIN:
                    self._median_sensors[sensor_type] = min(values)
                elif aggregation_method == AGGREGATION_MAX:
                    self._median_sensors[sensor_type] = max(values)
                else:  # AGGREGATION_MEDIAN
                    sorted_values = sorted(values)
                    n = len(sorted_values)
                    if n % 2 == 0:
                        self._median_sensors[sensor_type] = (sorted_values[n//2 - 1] + sorted_values[n//2]) / 2
                    else:
                        self._median_sensors[sensor_type] = sorted_values[n//2]

                _LOGGER.debug("%s %s for cycle %s: %s", 
                             aggregation_method, sensor_type, 
                             self.entity_id, self._median_sensors[sensor_type])
            else:
                self._median_sensors[sensor_type] = None

    def _update_cycle_attributes(self) -> None:
        """Aktualisiert die Attribute des Cycles basierend auf den Member Plants."""
        if self.device_type != DEVICE_TYPE_CYCLE:
            return

        # Sammle Attribute von allen Member Plants
        strains = set()
        breeders = set()
        sortes = set()
        feminized = set()
        effects = set()
        smells = set()
        tastes = set()
        phenotypes = set()
        hungers = set()
        growth_stretches = set()
        flower_stretches = set()
        mold_resistances = set()
        difficulties = set()
        yields = set()
        notes = set()
        websites = set()

        for plant_id in self._member_plants:
            for entry_id in self._hass.data[DOMAIN]:
                if ATTR_PLANT in self._hass.data[DOMAIN][entry_id]:
                    plant = self._hass.data[DOMAIN][entry_id][ATTR_PLANT]
                    if plant.entity_id == plant_id:
                        # Füge nicht-leere Werte zu den Sets hinzu
                        if plant._plant_info.get(ATTR_STRAIN):
                            strains.add(plant._plant_info[ATTR_STRAIN])
                        if plant._plant_info.get(ATTR_BREEDER):
                            breeders.add(plant._plant_info[ATTR_BREEDER])
                        if plant._plant_info.get("sorte"):
                            sortes.add(plant._plant_info["sorte"])
                        if plant._plant_info.get("feminized"):
                            feminized.add(plant._plant_info["feminized"])
                        if plant._plant_info.get("effects"):
                            effects.add(plant._plant_info["effects"])
                        if plant._plant_info.get("smell"):
                            smells.add(plant._plant_info["smell"])
                        if plant._plant_info.get("taste"):
                            tastes.add(plant._plant_info["taste"])
                        if plant._plant_info.get(ATTR_PHENOTYPE):
                            phenotypes.add(plant._plant_info[ATTR_PHENOTYPE])
                        if plant._plant_info.get(ATTR_HUNGER):
                            hungers.add(plant._plant_info[ATTR_HUNGER])
                        if plant._plant_info.get(ATTR_GROWTH_STRETCH):
                            growth_stretches.add(plant._plant_info[ATTR_GROWTH_STRETCH])
                        if plant._plant_info.get(ATTR_FLOWER_STRETCH):
                            flower_stretches.add(plant._plant_info[ATTR_FLOWER_STRETCH])
                        if plant._plant_info.get(ATTR_MOLD_RESISTANCE):
                            mold_resistances.add(plant._plant_info[ATTR_MOLD_RESISTANCE])
                        if plant._plant_info.get(ATTR_DIFFICULTY):
                            difficulties.add(plant._plant_info[ATTR_DIFFICULTY])
                        if plant._plant_info.get(ATTR_YIELD):
                            yields.add(plant._plant_info[ATTR_YIELD])
                        if plant._plant_info.get(ATTR_NOTES):
                            notes.add(plant._plant_info[ATTR_NOTES])
                        if plant._plant_info.get("website"):
                            websites.add(plant._plant_info["website"])
                        break

        # Aktualisiere die Plant Info mit den aggregierten Werten
        self._plant_info.update({
            ATTR_STRAIN: ", ".join(sorted(strains)) if strains else "",
            ATTR_BREEDER: ", ".join(sorted(breeders)) if breeders else "",
            "sorte": ", ".join(sorted(sortes)) if sortes else "",
            "feminized": ", ".join(sorted(feminized)) if feminized else "",
            "effects": ", ".join(sorted(effects)) if effects else "",
            "smell": ", ".join(sorted(smells)) if smells else "",
            "taste": ", ".join(sorted(tastes)) if tastes else "",
            ATTR_PHENOTYPE: ", ".join(sorted(phenotypes)) if phenotypes else "",
            ATTR_HUNGER: ", ".join(sorted(hungers)) if hungers else "",
            ATTR_GROWTH_STRETCH: ", ".join(sorted(growth_stretches)) if growth_stretches else "",
            ATTR_FLOWER_STRETCH: ", ".join(sorted(flower_stretches)) if flower_stretches else "",
            ATTR_MOLD_RESISTANCE: ", ".join(sorted(mold_resistances)) if mold_resistances else "",
            ATTR_DIFFICULTY: ", ".join(sorted(difficulties)) if difficulties else "",
            ATTR_YIELD: ", ".join(sorted(yields)) if yields else "",
            ATTR_NOTES: ", ".join(sorted(notes)) if notes else "",
            "website": ", ".join(sorted(websites)) if websites else "",
        })

        # Aktualisiere den State
        self.async_write_ha_state()

    def add_cycle_select(self, cycle_select: Entity) -> None:
        """Füge den Cycle Select Helper hinzu."""
        self.cycle_select = cycle_select

    def add_pot_size(self, pot_size) -> None:
        """Fügt den Pot Size Helper hinzu."""
        self.pot_size = pot_size

    def add_water_capacity(self, water_capacity) -> None:
        """Add water capacity entity."""
        self.water_capacity = water_capacity

    @property
    def name(self) -> str:
        """Return the name with emojis for the device."""
        name = self._plant_info[ATTR_NAME]
        # Füge Emojis für das Device hinzu
        if self.device_type == DEVICE_TYPE_CYCLE and " 🔄" not in name:
            name = f"{name} {self._plant_info.get('plant_emoji', '🔄')}"
        elif self.device_type == DEVICE_TYPE_PLANT and " 🌿" not in name:
            name = f"{name} {self._plant_info.get('plant_emoji', '🌿')}"
        return name

    @property
    def _name(self) -> str:
        """Return the clean name without emojis for entities."""
        name = self._plant_info[ATTR_NAME]
        # Entferne Emojis für die Entities
        if self.device_type == DEVICE_TYPE_CYCLE:
            name = name.replace(" 🔄", "")
        elif " 🌿" in name:
            name = name.replace(" 🌿", "")
        return name

    @property
    def has_entity_name(self) -> bool:
        """Return False to use raw entity names without device prefix."""
        return False


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: ConfigEntry, 
    device_entry: dr.DeviceEntry,
) -> bool:
    """Delete device entry from device registry."""
    _LOGGER.debug(
        "async_remove_config_entry_device called for device %s (config: %s)", 
        device_entry.id,
        config_entry.data
    )
    
    # Prüfe ob dies der Konfigurationsknoten ist
    if config_entry.data.get("is_config", False):
        # Prüfe ob noch andere Plant/Cycle Einträge existieren
        for entry in hass.config_entries.async_entries(DOMAIN):
            if not entry.data.get("is_config", False):  # Wenn es ein Plant/Cycle ist
                _LOGGER.warning(
                    "Cannot remove configuration node while plants/cycles exist. "
                    "Please remove all plants and cycles first."
                )
                return False
    
    device_registry = dr.async_get(hass)
    
    # Wenn das Device eine Plant ist und einem Cycle zugeordnet ist
    if device_entry.via_device_id:
        _LOGGER.debug("Removing plant device with via_device_id %s", device_entry.via_device_id)
        # Finde die Plant Entity
        entity_registry = er.async_get(hass)
        plant_entity_id = None
        for entity_entry in entity_registry.entities.values():
            if entity_entry.device_id == device_entry.id and entity_entry.domain == DOMAIN:
                plant_entity_id = entity_entry.entity_id
                break
                
        if plant_entity_id:
            # Suche das Cycle Device
            for device in device_registry.devices.values():
                if device.id == device_entry.via_device_id:
                    cycle_device = device
                    # Finde den zugehörigen Cycle
                    for entry_id in hass.data[DOMAIN]:
                        if ATTR_PLANT in hass.data[DOMAIN][entry_id]:
                            cycle = hass.data[DOMAIN][entry_id][ATTR_PLANT]
                            if (cycle.device_type == DEVICE_TYPE_CYCLE and 
                                cycle.unique_id == next(iter(cycle_device.identifiers))[1]):
                                # Entferne die Plant aus dem Cycle
                                cycle.remove_member_plant(plant_entity_id)
                                # Aktualisiere Flowering Duration
                                if cycle.flowering_duration:
                                    await cycle.flowering_duration._update_cycle_duration()
                                break
                    break
    
    # Entferne das Device
    device_registry.async_remove_device(device_entry.id)
    
    # Entferne dann die Config Entry
    await hass.config_entries.async_remove(config_entry.entry_id)
    
    return True

