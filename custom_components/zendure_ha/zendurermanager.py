"""Zendure Integration manager using DataUpdateCoordinator."""

from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timedelta
from typing import Any

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from homeassistant.components import bluetooth
from homeassistant.components.number import NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntry, DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from paho.mqtt import client as mqtt_client

from .api import Api
from .const import CONF_BROKER, CONF_BROKERPSW, CONF_BROKERUSER, CONF_P1METER, CONF_WIFIPSW, CONF_WIFISSID, DOMAIN, ManagerState, SmartMode
from .devices.ace1500 import ACE1500
from .devices.aio2400 import AIO2400
from .devices.hub1000 import Hub1000
from .devices.hub1200 import Hub1200
from .devices.hub2000 import Hub2000
from .devices.hyper2000 import Hyper2000
from .devices.solarflow800 import SolarFlow800
from .devices.solarflow2400ac import SolarFlow2400AC
from .number import ZendureNumber, ZendureRestoreNumber
from .select import ZendureRestoreSelect, ZendureSelect
from .zenduredevice import ZendureDevice, ZendureDeviceDefinition

_LOGGER = logging.getLogger(__name__)

ZENDURE_MANAGER_STORAGE_VERSION = 1
ZENDURE_DEVICES = "devices"


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
            model="Zendure Manager",
            name="Zendure Manager",
            manufacturer="Fireson",
        )

        # get the local settings
        self.broker = config_entry.data.get(CONF_BROKER, None)
        self.brokeruser = config_entry.data.get(CONF_BROKERUSER, None)
        self.brokerpsw = config_entry.data.get(CONF_BROKERPSW, None)
        self.wifissid = config_entry.data.get(CONF_WIFISSID, None)
        self.wifipsw = config_entry.data.get(CONF_WIFIPSW, None)
        self.uselocal = self.broker and self.brokeruser and self.brokerpsw and self.wifissid and self.wifipsw

        self.operation = 0
        self.setpoint = 0
        self.zero_idle = datetime.max
        self.zero_next = datetime.min
        self.zero_fast = datetime.min
        self.active: list[ZendureDevice] = []
        self.store: Store | None = None

        # Set sensors from values entered in config flow setup
        if self.p1meter:
            _LOGGER.info(f"Energy sensors: {self.p1meter} to _update_smart_energyp1")
            async_track_state_change_event(self._hass, [self.p1meter], self._update_smart_energyp1)

        # Create the api
        self.api = Api(self._hass, dict(config_entry.data))

        if "items" in config_entry.data:
            _LOGGER.info(f"Runtime data: {config_entry.as_dict()['items']}")

    async def initialize(self) -> bool:
        """Initialize the manager."""
        try:
            if not await self.api.connect():
                _LOGGER.error("Unable to connect to Zendure API")
                return False

            # create the zendure cloud mqtt client
            self._mqtt = self.api.get_mqtt(self.on_message)

            # load configuration from storage
            self.store = Store(self.hass, ZENDURE_MANAGER_STORAGE_VERSION, f"{DOMAIN}.storage")
            definitions = dict[str, ZendureDeviceDefinition]()
            if (storage := await self.store.async_load()) and isinstance(storage, dict):
                definitions = storage.get(ZENDURE_DEVICES, {})

            # load the devices from the api & add them to the storage
            api_devices = await self.api.getDevices()
            for key, definition in api_devices.items():
                definitions[key] = definition
            await self.store.async_save({ZENDURE_DEVICES: definitions})

            # create the devices
            await self.createDevices(definitions)
            _LOGGER.info(f"Found: {len(ZendureDevice.devicedict)} devices")

            # initialize the devices
            for device in ZendureDevice.devices:
                await device.initialize(self._mqtt)

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

    async def createDevices(self, definitions: dict[str, ZendureDeviceDefinition]) -> None:
        # Create the devices
        for deviceKey, deviceDef in definitions.items():
            try:
                match deviceDef.productName:
                    case "Hyper 2000":
                        device = Hyper2000(self._hass, deviceKey, deviceDef)
                    case "SolarFlow 800":
                        device = SolarFlow800(self._hass, deviceKey, deviceDef)
                    case "Hub 1000":
                        device = Hub1000(self._hass, deviceKey, deviceDef)
                    case "SolarFlow2.0":
                        device = Hub1200(self._hass, deviceKey, deviceDef)
                    case "SolarFlow Hub 2000":
                        device = Hub2000(self._hass, deviceKey, deviceDef)
                    case "SolarFlow AIO ZY":
                        device = AIO2400(self._hass, deviceKey, deviceDef)
                    case "Ace 1500":
                        device = ACE1500(self._hass, deviceKey, deviceDef)
                    case "SolarFlow 2400 AC":
                        device = SolarFlow2400AC(self._hass, deviceKey, deviceDef)
                    case _:
                        _LOGGER.info(f"Device {deviceDef.productName} is not supported!")
                        continue

                ZendureDevice.devicedict[deviceKey] = device
            except Exception as err:
                _LOGGER.error(err)

    async def unload(self) -> None:
        """Unload the manager."""
        if self._mqtt:
            for device in ZendureDevice.devices:
                self._mqtt.unsubscribe(f"/{device.prodkey}/{device.hid}/#")
                self._mqtt.unsubscribe(f"iot/{device.prodkey}/{device.hid}/#")
            self._mqtt.disconnect()

    async def remove_device(self, device_entry: DeviceEntry) -> None:
        """Remove a device from the manager."""
        for device in ZendureDevice.devices:
            if device.name == device_entry.name:
                _LOGGER.info(f"Remove device: {device_entry} => {device}")
                if self._mqtt:
                    self._mqtt.unsubscribe(f"/{device.prodkey}/{device.hid}/#")
                    self._mqtt.unsubscribe(f"iot/{device.prodkey}/{device.hid}/#")

                ZendureDevice.devicedict.pop(device.hid, None)
                ZendureDevice.devices.remove(device)

                # remove the device from the storage
                if self.store:
                    storage = await self.store.async_load()
                    if storage and isinstance(storage, dict):
                        devices = storage.get(ZENDURE_DEVICES, {})
                        if devices and device.hid in devices:
                            del devices[device.hid]
                            await self.store.async_save({ZENDURE_DEVICES: devices})
                return

    async def _device_detected(self, device: BLEDevice, advertisement_data: AdvertisementData) -> None:
        """Handle a detected device."""
        if advertisement_data.local_name and advertisement_data.local_name.startswith("Zen"):
            _LOGGER.info(f"Found Zendure BLE device: {device.name} => {advertisement_data}")

        # id = advertisement_data.manufacturer_data.get(0x004C, None)

    def update_operation(self, operation: int) -> None:
        _LOGGER.info(f"Update operation: {operation} from: {self.operation}")

        if operation == self.operation:
            return

        self.operation = operation
        if self.operation != SmartMode.MATCHING:
            for d in ZendureDevice.devices:
                d.powerSet(0, self.operation == SmartMode.MANUAL)

        # One device always has it's own phase
        if len(ZendureDevice.devices) == 1 and not ZendureDevice.devices[0].clusterdevices:
            ZendureDevice.devices[0].clusterType = 1
            ZendureDevice.devices[0].clusterdevices = [ZendureDevice.devices[0]]
            ZendureDevice.clusters = [ZendureDevice.devices[0]]

    async def _async_update_data(self) -> int:
        """Refresh the data of all devices's."""
        _LOGGER.info("refresh devices")
        try:
            if self._mqtt:
                for d in ZendureDevice.devices:
                    d.sendRefresh()

            # if self.uselocal:
            #     _LOGGER.info("Check for bluetooth devices ...")
            #     bleak_scanner = bluetooth.async_get_scanner(self._hass)
            #     bleak_scanner.register_detection_callback(self._device_detected)

        except Exception as err:
            _LOGGER.error(err)
        if self.hass and self.hass.loop.is_running():
            self._schedule_refresh()
        return 0

    def on_message(self, _client: Any, _userdata: Any, msg: Any) -> None:
        try:
            # check for valid device in payload
            payload = json.loads(msg.payload.decode())
            if (deviceid := payload.get("deviceId", None)) and (device := ZendureDevice.devicedict.get(deviceid, None)):
                device.message(msg.topic, payload)

        except:  # noqa: E722
            return

    @callback
    def _update_manual_energy(self, _number: Any, power: float) -> None:
        try:
            if self.operation == SmartMode.MANUAL:
                self.setpoint = int(power)
                self.updateSetpoint(self.setpoint, ManagerState.DISCHARGING if power >= 0 else ManagerState.CHARGING)

        except Exception as err:
            _LOGGER.error(err)
            _LOGGER.error(traceback.format_exc())

    @callback
    def _update_smart_energyp1(self, event: Event[EventStateChangedData]) -> None:
        try:
            # exit if there is nothing to do
            if (new_state := event.data["new_state"]) is None or new_state.state == "unknown" or self.operation == SmartMode.NONE:
                return

            # check minimal time between updates
            time = datetime.now()
            p1 = int(float(new_state.state))
            if time < self.zero_next or (time < self.zero_fast and abs(p1) < SmartMode.FAST_UPDATE):
                return

            # get the current power, exit if a device is waiting
            powerActual = 0
            for d in ZendureDevice.devices:
                d.powerAct = d.asInt("packInputPower") - (d.asInt("outputPackPower") - d.asInt("solarInputPower"))
                powerActual += d.powerAct

            _LOGGER.info(f"Update p1: {p1} power: {powerActual} operation: {self.operation}")
            # update the setpoint
            if self.operation == SmartMode.MANUAL:
                self.updateSetpoint(self.setpoint, ManagerState.DISCHARGING if self.setpoint >= 0 else ManagerState.CHARGING)
            elif powerActual < 0:
                powerActual = powerActual + p1 + (SmartMode.START_POWER if powerActual == 0 else SmartMode.MIN_POWER)
                self.updateSetpoint(min(0, powerActual), ManagerState.CHARGING)
            elif powerActual > 0:
                self.updateSetpoint(max(0, powerActual + p1), ManagerState.DISCHARGING)
            elif self.zero_idle == datetime.max:
                _LOGGER.info(f"Wait 10 sec for state change p1: {p1}")
                self.zero_idle = time + timedelta(seconds=SmartMode.TIMEIDLE)
            elif self.zero_idle < time:
                _LOGGER.info(f"Update state: p1: {p1}")
                self.updateSetpoint(p1, ManagerState.DISCHARGING if p1 >= 0 else ManagerState.CHARGING)
                self.zero_idle = datetime.max

            self.zero_next = time + timedelta(seconds=SmartMode.TIMEZERO)
            self.zero_fast = time + timedelta(seconds=SmartMode.TIMEFAST)

        except Exception as err:
            _LOGGER.error(err)
            _LOGGER.error(traceback.format_exc())

    def updateSetpoint(self, power: int, state: ManagerState) -> None:
        """Update the setpoint for all devices."""
        totalCapacity = 0
        totalPower = 0
        for d in ZendureDevice.devices:
            if state == ManagerState.DISCHARGING:
                d.capacity = max(0, d.asInt("packNum") * (d.asInt("electricLevel") - d.asInt("minSoc")))
                _LOGGER.info(f"Update capacity: {d.name} {d.capacity} = {d.asInt('packNum')} * ({d.asInt('electricLevel')} - {d.asInt('minSoc')})")
                totalPower += d.powerMax
            else:
                d.capacity = max(0, d.asInt("packNum") * (d.asInt("socSet") - d.asInt("electricLevel")))
                _LOGGER.info(f"Update capacity: {d.name} {d.capacity} = {d.asInt('packNum')} * ({d.asInt('socSet')} - {d.asInt('electricLevel')})")
                totalPower += abs(d.powerMin)
            if d.clusterType == 0:
                d.capacity = 0
            totalCapacity += d.capacity

        _LOGGER.info(f"Update setpoint: {power} state{state} capacity: {totalCapacity} max: {totalPower}")

        # redistribute the power on clusters
        isreverse = bool(abs(power) > totalPower / 2)
        active = sorted(ZendureDevice.clusters, key=lambda d: d.clustercapacity, reverse=isreverse)
        for c in active:
            clusterCapacity = c.clustercapacity
            clusterPower = int(power * clusterCapacity / totalCapacity) if totalCapacity > 0 else 0
            clusterPower = max(0, min(c.clusterMax, clusterPower)) if state == ManagerState.DISCHARGING else min(0, max(c.clusterMin, clusterPower))
            totalCapacity -= clusterCapacity

            if totalCapacity == 0:
                clusterPower = max(0, min(c.clusterMax, power)) if state == ManagerState.DISCHARGING else min(0, max(c.clusterMin, power))
            elif abs(clusterPower) > 0 and (abs(clusterPower) < SmartMode.MIN_POWER or (abs(clusterPower) < SmartMode.START_POWER and c.powerAct == 0)):
                clusterPower = 0

            for d in sorted(c.clusterdevices, key=lambda d: d.capacity, reverse=isreverse):
                if d.capacity == 0:
                    continue
                pwr = int(clusterPower * d.capacity / clusterCapacity) if clusterCapacity > 0 else 0
                clusterCapacity -= d.capacity
                pwr = max(0, min(d.powerMax, pwr)) if state == ManagerState.DISCHARGING else min(0, max(d.powerMin, pwr))
                if abs(pwr) > 0:
                    if clusterCapacity == 0:
                        pwr = max(0, min(d.powerMax, clusterPower)) if state == ManagerState.DISCHARGING else min(0, max(d.powerMin, clusterPower))
                    elif abs(pwr) > SmartMode.START_POWER or (abs(pwr) > SmartMode.MIN_POWER and d.powerAct != 0):
                        clusterPower -= pwr
                    else:
                        pwr = 0
                power -= pwr

                # update the device
                _LOGGER.info(f"Update power: {d.name} {pwr}")
                d.powerSet(pwr, True)
