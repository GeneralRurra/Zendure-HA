"""Interfaces with the Zendure Integration api sensors."""

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.template import Template
from stringcase import snakecase

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(_hass: HomeAssistant, _config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up the Zendure sensor."""
    ZendureSensor.addSensors = async_add_entities


class ZendureSensor(SensorEntity):
    addSensors: AddEntitiesCallback

    def __init__(self, deviceinfo: DeviceInfo, uniqueid: str, template: Template | None = None, uom: str | None = None, deviceclass: Any | None = None) -> None:
        """Initialize a Zendure entity."""
        self._attr_has_entity_name = True
        self._attr_should_poll = False
        self._attr_available = True
        self.entity_description = SensorEntityDescription(key=uniqueid, name=uniqueid, native_unit_of_measurement=uom, device_class=deviceclass)
        self._attr_device_info = deviceinfo
        self._attr_unique_id = f"{deviceinfo.get('name', None)}-{uniqueid}"
        self.entity_id = f"sensor.{deviceinfo.get('name', None)}-{snakecase(uniqueid)}"
        self._attr_translation_key = snakecase(uniqueid)
        self._value_template: Template | None = template

    def update_value(self, value: Any) -> None:
        try:
            new_value = self._value_template.async_render_with_possible_json_value(value, None) if self._value_template is not None else int(value)

            if self.hass and new_value != self._attr_native_value:
                self._attr_native_value = new_value
                if self.hass and self.hass.loop.is_running():
                    self.schedule_update_ha_state()

        except Exception as err:
            self._attr_native_value = value
            _LOGGER.error(f"Error {err} setting state: {self._attr_unique_id} => {value}")
