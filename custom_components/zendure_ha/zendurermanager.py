"""Zendure Integration manager using DataUpdateCoordinator."""

from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.number import NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import DOMAIN, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from paho.mqtt import client as mqtt_client

from custom_components.zendure_ha.api import Api
from custom_components.zendure_ha.const import CONF_P1METER, LOGTYPE_BATTERY, BatteryState, SmartMode
from custom_components.zendure_ha.number import ZendureNumber, ZendureRestoreNumber
from custom_components.zendure_ha.select import ZendureRestoreSelect, ZendureSelect
from custom_components.zendure_ha.zenduredevice import ZendureDevice

_LOGGER = logging.getLogger(__name__)


class ZendureManager(DataUpdateCoordinator[int]):
    """The Zendure manager."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize ZendureManager."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({config_entry.unique_id})",
            update_interval=timedelta(seconds=90),
            always_update=True,
        )

        self._hass = hass
        self._mqtt: mqtt_client.Client | None = None
        self.p1meter = config_entry.data.get(CONF_P1METER)
        self._attr_device_info = self.attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "ZendureManager")},
            name="Zendure Manager",
            manufacturer="Fireson",
        )
        self.operation = 0
        self.state = BatteryState.IDLE
        self.setpoint = 0
        self.zero_idle = datetime.max
        self.zero_next = datetime.min
        self.zero_fast = datetime.min
        self.active: list[ZendureDevice] = []

        # Set sensors from values entered in config flow setup
        if self.p1meter:
            _LOGGER.info(f"Energy sensors: {self.p1meter} to _update_smart_energyp1")
            async_track_state_change_event(self._hass, [self.p1meter], self._update_smart_energyp1)

        # Create the api
        self.api = Api(self._hass, config_entry.data)

        if "items" in config_entry.data:
            _LOGGER.info(f"Runtime data: {config_entry.as_dict()['items']}")

    async def initialize(self) -> bool:
        """Initialize the manager."""
        try:
            if not await self.api.connect():
                return False
            ZendureDevice.devicedict = await self.api.getDevices(self._hass)
            self._mqtt = self.api.get_mqtt(self.on_message)

            try:
                for d in ZendureDevice.devicedict.values():
                    d.mqtt = self._mqtt
                    self._mqtt.subscribe(f"/{d.prodkey}/{d.hid}/#")
                    self._mqtt.subscribe(f"iot/{d.prodkey}/{d.hid}/#")
                    d.sensorsCreate()
                    d.sendRefresh()

            except Exception as err:
                _LOGGER.error(err)

            _LOGGER.info(f"Found: {len(ZendureDevice.devicedict)} devices")

            # Add ZendureManager sensors
            _LOGGER.info(f"Adding sensors {self.name}")
            selects = [
                ZendureRestoreSelect(
                    self._attr_device_info,
                    "Operation",
                    {0: "off", 1: "manual", 2: "smart"},
                    self.update_operation,
                    0,
                ),
            ]
            ZendureSelect.addSelects(selects)

            numbers = [
                ZendureRestoreNumber(
                    self.attr_device_info,
                    "manual_power",
                    self._update_manual_energy,
                    None,
                    "W",
                    "power",
                    10000,
                    -10000,
                    NumberMode.BOX,
                ),
            ]
            ZendureNumber.addNumbers(numbers)

        except Exception as err:
            _LOGGER.error(err)
            return False
        return True

    def update_operation(self, operation: int) -> None:
        _LOGGER.info(f"Update operation: {operation} from: {self.operation}")
        self.operation = operation
        self.state = BatteryState.IDLE
        for d in ZendureDevice.devices:
            d.powerState(BatteryState.IDLE)

    async def _async_update_data(self) -> int:
        """Refresh the data of all devices's."""
        _LOGGER.info("refresh devices")
        try:
            if self._mqtt:
                for d in ZendureDevice.devices:
                    d.sendRefresh()
        except Exception as err:
            _LOGGER.error(err)
        if self.hass and self.hass.loop.is_running():
            self._schedule_refresh()
        return 0

    def on_message(self, _client: Any, _userdata: Any, msg: Any) -> None:
        try:
            # check for valid device in payload
            payload = json.loads(msg.payload.decode())
            if not (deviceid := payload.get("deviceId", None)) or not (device := ZendureDevice.devicedict.get(deviceid, None)):
                # _LOGGER.info(f"Unknown topic: {msg.topic} => {payload}")
                return
            device.lastUpdate = datetime.now() + timedelta(seconds=30)

            topics = msg.topic.split("/")
            parameter = topics[-1]

            # _LOGGER.info(f"Topic: {msg.topic} => {payload}")
            match parameter:
                case "report":
                    if properties := payload.get("properties", None):
                        for key, value in properties.items():
                            if device.updateProperty(key, value):
                                match key:
                                    case "packInputPower":
                                        device.powerActual(int(value))
                                    case "outputPackPower":
                                        device.powerActual(-int(value))

                    if batprops := payload.get("packData", None):
                        # get the battery serial numbers
                        if properties and properties.get("packNum", None):
                            device.batteries = [bat["sn"] for bat in batprops if "sn" in bat]
                            _LOGGER.info(f"Update batteries: {device.batteries}")

                        # update the battery properties
                        for bat in batprops:
                            sn = bat.pop("sn")
                            if sn in device.batteries:
                                idx = list.index(device.batteries, sn) + 1
                                for key, value in bat.items():
                                    device.updateProperty(f"battery {idx} {key}", value)

                case "config":
                    # _LOGGER.info(f"Receive: {device.hid} => event: {payload}")
                    return

                case "device":
                    # if topics[-2] == "event":
                    #     _LOGGER.info(f"Receive: {device.hid} => event: {payload}")
                    return

                case "error":
                    # if topics[-2] == "event":
                    #     _LOGGER.info(f"Receive: {device.hid} => error: {payload}")
                    return

                case "reply":
                    # if topics[-3] == "function":
                    _LOGGER.info(f"Receive: {device.hid} => ready!")
                    return

                case "log":
                    if payload["logType"] == LOGTYPE_BATTERY:
                        device.updateBattery(payload["log"]["params"])

                # case _:
                #     _LOGGER.info(f"Unknown topic {msg.topic} => {payload}")

        except Exception as err:
            _LOGGER.error(err)
            _LOGGER.error(traceback.format_exc())

    @callback
    def _update_manual_energy(self, _number: Any, power: float) -> None:
        try:
            if self.operation == SmartMode.MANUAL:
                self.updateState(BatteryState.DISCHARGING if power >= 0 else BatteryState.CHARGING)
                self.updateSetpoint(int(power), datetime.now())

        except Exception as err:
            _LOGGER.error(err)
            _LOGGER.error(traceback.format_exc())

    @callback
    def _update_smart_energyp1(self, event: Event[EventStateChangedData]) -> None:
        try:
            # exit if there is nothing to do
            if (new_state := event.data["new_state"]) is None or self.operation == SmartMode.NONE:
                return

            # check minimal time between updates
            time = datetime.now()
            p1 = int(float(new_state.state))
            if time < self.zero_next or (time < self.zero_fast and abs(p1) < SmartMode.FAST_UPDATE):
                return

            # get the current power, exit if a device is waiting
            powerActual = 0
            for d in ZendureDevice.devices:
                if d.lastUpdate > time and d.waitTime > time:
                    return
                powerActual += d.powerAct

            # update the setpoint
            if self.operation == SmartMode.MANUAL:
                self.updateSetpoint(self.setpoint, time)
            elif self.state == BatteryState.CHARGING:
                self.updateSetpoint(powerActual + p1 + 50, time)
            else:
                self.updateSetpoint(powerActual + p1, time)

            self.zero_next = time + timedelta(seconds=SmartMode.TIMEZERO)
            self.zero_fast = time + timedelta(seconds=SmartMode.TIMEFAST)

            if self.operation == SmartMode.MATCHING:
                if powerActual != 0:
                    self.zero_idle = datetime.max
                elif self.zero_idle == datetime.max and abs(p1) > SmartMode.START_POWER:
                    self.zero_idle = time + timedelta(seconds=SmartMode.TIMEIDLE)
                elif self.zero_idle < time:
                    self.updateState(BatteryState.DISCHARGING if p1 >= 0 else BatteryState.CHARGING)

        except Exception as err:
            _LOGGER.error(err)
            _LOGGER.error(traceback.format_exc())

    def updateSetpoint(self, power: int, time: datetime) -> None:
        """Update the setpoint for all devices."""
        if self.setpoint == power:
            return
        _LOGGER.info(f"Update setpoint: {power} from: {self.setpoint} state{self.state}")

        # update the device and get totals
        capacity = 0
        powerMax = 0
        for d in ZendureDevice.devices:
            if d.waitTime > time:
                return
            d.waitTime = datetime.min
            if self.state == BatteryState.IDLE or d.clusterType == 0:
                d.capacity = 0
            elif self.state == BatteryState.DISCHARGING:
                d.capacity = d.asInt("packNum") * (d.asInt("electricLevel") - d.asInt("socMin"))
                powerMax += d.powerMax
            else:
                d.capacity = max(0, d.asInt("packNum") * (d.asInt("socSet") - d.asInt("electricLevel")))
                powerMax += abs(d.powerMin)
            capacity += d.capacity

        # redistribute the power on clusters
        self.setpoint = power
        active = sorted(ZendureDevice.clusters, key=lambda d: d.clustercapacity, reverse=power > powerMax / 2)
        for d in active:
            pwr = int(power * d.capacity / capacity) if capacity > 0 else 0
            capacity -= d.clustercapacity
            pwr = max(0, min(d.clusterMax, pwr)) if self.state == BatteryState.DISCHARGING else min(0, max(d.clusterMin, pwr))
            if abs(pwr) > 0:
                if capacity == 0:
                    pwr = max(0, min(d.clusterMax, power)) if self.state == BatteryState.DISCHARGING else min(0, max(d.clusterMin, power))
                elif abs(pwr) > SmartMode.START_POWER or (abs(pwr) > SmartMode.MIN_POWER and d.powerAct != 0):
                    power -= pwr
                else:
                    pwr = 0

            # update the device
            d.clusterSet(self.state, pwr)

    def updateState(self, state: BatteryState) -> None:
        """Update the state of the manager."""
        if self.state == state:
            return
        _LOGGER.info(f"Update state: {state} from: {self.state}")
        self.state = state

        # update the devices
        for d in ZendureDevice.devices:
            d.powerState(state)
