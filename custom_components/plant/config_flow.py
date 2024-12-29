"""Config flow for Custom Plant integration."""
from __future__ import annotations

# Standard Library Imports
import logging
import re
from typing import Any
import urllib.parse

# Third Party Imports
import voluptuous as vol

# Home Assistant Imports
from homeassistant import config_entries, data_entry_flow
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_DOMAIN,
    ATTR_ENTITY_PICTURE,
    ATTR_NAME,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.selector import selector

# Local Imports
from .const import (
    ATTR_ENTITY,
    ATTR_LIMITS,
    ATTR_OPTIONS,
    ATTR_SEARCH_FOR,
    ATTR_SELECT,
    ATTR_SENSORS,
    ATTR_STRAIN,
    CONF_MAX_CONDUCTIVITY,
    CONF_MAX_DLI,
    CONF_MAX_HUMIDITY,
    CONF_MAX_ILLUMINANCE,
    CONF_MAX_MOISTURE,
    CONF_MAX_TEMPERATURE,
    CONF_MIN_CONDUCTIVITY,
    CONF_MIN_DLI,
    CONF_MIN_HUMIDITY,
    CONF_MIN_ILLUMINANCE,
    CONF_MIN_MOISTURE,
    CONF_MIN_TEMPERATURE,
    DATA_SOURCE,
    DATA_SOURCE_PLANTBOOK,
    DOMAIN,
    DOMAIN_PLANTBOOK,
    DOMAIN_SENSOR,
    FLOW_CONDUCTIVITY_TRIGGER,
    FLOW_DLI_TRIGGER,
    FLOW_ERROR_NOTFOUND,
    FLOW_FORCE_SPECIES_UPDATE,
    FLOW_HUMIDITY_TRIGGER,
    FLOW_ILLUMINANCE_TRIGGER,
    FLOW_MOISTURE_TRIGGER,
    FLOW_PLANT_INFO,
    FLOW_PLANT_LIMITS,
    FLOW_RIGHT_PLANT,
    FLOW_SENSOR_CONDUCTIVITY,
    FLOW_SENSOR_HUMIDITY,
    FLOW_SENSOR_ILLUMINANCE,
    FLOW_SENSOR_MOISTURE,
    FLOW_SENSOR_TEMPERATURE,
    FLOW_STRING_DESCRIPTION,
    FLOW_TEMP_UNIT,
    FLOW_TEMPERATURE_TRIGGER,
    OPB_DISPLAY_PID,
    DEFAULT_GROWTH_PHASE,
    GROWTH_PHASES,
    ATTR_BREEDER,
    ATTR_FLOWERING_DURATION,
    ATTR_WEBSITE,
    ATTR_INFOTEXT1,
    ATTR_INFOTEXT2,
    ATTR_EFFECTS,
    ATTR_SMELL,
    ATTR_TASTE,
    ATTR_LINEAGE,
    ATTR_PHENOTYPE,
    ATTR_HUNGER,
    ATTR_GROWTH_STRETCH,
    ATTR_FLOWER_STRETCH,
    ATTR_MOLD_RESISTANCE,
    ATTR_DIFFICULTY,
    ATTR_YIELD,
    ATTR_NOTES,
    ATTR_IS_NEW_PLANT,
    DEVICE_TYPE_PLANT,
    DEVICE_TYPE_CYCLE,
    DEVICE_TYPES,
    ATTR_DEVICE_TYPE,
    AGGREGATION_MEDIAN,
    AGGREGATION_MEAN,
    AGGREGATION_MIN,
    AGGREGATION_MAX,
    AGGREGATION_METHODS,
    DEFAULT_AGGREGATIONS,
    CONF_AGGREGATION,
)
from .plant_helpers import PlantHelper

_LOGGER = logging.getLogger(__name__)


