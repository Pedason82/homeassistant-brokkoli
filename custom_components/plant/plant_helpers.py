"""Plant helper functions"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.const import ATTR_ENTITY_PICTURE, ATTR_NAME
from homeassistant.core import HomeAssistant

from .const import (
    ATTR_BREEDER,
    ATTR_BRIGHTNESS,
    ATTR_CONDUCTIVITY,
    ATTR_FLOWERING_DURATION,
    ATTR_HUMIDITY,
    ATTR_ILLUMINANCE,
    ATTR_LIMITS,
    ATTR_MOISTURE,
    ATTR_PID,
    ATTR_SENSORS,
    ATTR_STRAIN,
    ATTR_TEMPERATURE,
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
    DATA_SOURCE_MANUAL,
    DATA_SOURCE_PLANTBOOK,
    DEFAULT_MAX_CONDUCTIVITY,
    DEFAULT_MAX_DLI,
    DEFAULT_MAX_HUMIDITY,
    DEFAULT_MAX_ILLUMINANCE,
    DEFAULT_MAX_MOISTURE,
    DEFAULT_MAX_TEMPERATURE,
    DEFAULT_MIN_CONDUCTIVITY,
    DEFAULT_MIN_DLI,
    DEFAULT_MIN_HUMIDITY,
    DEFAULT_MIN_ILLUMINANCE,
    DEFAULT_MIN_MOISTURE,
    DEFAULT_MIN_TEMPERATURE,
    DOMAIN_PLANTBOOK,
    FLOW_PLANT_INFO,
    OPB_DISPLAY_PID,
    OPB_GET,
    DEVICE_TYPE_CYCLE,
    ATTR_DEVICE_TYPE,
)

_LOGGER = logging.getLogger(__name__)

class PlantHelper:
    """Helper class for plant component."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the helper."""
        self._hass = hass
        self.has_openplantbook = DOMAIN_PLANTBOOK in hass.config.components

    async def get_plantbook_data(self, config: dict) -> dict:
        """Get plant data from OpenPlantbook."""
        if not self.has_openplantbook:
            return {}

        strain = config.get(ATTR_STRAIN)
        breeder = config.get(ATTR_BREEDER)
        if not strain:
            return {}

        try:
            result = await self._hass.services.async_call(
                DOMAIN_PLANTBOOK,
                OPB_GET,
                {
                    "species": strain,
                    "breeder": breeder
                },
                blocking=True,
                return_response=True
            )
            
            if result:
                _LOGGER.debug("Raw OpenPlantbook response: %s", result)
                ret = {}
                ret[FLOW_PLANT_INFO] = {
                    DATA_SOURCE: DATA_SOURCE_PLANTBOOK,
                    ATTR_PID: result.get("pid", ""),
                    ATTR_STRAIN: result.get("strain", strain),
                    ATTR_BREEDER: result.get("breeder", breeder),
                    ATTR_ENTITY_PICTURE: result.get("image_url", ""),
                    OPB_DISPLAY_PID: result.get("strain", ""),
                    ATTR_FLOWERING_DURATION: int(result.get("flowertime", "0")),
                    "sorte": result.get("sorte", ""),
                    "feminized": result.get("feminized", ""),
                    "timestamp": result.get("timestamp", ""),
                    "website": result.get("website", ""),
                    "infotext1": result.get("infotext1", ""),
                    "infotext2": result.get("infotext2", ""),
                    "effects": result.get("effects", ""),
                    "smell": result.get("smell", ""),
                    "taste": result.get("taste", ""),
                    "lineage": result.get("lineage", ""),
                }

                # Add default limits
                ret[FLOW_PLANT_INFO][ATTR_LIMITS] = {
                    CONF_MAX_MOISTURE: DEFAULT_MAX_MOISTURE,
                    CONF_MIN_MOISTURE: DEFAULT_MIN_MOISTURE,
                    CONF_MAX_ILLUMINANCE: DEFAULT_MAX_ILLUMINANCE,
                    CONF_MIN_ILLUMINANCE: DEFAULT_MIN_ILLUMINANCE,
                    CONF_MAX_TEMPERATURE: DEFAULT_MAX_TEMPERATURE,
                    CONF_MIN_TEMPERATURE: DEFAULT_MIN_TEMPERATURE,
                    CONF_MAX_CONDUCTIVITY: DEFAULT_MAX_CONDUCTIVITY,
                    CONF_MIN_CONDUCTIVITY: DEFAULT_MIN_CONDUCTIVITY,
                    CONF_MAX_HUMIDITY: DEFAULT_MAX_HUMIDITY,
                    CONF_MIN_HUMIDITY: DEFAULT_MIN_HUMIDITY,
                    CONF_MAX_DLI: DEFAULT_MAX_DLI,
                    CONF_MIN_DLI: DEFAULT_MIN_DLI,
                }
                return ret

        except Exception as ex:
            _LOGGER.warning("Unable to get OpenPlantbook data: %s", ex)
            
        return {}

    async def generate_configentry(self, config: dict) -> dict[str:Any]:
        """Generate a config entry."""
        _LOGGER.debug("Generating config entry for %s", config)
        ret = {}
        ret[FLOW_PLANT_INFO] = {}

        # Get OpenPlantbook data if available
        if self.has_openplantbook and config.get(ATTR_DEVICE_TYPE) != DEVICE_TYPE_CYCLE:
            opb_config = await self.get_plantbook_data(config)
            if opb_config:
                ret.update(opb_config)
                return ret

        # Basis-Attribute für beide Typen
        base_info = {
            ATTR_NAME: config[ATTR_NAME],
            ATTR_STRAIN: config.get(ATTR_STRAIN, ""),
            ATTR_BREEDER: config.get(ATTR_BREEDER, ""),
            DATA_SOURCE: DATA_SOURCE_MANUAL,
            ATTR_ENTITY_PICTURE: config.get(ATTR_ENTITY_PICTURE, ""),
            OPB_DISPLAY_PID: config.get(OPB_DISPLAY_PID, ""),
            ATTR_FLOWERING_DURATION: config.get(ATTR_FLOWERING_DURATION, "0"),
            "pid": "",
            "sorte": "",
            "feminized": "",
            "timestamp": "",
            "website": "",
            "effects": "",
            "smell": "",
            "taste": "",
            "phenotype": "",
            "hunger": "",
            "growth_stretch": "",
            "flower_stretch": "",
            "mold_resistance": "",
            "difficulty": "",
            "yield": "",
            "notes": "",
        }

        # Füge lineage und infotexte nur für Plants hinzu
        if config.get(ATTR_DEVICE_TYPE) != DEVICE_TYPE_CYCLE:
            base_info.update({
                "lineage": "",
                "infotext1": "",
                "infotext2": "",
            })

        ret[FLOW_PLANT_INFO] = base_info

        # Füge die Standard-Grenzwerte hinzu
        ret[FLOW_PLANT_INFO][ATTR_LIMITS] = {
            CONF_MAX_MOISTURE: DEFAULT_MAX_MOISTURE,
            CONF_MIN_MOISTURE: DEFAULT_MIN_MOISTURE,
            CONF_MAX_ILLUMINANCE: DEFAULT_MAX_ILLUMINANCE,
            CONF_MIN_ILLUMINANCE: DEFAULT_MIN_ILLUMINANCE,
            CONF_MAX_TEMPERATURE: DEFAULT_MAX_TEMPERATURE,
            CONF_MIN_TEMPERATURE: DEFAULT_MIN_TEMPERATURE,
            CONF_MAX_CONDUCTIVITY: DEFAULT_MAX_CONDUCTIVITY,
            CONF_MIN_CONDUCTIVITY: DEFAULT_MIN_CONDUCTIVITY,
            CONF_MAX_HUMIDITY: DEFAULT_MAX_HUMIDITY,
            CONF_MIN_HUMIDITY: DEFAULT_MIN_HUMIDITY,
            CONF_MAX_DLI: DEFAULT_MAX_DLI,
            CONF_MIN_DLI: DEFAULT_MIN_DLI,
        }

        _LOGGER.debug("Resulting config: %s", ret)
        return ret
