"""Zendure Integration device."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from math import asin
from typing import Any

from homeassistant.components.number import NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.template import Template
from paho.mqtt import client as mqtt_client

from .binary_sensor import ZendureBinarySensor
from .const import DOMAIN
from .number import ZendureNumber
from .select import ZendureSelect
from .sensor import ZendureSensor
from .switch import ZendureSwitch
from .zendurephase import ZendurePhase

_LOGGER = logging.getLogger(__name__)


class BatteryState:
    OFF = 0
    CHARGING = 1
    DISCHARGING = 2


class ZendureDevice:
    """A Zendure Device."""

    batteryState = BatteryState.OFF
    _devices: list[ZendureDevice] = []
    _messageid = 0

    def __init__(self, hass: HomeAssistant, h_id: str, h_prod: str, name: str, model: str) -> None:
        """Initialize ZendureDevice."""
        self._hass = hass
        self.hid = h_id
        self.prodkey = h_prod
        self.name = name
        self.unique = "".join(name.split())
        self.attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.name)},
            name=self.name,
            manufacturer="Zendure",
            model=model,
        )
        self._topic_read = f"iot/{self.prodkey}/{self.hid}/properties/read"
        self._topic_write = f"iot/{self.prodkey}/{self.hid}/properties/write"
        self.topic_function = f"iot/{self.prodkey}/{self.hid}/function/invoke"
        self.mqtt: mqtt_client.Client
        self.entities: dict[str, Any] = {}
        self._devices.append(self)
        self.phase: ZendurePhase | None = None

        self.lastUpdate = datetime.now()
        self.batteryMax = 0
        self.chargemax = 0
        self.dischargemax = 0
        self.setpoint = 0
        self.setpointOutput = 0
        self.capacity = 0
        self.power = 0
        self.adjust = 0

    def updateProperty(self, key: Any, value: Any) -> bool:
        self.lastUpdate = datetime.now()
        if sensor := self.entities.get(key, None):
            if sensor.state != value:
                sensor.update_value(value)
                return True
        elif isinstance(value, (int | float)):
            self._hass.loop.call_soon_threadsafe(self.sensorAdd, key, value)
            return True
        else:
            _LOGGER.info(f"Found unknown state value:  {self.hid} {key} => {value}")
        return False

    def sensorsCreate(self) -> None:
        return

    def sendRefresh(self) -> None:
        self.mqtt.publish(self._topic_read, '{"properties": ["getAll"]}')

    def writeProperty(self, entity: Entity, value: Any) -> None:
        _LOGGER.info(f"Writing property {self.name} {entity.name} => {value}")
        ZendureDevice._messageid += 1
        if entity.unique_id is None:
            _LOGGER.error(f"Entity {entity.name} has no unique_id.")
            return

        property_name = entity.unique_id[(len(self.name) + 1) :]
        if property_name in {"minSoc", "socSet"}:
            value = int(value * 10)

        self.writeProperties({property_name: value})

    def writeProperties(self, props: dict[str, Any]) -> None:
        ZendureDevice._messageid += 1
        payload = json.dumps(
            {
                "deviceId": self.hid,
                "messageId": ZendureDevice._messageid,
                "timestamp": int(datetime.now().timestamp()),
                "properties": props,
            },
            default=lambda o: o.__dict__,
        )
        self.mqtt.publish(self._topic_write, payload)

    def sensorAdd(self, propertyname: str, value: Any | None = None) -> None:
        try:
            _LOGGER.info(f"{self.hid} {self.name}new sensor: {propertyname}")
            sensor = ZendureSensor(self.attr_device_info, propertyname, logchanges=1)
            self.entities[propertyname] = sensor
            ZendureSensor.addSensors([sensor])
            if value:
                sensor.update_value(value)
        except Exception as err:
            _LOGGER.error(err)

    def updateBattery(self, data: list[int]) -> None:
        batPct = data[0]

        # _LOGGER.info(f"update_battery: {self.name} => {data}")
        # for i in range(data[1]):

        #     def value(idx: int) -> int:
        #         return data[idx * 4 + 2 + i]

        #     soc = value(0)
        #     vollt = value(1) * 10
        #     curr = value(2) / 10
        #     temp = value(8)
        #     _LOGGER.info(f"update_battery cell: {i} => {soc} {vollt} {curr} {temp}")

        # _LOGGER.info(f"update_battery: {self.hid} => {batPct}")

    def function_invoke(self, command: Any) -> None:
        ZendureDevice._messageid += 1
        payload = json.dumps(
            command,
            default=lambda o: o.__dict__,
        )
        self.mqtt.publish(self.topic_function, payload)

    def power_off(self) -> None:
        if self.asInt("packState") == 0 and self.asInt("autoModel") == 0:
            return
        _LOGGER.info(f"power off: {self.name} set: 0 from {self.power} capacity:{self.capacity} max:{self.chargemax}")

        self.setpoint = 0
        self.function_invoke({
            "arguments": [
                {
                    "autoModelProgram": 0,
                    "autoModelValue": {"chargingType": 0, "outPower": 0},
                    "msgType": 1,
                    "autoModel": 0,
                }
            ],
            "deviceKey": self.hid,
            "function": "deviceAutomation",
            "messageId": ZendureDevice._messageid,
            "timestamp": int(datetime.now().timestamp()),
        })

    def updateSetpoint(self, _setpoint: int | None = None) -> None:
        """Update setpoint."""
        return

    @staticmethod
    def updateDistribution(setpoint: int, checkIdle: bool = False) -> None:
        """Update distribution."""
        totalCapacity = 0
        totalSetpoint = 0
        for p in ZendurePhase.phases:
            p.capacity = 0

        isIdle = True
        for d in ZendureDevice._devices:
            if ZendureDevice.batteryState == BatteryState.DISCHARGING:
                d.capacity = max(0, d.asInt("packNum") * (d.asInt("electricLevel") - d.asInt("socMin")))
            else:
                d.capacity = max(0, d.asInt("packNum") * (d.asInt("socSet") - d.asInt("electricLevel")))

            if d.phase:
                d.phase.capacity += d.capacity
            totalCapacity += d.capacity
            totalSetpoint += d.power
            if d.asInt("packState") > 0:
                isIdle = False

        # update smart matching
        if checkIdle and isIdle:
            ZendureDevice.batteryState = BatteryState.DISCHARGING if setpoint > 0 else BatteryState.CHARGING
            _LOGGER.info(f"update batteryState: {ZendureDevice.batteryState}")

        # Update the setpoint & max of each device/phase
        if totalCapacity != 0:
            _LOGGER.info(f"update distribution {setpoint} totalSetpoint: {totalSetpoint}")
            for d in ZendureDevice._devices:
                diff = d.power - (totalSetpoint * d.capacity / totalCapacity)
                if abs(diff) > 30 and d.power > 30:
                    _LOGGER.info(f"Adjust distribution {d.name} diff: {diff}")
                    d.updateSetpoint(int(-diff + setpoint * d.capacity / totalCapacity))
                else:
                    _LOGGER.info(f"Adjust distribution {d.name} setpoint")
                    d.updateSetpoint(int(setpoint * d.capacity / totalCapacity))

    def binary(
        self,
        uniqueid: str,
        template: str | None = None,
        deviceclass: Any | None = None,
    ) -> ZendureBinarySensor:
        tmpl = Template(template, self._hass) if template else None
        s = ZendureBinarySensor(self.attr_device_info, uniqueid, tmpl, deviceclass)
        self.entities[uniqueid] = s
        return s

    def number(
        self,
        uniqueid: str,
        template: str | None = None,
        uom: str | None = None,
        deviceclass: Any | None = None,
        minimum: int = 0,
        maximum: int = 2000,
        mode: NumberMode = NumberMode.AUTO,
    ) -> ZendureNumber:
        def _write_property(entity: Entity, value: Any) -> None:
            self.writeProperty(entity, value)

        tmpl = Template(template, self._hass) if template else None
        s = ZendureNumber(
            self.attr_device_info,
            uniqueid,
            _write_property,
            tmpl,
            uom,
            deviceclass,
            maximum,
            minimum,
            mode,
        )
        self.entities[uniqueid] = s
        return s

    def select(self, uniqueid: str, options: dict[int, str], onwrite: Callable) -> ZendureSelect:
        s = ZendureSelect(self.attr_device_info, uniqueid, options, onwrite)
        self.entities[uniqueid] = s
        return s

    def sensor(
        self,
        uniqueid: str,
        template: str | None = None,
        uom: str | None = None,
        deviceclass: Any | None = None,
        logchanges: int = 0,
    ) -> ZendureSensor:
        tmpl = Template(template, self._hass) if template else None
        s = ZendureSensor(self.attr_device_info, uniqueid, tmpl, uom, deviceclass, logchanges)
        self.entities[uniqueid] = s
        return s

    def switch(
        self,
        uniqueid: str,
        template: str | None = None,
        deviceclass: Any | None = None,
    ) -> ZendureSwitch:
        def _write_property(entity: Entity, value: Any) -> None:
            self.writeProperty(entity, value)

        tmpl = Template(template, self._hass) if template else None
        s = ZendureSwitch(self.attr_device_info, uniqueid, _write_property, tmpl, deviceclass)
        self.entities[uniqueid] = s
        return s

    def asInt(self, name: str) -> int:
        if (sensor := self.entities.get(name, None)) and sensor.state:
            return int(sensor.state)
        return 0

    def isInt(self, name: str) -> int | None:
        if (sensor := self.entities.get(name, None)) and sensor.state:
            return int(sensor.state)
        return None

    def asFloat(self, name: str) -> float:
        if (sensor := self.entities.get(name, None)) and sensor.state:
            return float(sensor.state)
        return 0

    def isEqual(self, name: str, value: Any) -> bool:
        if (sensor := self.entities.get(name, None)) and sensor.state:
            return sensor.state == value
        return False


class AcMode:
    INPUT = 1
    OUTPUT = 2