@config_entries.HANDLERS.register(DOMAIN)
class PlantConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Plant."""

    VERSION = 1

    def __init__(self):
        """Initialize flow."""
        self.plant_info = {}
        self.error = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)

    async def async_step_import(self, import_input):
        """Importing config from configuration.yaml"""
        _LOGGER.debug(import_input)
        # return FlowResultType.ABORT
        return self.async_create_entry(
            title=import_input[FLOW_PLANT_INFO][ATTR_NAME],
            data=import_input,
        )

    async def async_step_user(self, user_input=None):
        """Handle the initial step - select device type."""
        if user_input is not None:
            self.device_type = user_input.get(ATTR_DEVICE_TYPE)
            
            # Wenn der Aufruf vom Service kommt, nutzen wir die vorgegebenen Daten
            if self.context.get("source_type") == "service":
                self.device_type = user_input.get(ATTR_DEVICE_TYPE, DEVICE_TYPE_PLANT)
                if self.device_type == DEVICE_TYPE_CYCLE:
                    return await self.async_step_cycle(user_input)
                else:
                    return await self.async_step_plant(user_input)
            
            # Normaler Flow über UI
            if self.device_type == DEVICE_TYPE_CYCLE:
                return await self.async_step_cycle()
            else:
                return await self.async_step_plant()

        # Nur Device Type Auswahl im ersten Schritt
        data_schema = {
            vol.Required(ATTR_DEVICE_TYPE, default=DEVICE_TYPE_PLANT): vol.In(DEVICE_TYPES),
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(data_schema),
        )

    async def async_step_cycle(self, user_input=None):
        """Handle cycle configuration."""
        errors = {}
        if user_input is not None:
            self.plant_info = {
                ATTR_NAME: user_input[ATTR_NAME],
                ATTR_DEVICE_TYPE: DEVICE_TYPE_CYCLE,
                ATTR_IS_NEW_PLANT: True,
                ATTR_STRAIN: "",
                ATTR_BREEDER: "",
                "growth_phase": DEFAULT_GROWTH_PHASE,
                "plant_emoji": user_input.get("plant_emoji", "🔄"),
                "growth_phase_aggregation": user_input.get("growth_phase_aggregation", "min"),
                "flowering_duration_aggregation": user_input.get("flowering_duration_aggregation", "mean"),
                # Speichere die Aggregationsmethoden
                "aggregations": {
                    'temperature': user_input.get('temperature_aggregation', DEFAULT_AGGREGATIONS['temperature']),
                    'moisture': user_input.get('moisture_aggregation', DEFAULT_AGGREGATIONS['moisture']),
                    'conductivity': user_input.get('conductivity_aggregation', DEFAULT_AGGREGATIONS['conductivity']),
                    'illuminance': user_input.get('illuminance_aggregation', DEFAULT_AGGREGATIONS['illuminance']),
                    'humidity': user_input.get('humidity_aggregation', DEFAULT_AGGREGATIONS['humidity']),
                    'ppfd': user_input.get('ppfd_aggregation', DEFAULT_AGGREGATIONS['ppfd']),
                    'dli': user_input.get('dli_aggregation', DEFAULT_AGGREGATIONS['dli']),
                    'total_integral': user_input.get('total_integral_aggregation', DEFAULT_AGGREGATIONS['total_integral']),
                }
            }
            
            # Nutze PlantHelper für die Standard-Grenzwerte
            plant_helper = PlantHelper(hass=self.hass)
            plant_config = await plant_helper.generate_configentry(
                config={
                    ATTR_NAME: self.plant_info[ATTR_NAME],
                    ATTR_STRAIN: "",
                    ATTR_BREEDER: "",
                    ATTR_SENSORS: {},
                }
            )
            
            # Übernehme die Standard-Grenzwerte
            self.plant_info.update(plant_config[FLOW_PLANT_INFO])
            
            # Erstelle direkt den Entry ohne weitere Schritte
            return self.async_create_entry(
                title=self.plant_info[ATTR_NAME],
                data={FLOW_PLANT_INFO: self.plant_info}
            )

        # Wenn der Aufruf vom Service kommt, nutzen wir die vorgegebenen Daten
        if self.context.get("source_type") == "service":
            return self.async_create_entry(
                title=user_input[ATTR_NAME],
                data={FLOW_PLANT_INFO: {
                    ATTR_NAME: user_input[ATTR_NAME],
                    ATTR_DEVICE_TYPE: DEVICE_TYPE_CYCLE,
                    ATTR_IS_NEW_PLANT: True,
                    ATTR_STRAIN: "",
                    ATTR_BREEDER: "",
                    "growth_phase": DEFAULT_GROWTH_PHASE,
                    "plant_emoji": user_input.get("plant_emoji", "🔄"),
                }}
            )

        data_schema = {
            vol.Required(ATTR_NAME): cv.string,
            vol.Optional("plant_emoji", default="🔄"): cv.string,
            vol.Optional("growth_phase_aggregation", default="min"): vol.In(["min", "max"]),
            vol.Optional("flowering_duration_aggregation", default="mean"): vol.In(AGGREGATION_METHODS),
            vol.Optional("temperature_aggregation", 
                        default=DEFAULT_AGGREGATIONS['temperature']): vol.In(AGGREGATION_METHODS),
            vol.Optional("moisture_aggregation", 
                        default=DEFAULT_AGGREGATIONS['moisture']): vol.In(AGGREGATION_METHODS),
            vol.Optional("conductivity_aggregation", 
                        default=DEFAULT_AGGREGATIONS['conductivity']): vol.In(AGGREGATION_METHODS),
            vol.Optional("illuminance_aggregation", 
                        default=DEFAULT_AGGREGATIONS['illuminance']): vol.In(AGGREGATION_METHODS),
            vol.Optional("humidity_aggregation", 
                        default=DEFAULT_AGGREGATIONS['humidity']): vol.In(AGGREGATION_METHODS),
            vol.Optional("ppfd_aggregation", 
                        default=DEFAULT_AGGREGATIONS['ppfd']): vol.In(AGGREGATION_METHODS),
            vol.Optional("dli_aggregation", 
                        default=DEFAULT_AGGREGATIONS['dli']): vol.In(AGGREGATION_METHODS),
            vol.Optional("total_integral_aggregation", 
                        default=DEFAULT_AGGREGATIONS['total_integral']): vol.In(AGGREGATION_METHODS),
        }

        return self.async_show_form(
            step_id="cycle",
            data_schema=vol.Schema(data_schema),
            errors=errors,
        )

    async def async_step_plant(self, user_input=None):
        """Handle plant configuration."""
        errors = {}
        if user_input is not None:
            self.plant_info = dict(user_input)
            self.plant_info[ATTR_IS_NEW_PLANT] = True
            self.plant_info[ATTR_DEVICE_TYPE] = DEVICE_TYPE_PLANT
            self.plant_info[ATTR_STRAIN] = user_input[ATTR_STRAIN]
            self.plant_info[ATTR_BREEDER] = user_input.get(ATTR_BREEDER, "")
            self.plant_info["growth_phase"] = user_input.get("growth_phase", DEFAULT_GROWTH_PHASE)
            self.plant_info["plant_emoji"] = user_input.get("plant_emoji", "🥦")

            plant_helper = PlantHelper(hass=self.hass)
            plant_config = await plant_helper.get_plantbook_data({
                ATTR_STRAIN: self.plant_info[ATTR_STRAIN],
                ATTR_BREEDER: self.plant_info[ATTR_BREEDER]
            })

            if plant_config and plant_config.get(FLOW_PLANT_INFO, {}).get(DATA_SOURCE) == DATA_SOURCE_PLANTBOOK:
                plant_info = plant_config[FLOW_PLANT_INFO]
                self.plant_info.update(plant_info)

            if self.context.get("source_type") == "service":
                return self.async_create_entry(
                    title=self.plant_info[ATTR_NAME],
                    data={FLOW_PLANT_INFO: self.plant_info}
                )

            return await self.async_step_limits()

        data_schema = {
            vol.Required(ATTR_NAME): cv.string,
            vol.Optional("plant_emoji", default="🥦"): cv.string,
            vol.Required(ATTR_STRAIN): cv.string,
            vol.Required(ATTR_BREEDER): cv.string,
            vol.Optional("growth_phase", default=DEFAULT_GROWTH_PHASE): vol.In(
                GROWTH_PHASES
            ),
            vol.Optional(FLOW_SENSOR_TEMPERATURE): selector(
                {
                    ATTR_ENTITY: {
                        ATTR_DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
                        ATTR_DOMAIN: DOMAIN_SENSOR,
                    }
                }
            ),
            vol.Optional(FLOW_SENSOR_MOISTURE): selector(
                {
                    ATTR_ENTITY: {
                        ATTR_DEVICE_CLASS: SensorDeviceClass.MOISTURE,
                        ATTR_DOMAIN: DOMAIN_SENSOR,
                    }
                }
            ),
            vol.Optional(FLOW_SENSOR_CONDUCTIVITY): selector(
                {ATTR_ENTITY: {ATTR_DOMAIN: DOMAIN_SENSOR}}
            ),
            vol.Optional(FLOW_SENSOR_ILLUMINANCE): selector(
                {
                    ATTR_ENTITY: {
                        ATTR_DEVICE_CLASS: SensorDeviceClass.ILLUMINANCE,
                        ATTR_DOMAIN: DOMAIN_SENSOR,
                    }
                }
            ),
            vol.Optional(FLOW_SENSOR_HUMIDITY): selector(
                {
                    ATTR_ENTITY: {
                        ATTR_DEVICE_CLASS: SensorDeviceClass.HUMIDITY,
                        ATTR_DOMAIN: DOMAIN_SENSOR,
                    }
                }
            ),
        }

        return self.async_show_form(
            step_id="plant",
            data_schema=vol.Schema(data_schema),
            errors=errors,
            description_placeholders={"opb_search": self.plant_info.get(ATTR_STRAIN)},
        )

    async def async_step_limits(self, user_input=None):
        """Handle limits step."""
        # Get default values from OpenPlantbook
        plant_helper = PlantHelper(hass=self.hass)
        plant_config = await plant_helper.generate_configentry(
            config={
                ATTR_NAME: self.plant_info[ATTR_NAME],
                ATTR_STRAIN: self.plant_info[ATTR_STRAIN],
                ATTR_BREEDER: self.plant_info.get(ATTR_BREEDER, ""),
                ATTR_SENSORS: {},
            }
        )

        if user_input is not None:
            _LOGGER.debug("User Input %s", user_input)
            # Validate user input
            valid = await self.validate_step_3(user_input)
            if valid:
                if FLOW_RIGHT_PLANT in user_input and not user_input[FLOW_RIGHT_PLANT]:
                    # User says this is not the right plant
                    # Reset the search and go back to step 1
                    self.plant_info[ATTR_SEARCH_FOR] = ""
                    return await self.async_step_user()

                # Store info to use in next step
                self.plant_info[ATTR_LIMITS] = {}
                for key in user_input:
                    if key in [
                        CONF_MAX_MOISTURE,
                        CONF_MIN_MOISTURE,
                        CONF_MAX_ILLUMINANCE,
                        CONF_MIN_ILLUMINANCE,
                        CONF_MAX_DLI,
                        CONF_MIN_DLI,
                        CONF_MAX_TEMPERATURE,
                        CONF_MIN_TEMPERATURE,
                        CONF_MAX_CONDUCTIVITY,
                        CONF_MIN_CONDUCTIVITY,
                        CONF_MAX_HUMIDITY,
                        CONF_MIN_HUMIDITY,
                    ]:
                        self.plant_info[ATTR_LIMITS][key] = user_input[key]

                if OPB_DISPLAY_PID in user_input:
                    self.plant_info[OPB_DISPLAY_PID] = user_input[OPB_DISPLAY_PID]
                if ATTR_ENTITY_PICTURE not in user_input or not user_input[ATTR_ENTITY_PICTURE]:
                    # Wenn kein Bild im user_input ist, nehmen wir das aus OpenPlantbook
                    self.plant_info[ATTR_ENTITY_PICTURE] = plant_config[FLOW_PLANT_INFO].get(ATTR_ENTITY_PICTURE, "")
                else:
                    # Sonst nehmen wir das vom User eingegebene Bild
                    self.plant_info[ATTR_ENTITY_PICTURE] = user_input[ATTR_ENTITY_PICTURE]
                if ATTR_FLOWERING_DURATION in user_input:
                    try:
                        self.plant_info[ATTR_FLOWERING_DURATION] = int(user_input[ATTR_FLOWERING_DURATION])
                    except (ValueError, TypeError):
                        self.plant_info[ATTR_FLOWERING_DURATION] = 0

                # Speichere alle zusätzlichen Attribute
                for attr in ["pid", "sorte", "feminized", "timestamp", 
                            "website", "infotext1", "infotext2", 
                            "effects", "smell", "taste", "lineage",
                            ATTR_PHENOTYPE, ATTR_HUNGER, ATTR_GROWTH_STRETCH,
                            ATTR_FLOWER_STRETCH, ATTR_MOLD_RESISTANCE, ATTR_DIFFICULTY,
                            ATTR_YIELD, ATTR_NOTES]:
                    # Für pid und timestamp nehmen wir die Werte aus plant_config wenn sie nicht im user_input sind
                    if attr in ["pid", "timestamp"]:
                        self.plant_info[attr] = str(plant_config[FLOW_PLANT_INFO].get(attr, ""))
                    elif attr in user_input:
                        self.plant_info[attr] = str(user_input[attr])

                _LOGGER.debug("Plant info after saving: %s", self.plant_info)
                return await self.async_step_limits_done()

        data_schema = {}
        extra_desc = ""
        if plant_config[FLOW_PLANT_INFO].get(OPB_DISPLAY_PID):
            # We got data from OPB.  Display a "wrong plant" switch
            data_schema[vol.Optional(FLOW_RIGHT_PLANT, default=True)] = cv.boolean
            display_pid = plant_config[FLOW_PLANT_INFO].get(OPB_DISPLAY_PID)
        else:
            display_pid = self.plant_info[ATTR_STRAIN].title()

        data_schema[
            vol.Optional(
                OPB_DISPLAY_PID,
                description={"suggested_value": display_pid}
            )
        ] = cv.string

        data_schema[
            vol.Optional(
                ATTR_BREEDER,
                default=plant_config[FLOW_PLANT_INFO].get(ATTR_BREEDER, "")
            )
        ] = str

        # Füge Blütezeit zwischen Breeder und Sorte hinzu
        flowering_duration = plant_config[FLOW_PLANT_INFO].get(ATTR_FLOWERING_DURATION, 0)
        try:
            flowering_duration = int(flowering_duration)
        except (ValueError, TypeError):
            flowering_duration = 0

        data_schema[
            vol.Optional(
                ATTR_FLOWERING_DURATION,
                default=flowering_duration
            )
        ] = vol.Coerce(int)

        data_schema[
            vol.Optional(
                "sorte",
                default=plant_config[FLOW_PLANT_INFO].get("sorte", "")
            )
        ] = str

        data_schema[
            vol.Optional(
                "feminized",
                default=plant_config[FLOW_PLANT_INFO].get("feminized", "")
            )
        ] = str

        data_schema[
            vol.Optional(
                "effects",
                default=plant_config[FLOW_PLANT_INFO].get("effects", "")
            )
        ] = str

        data_schema[
            vol.Optional(
                "smell",
                default=plant_config[FLOW_PLANT_INFO].get("smell", "")
            )
        ] = str

        data_schema[
            vol.Optional(
                "taste",
                default=plant_config[FLOW_PLANT_INFO].get("taste", "")
            )
        ] = str

        # Benutzerdefinierte Felder
        for attr in [ATTR_PHENOTYPE, ATTR_HUNGER, ATTR_GROWTH_STRETCH,
                    ATTR_FLOWER_STRETCH, ATTR_MOLD_RESISTANCE, ATTR_DIFFICULTY,
                    ATTR_YIELD, ATTR_NOTES]:
            data_schema[
                vol.Optional(
                    attr,
                    default=plant_config[FLOW_PLANT_INFO].get(attr, "")
                )
            ] = str

        data_schema[
            vol.Optional(
                "website",
                default=plant_config[FLOW_PLANT_INFO].get("website", "")
            )
        ] = str

        data_schema[
            vol.Optional(
                "lineage",
                default=plant_config[FLOW_PLANT_INFO].get("lineage", "")
            )
        ] = str

        data_schema[
            vol.Optional(
                "infotext1",
                default=plant_config[FLOW_PLANT_INFO].get("infotext1", "")
            )
        ] = str

        data_schema[
            vol.Optional(
                "infotext2",
                default=plant_config[FLOW_PLANT_INFO].get("infotext2", "")
            )
        ] = str

        # Speichern der benutzerdefinierten Attribute
        if user_input is not None:
            for attr in [ATTR_PHENOTYPE, ATTR_HUNGER, ATTR_GROWTH_STRETCH, 
                        ATTR_FLOWER_STRETCH, ATTR_MOLD_RESISTANCE, ATTR_DIFFICULTY, 
                        ATTR_YIELD, ATTR_NOTES]:
                if attr in user_input:
                    self.plant_info[attr] = str(user_input[attr])

        # Get entity_picture from config
        entity_picture = plant_config[FLOW_PLANT_INFO].get(ATTR_ENTITY_PICTURE)
        preview_picture = entity_picture  # Speichere original Pfad für Vorschau

        if entity_picture and not entity_picture.startswith("http"):
            try:
                # Nur für die Vorschau die volle URL generieren
                preview_picture = f"{get_url(self.hass, require_current_request=True)}{urllib.parse.quote(entity_picture)}"
            except NoURLAvailableError:
                _LOGGER.error(
                    "No internal or external url found. Please configure these in HA General Settings"
                )
                preview_picture = ""

        # Füge die Grenzwerte hinzu
        data_schema[vol.Optional(CONF_MAX_MOISTURE, default=int(plant_config[FLOW_PLANT_INFO].get(CONF_MAX_MOISTURE, 60)))] = int
        data_schema[vol.Optional(CONF_MIN_MOISTURE, default=int(plant_config[FLOW_PLANT_INFO].get(CONF_MIN_MOISTURE, 20)))] = int
        data_schema[vol.Optional(CONF_MAX_ILLUMINANCE, default=int(plant_config[FLOW_PLANT_INFO].get(CONF_MAX_ILLUMINANCE, 30000)))] = int
        data_schema[vol.Optional(CONF_MIN_ILLUMINANCE, default=int(plant_config[FLOW_PLANT_INFO].get(CONF_MIN_ILLUMINANCE, 1500)))] = int
        data_schema[vol.Optional(CONF_MAX_DLI, default=float(plant_config[FLOW_PLANT_INFO].get(CONF_MAX_DLI, 30)))] = int
        data_schema[vol.Optional(CONF_MIN_DLI, default=float(plant_config[FLOW_PLANT_INFO].get(CONF_MIN_DLI, 8)))] = int
        data_schema[vol.Optional(CONF_MAX_TEMPERATURE, default=int(plant_config[FLOW_PLANT_INFO].get(CONF_MAX_TEMPERATURE, 30)))] = int
        data_schema[vol.Optional(CONF_MIN_TEMPERATURE, default=int(plant_config[FLOW_PLANT_INFO].get(CONF_MIN_TEMPERATURE, 10)))] = int
        data_schema[vol.Optional(CONF_MAX_CONDUCTIVITY, default=int(plant_config[FLOW_PLANT_INFO].get(CONF_MAX_CONDUCTIVITY, 2000)))] = int
        data_schema[vol.Optional(CONF_MIN_CONDUCTIVITY, default=int(plant_config[FLOW_PLANT_INFO].get(CONF_MIN_CONDUCTIVITY, 500)))] = int
        data_schema[vol.Optional(CONF_MAX_HUMIDITY, default=int(plant_config[FLOW_PLANT_INFO].get(CONF_MAX_HUMIDITY, 60)))] = int
        data_schema[vol.Optional(CONF_MIN_HUMIDITY, default=int(plant_config[FLOW_PLANT_INFO].get(CONF_MIN_HUMIDITY, 20)))] = int
        
        # Für das Eingabefeld den originalen Pfad verwenden
        data_schema[vol.Optional(ATTR_ENTITY_PICTURE, description={"suggested_value": entity_picture})] = str

        return self.async_show_form(
            step_id="limits",
            data_schema=vol.Schema(data_schema),
            description_placeholders={
                ATTR_ENTITY_PICTURE: preview_picture,  # Für die Vorschau die volle URL
                ATTR_NAME: self.plant_info.get(ATTR_NAME),
                FLOW_TEMP_UNIT: self.hass.config.units.temperature_unit,
                "br": "<br />",
                "extra_desc": extra_desc,
            },
        )

    async def async_step_limits_done(self, user_input=None):
        """After limits are set"""
        return self.async_create_entry(
            title=self.plant_info[ATTR_NAME],
            data={FLOW_PLANT_INFO: self.plant_info},
        )

    async def validate_step_1(self, user_input):
        """Validate step one"""
        _LOGGER.debug("Validating step 1: %s", user_input)
        return True

    async def validate_step_2(self, user_input):
        """Validate step two"""
        _LOGGER.debug("Validating step 2: %s", user_input)

        if not ATTR_STRAIN in user_input:
            return False
        if not isinstance(user_input[ATTR_STRAIN], str):
            return False
        if len(user_input[ATTR_STRAIN]) < 5:
            return False
        _LOGGER.debug("Valid")

        return True

    async def validate_step_3(self, user_input):
        """Validate step three"""
        _LOGGER.debug("Validating step 3: %s", user_input)

        return True

    async def validate_step_4(self, user_input):
        """Validate step four"""
        return True

    async def async_abort(self, reason: str):
        """Handle config flow abort."""
        if self.plant_info:
            self.plant_info[ATTR_IS_NEW_PLANT] = False
            # Update existing config entries if needed
            for entry in self._async_current_entries():
                if entry.data[FLOW_PLANT_INFO].get(ATTR_IS_NEW_PLANT):
                    data = dict(entry.data)
                    data[FLOW_PLANT_INFO][ATTR_IS_NEW_PLANT] = False
                    self.hass.config_entries.async_update_entry(entry, data=data)
        return self.async_abort(reason=reason)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handling opetions for plant"""

    def __init__(
        self,
        entry: config_entries.ConfigEntry,
    ) -> None:
        """Initialize options flow."""

        entry.async_on_unload(entry.add_update_listener(self.update_plant_options))

        self.plant = None
        self.entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        """Manage the options."""
        if user_input is not None:
            if ATTR_STRAIN not in user_input or not re.match(
                r"\w+", user_input[ATTR_STRAIN]
            ):
                user_input[ATTR_STRAIN] = ""
            if ATTR_ENTITY_PICTURE not in user_input or not re.match(
                r"(\/)?\w+", user_input[ATTR_ENTITY_PICTURE]
            ):
                user_input[ATTR_ENTITY_PICTURE] = ""
            if OPB_DISPLAY_PID not in user_input or not re.match(
                r"\w+", user_input[OPB_DISPLAY_PID]
            ):
                user_input[OPB_DISPLAY_PID] = ""

            return self.async_create_entry(title="", data=user_input)

        self.plant = self.hass.data[DOMAIN][self.entry.entry_id]["plant"]
        plant_helper = PlantHelper(hass=self.hass)
        data_schema = {}
        data_schema[
            vol.Optional(
                ATTR_STRAIN, description={"suggested_value": self.plant.pid}
            )
        ] = cv.string
        if plant_helper.has_openplantbook and self.plant.pid:
            data_schema[vol.Optional(FLOW_FORCE_SPECIES_UPDATE, default=False)] = (
                cv.boolean
            )

        display_strain = self.plant.display_strain or ""
        data_schema[
            vol.Optional(
                OPB_DISPLAY_PID, description={"suggested_value": display_strain}
            )
        ] = str
        entity_picture = self.plant.entity_picture or ""
        data_schema[
            vol.Optional(
                ATTR_ENTITY_PICTURE, description={"suggested_value": entity_picture}
            )
        ] = str

        data_schema[
            vol.Optional(
                FLOW_ILLUMINANCE_TRIGGER, default=self.plant.illuminance_trigger
            )
        ] = cv.boolean
        data_schema[vol.Optional(FLOW_DLI_TRIGGER, default=self.plant.dli_trigger)] = (
            cv.boolean
        )

        data_schema[
            vol.Optional(FLOW_HUMIDITY_TRIGGER, default=self.plant.humidity_trigger)
        ] = cv.boolean
        data_schema[
            vol.Optional(
                FLOW_TEMPERATURE_TRIGGER, default=self.plant.temperature_trigger
            )
        ] = cv.boolean
        data_schema[
            vol.Optional(FLOW_MOISTURE_TRIGGER, default=self.plant.moisture_trigger)
        ] = cv.boolean
        data_schema[
            vol.Optional(
                FLOW_CONDUCTIVITY_TRIGGER, default=self.plant.conductivity_trigger
            )
        ] = cv.boolean

        # data_schema[vol.Optional(CONF_CHECK_DAYS, default=self.plant.check_days)] = int

        return self.async_show_form(step_id="init", data_schema=vol.Schema(data_schema))

    async def update_plant_options(
        self, hass: HomeAssistant, entry: config_entries.ConfigEntry
    ):
        """Handle options update."""

        _LOGGER.debug(
            "Update plant options begin for %s Data %s, Options: %s",
            entry.entry_id,
            entry.options,
            entry.data,
        )
        entity_picture = entry.options.get(ATTR_ENTITY_PICTURE)

        if entity_picture is not None:
            if entity_picture == "":
                self.plant.add_image(entity_picture)
            else:
                try:
                    url = cv.url(entity_picture)
                    _LOGGER.debug("Url 1 %s", url)
                # pylint: disable=broad-except
                except Exception as exc1:
                    _LOGGER.warning("Not a valid url: %s", entity_picture)
                    if entity_picture.startswith("/local/"):
                        try:
                            url = cv.path(entity_picture)
                            _LOGGER.debug("Url 2 %s", url)
                        except Exception as exc2:
                            _LOGGER.warning("Not a valid path: %s", entity_picture)
                            raise vol.Invalid(
                                f"Invalid URL: {entity_picture}"
                            ) from exc2
                    else:
                        raise vol.Invalid(f"Invalid URL: {entity_picture}") from exc1
                _LOGGER.debug("Update image to %s", entity_picture)
                self.plant.add_image(entity_picture)

        new_display_strain = entry.options.get(OPB_DISPLAY_PID)
        if new_display_strain is not None:
            self.plant.display_strain = new_display_strain

        new_strain = entry.options.get(ATTR_STRAIN)
        force_new_strain = entry.options.get(FLOW_FORCE_SPECIES_UPDATE)
        if new_strain is not None and (
            new_strain != self.plant.strain or force_new_strain is True
        ):
            _LOGGER.debug(
                "Strain changed from '%s' to '%s'", self.plant.strain, new_strain
            )
            plant_helper = PlantHelper(hass=self.hass)
            plant_config = await plant_helper.generate_configentry(
                config={
                    ATTR_STRAIN: new_strain,
                    ATTR_ENTITY_PICTURE: entity_picture,
                    OPB_DISPLAY_PID: new_display_strain,
                    FLOW_FORCE_SPECIES_UPDATE: force_new_strain,
                }
            )
            if plant_config[DATA_SOURCE] == DATA_SOURCE_PLANTBOOK:
                self.plant.strain = new_strain
                self.plant.add_image(plant_config[FLOW_PLANT_INFO][ATTR_ENTITY_PICTURE])
                self.plant.display_strain = plant_config[FLOW_PLANT_INFO][
                    OPB_DISPLAY_PID
                ]
                for key, value in plant_config[FLOW_PLANT_INFO][
                    FLOW_PLANT_LIMITS
                ].items():
                    set_entity = getattr(self.plant, key)
                    _LOGGER.debug("Entity: %s To: %s", set_entity, value)
                    set_entity_id = set_entity.entity_id
                    _LOGGER.debug(
                        "Setting %s to %s",
                        set_entity_id,
                        value,
                    )

                    self.hass.states.async_set(
                        set_entity_id,
                        new_state=value,
                        attributes=self.hass.states.get(set_entity_id).attributes,
                    )

            else:
                self.plant.strain = new_strain

            # We need to reset the force_update option back to False, or else
            # this will only be run once (unchanged options are will not trigger the flow)
            options = dict(entry.options)
            data = dict(entry.data)
            options[FLOW_FORCE_SPECIES_UPDATE] = False
            options[OPB_DISPLAY_PID] = self.plant.display_strain
            options[ATTR_ENTITY_PICTURE] = self.plant.entity_picture
            _LOGGER.debug(
                "Doing a refresh to update values: Data: %s Options: %s",
                data,
                options,
            )

            hass.config_entries.async_update_entry(entry, data=data, options=options)
        _LOGGER.debug("Update plant options done for %s", entry.entry_id)
        self.plant.update_registry()

