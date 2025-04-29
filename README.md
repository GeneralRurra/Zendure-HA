# Zendure Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

![Zendure Product](https://github.com/user-attachments/assets/393fec2b-af03-4876-a2d3-3bb3111de1d0)

Welcome to the **Zendure Home Assistant Integration**!

This integration allows you to control, monitor, and optimize your Zendure devices through Home Assistant — either via the Cloud or directly using MQTT.

---

## ✨ Features
- Connection to the **Zendure Cloud API** & **MQTT server**.
- **Local MQTT operation** without cloud dependency.
- Dynamic **energy optimization** (Smart Matching via P1 sensor).
- Supports **SolarFlow**, **Hyper 2000**, **Hub 1000/1200/2000**, **AIO 2400**, and more.
- Management of **device clusters** and **battery modules**.
- Extensive **Sensors**, **Switches**, **Numbers**, and **Selects** for each device type.

---

## 🔄 Installation

### 1. Installation via HACS (**recommended**)

The easiest and recommended method is installation via HACS (Home Assistant Community Store).

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=FireSon&repository=Zendure-HA&category=integration)

**Steps:**
1. Make sure you have [HACS](https://hacs.xyz/) installed.
2. Open Home Assistant → **HACS** → **Integrations** → **Add custom repository**.
3. Manually add the following repository:
   ```
   https://github.com/FireSon/Zendure-HA
   ```
4. Choose **Category: Integration**.
5. Search for **Zendure Home Assistant Integration** and install it.

> Find a HACS installation guide here: [Domotica & IoT Guide](https://hacs.xyz/docs/setup/download).

### 2. Manual Installation

If you prefer not to use HACS:
1. Copy the folder `custom_components/zendure_ha` into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Add the integration via **Settings → Devices & Services**.

> 🔥 **Tip:** HACS is highly recommended as it automatically manages updates!

---

## 📊 Available Entities per Device

<details>
<summary><strong>Hyper 2000</strong> 📈</summary>

| Type         | Entity                      | Unit            | Description                     |
|--------------|------------------------------|-----------------|---------------------------------|
| Sensor       | `solar_input_power`          | W (Watt)         | Solar input power |
| Sensor       | `pack_input_power`           | W (Watt)         | Battery input power |
| Sensor       | `output_pack_power`          | W (Watt)         | Battery output power |
| Sensor       | `output_home_power`          | W (Watt)         | Output to home |
| Sensor       | `remain_out_time`            | h (hours)        | Remaining discharge time |
| Sensor       | `remain_input_time`          | h (hours)        | Remaining charge time |
| Sensor       | `electric_level`             | %                | SOC (State of Charge) |
| Sensor       | `hyper_tmp`                  | °C             | Device temperature |
| Sensor       | `aggr_charge_day_kwh`         | kWh              | Daily charge |
| Sensor       | `aggr_discharge_day_kwh`      | kWh              | Daily discharge |
| BinarySensor | `master_switch`              | -                | Master switch |
| BinarySensor | `wifi_state`                 | -                | Wi-Fi status |
| Switch       | `lamp_switch`                | -                | LED lamp switch |
| Number       | `input_limit`                | W (Watt)         | Max input limit |
| Number       | `output_limit`               | W (Watt)         | Max output limit |
| Select       | `ac_mode`                    | Input/Output     | AC operating mode |

</details>

---

<details>
<summary><strong>SolarFlow 800 / SolarFlow 2400 AC</strong> 🌞</summary>

| Type         | Entity                      | Unit            | Description                     |
|--------------|------------------------------|-----------------|---------------------------------|
| Sensor       | `solar_input_power`          | W (Watt)         | Solar power input |
| Sensor       | `pack_input_power`           | W (Watt)         | Battery charge input |
| Sensor       | `output_pack_power`          | W (Watt)         | Battery discharge |
| Sensor       | `electric_level`             | %                | SOC (State of Charge) |
| Sensor       | `pack_num`                   | -                | Number of batteries |
| Sensor       | `hyper_tmp`                  | °C             | Device temperature |
| Sensor       | `aggr_charge_day_kwh`         | kWh              | Daily charge |
| Sensor       | `aggr_discharge_day_kwh`      | kWh              | Daily discharge |
| BinarySensor | `wifi_state`                 | -                | Wi-Fi status |

</details>

---

<details>
<summary><strong>Hub 1000 / Hub 1200 / Hub 2000</strong> ⚡</summary>

| Type         | Entity                      | Unit            | Description                     |
|--------------|------------------------------|-----------------|---------------------------------|
| Sensor       | `solar_input_power`          | W (Watt)         | Solar input |
| Sensor       | `output_pack_power`          | W (Watt)         | Output power |
| Sensor       | `pack_input_power`           | W (Watt)         | Battery input |
| Sensor       | `electric_level`             | %                | Battery SOC |
| Sensor       | `pack_num`                   | -                | Number of batteries |
| Sensor       | `hyper_tmp`                  | °C             | Device temperature |
| Sensor       | `aggr_charge_day_kwh`         | kWh              | Daily charge |
| Sensor       | `aggr_discharge_day_kwh`      | kWh              | Daily discharge |
| Switch       | `lamp_switch` (optional)     | -                | LED control |

</details>

---

<details>
<summary><strong>AIO 2400</strong> 🔋</summary>

| Type         | Entity                      | Unit            | Description                     |
|--------------|------------------------------|-----------------|---------------------------------|
| Sensor       | `solar_input_power`          | W (Watt)         | Solar power input |
| Sensor       | `pack_input_power`           | W (Watt)         | Battery charge input |
| Sensor       | `output_pack_power`          | W (Watt)         | Output power |
| Sensor       | `electric_level`             | %                | SOC (State of Charge) |
| Sensor       | `pack_num`                   | -                | Number of batteries |
| Sensor       | `hyper_tmp`                  | °C             | Temperature measurement |
| Sensor       | `aggr_charge_day_kwh`         | kWh              | Daily charge |
| Sensor       | `aggr_discharge_day_kwh`      | kWh              | Daily discharge |

</details>

---

<details>
<summary><strong>Battery Modules</strong> 💡</summary>

| Type         | Entity                      | Unit            | Description                     |
|--------------|------------------------------|-----------------|---------------------------------|
| Sensor       | `battery_total_vol`          | V (Volt)         | Total voltage |
| Sensor       | `battery_max_vol`            | V (Volt)         | Maximum cell voltage |
| Sensor       | `battery_min_vol`            | V (Volt)         | Minimum cell voltage |
| Sensor       | `battery_current`            | A (Ampere)       | Battery current |
| Sensor       | `battery_power`              | W (Watt)         | Battery power |
| Sensor       | `battery_soc_level`          | %                | State of charge |
| Sensor       | `battery_temperature`        | °C             | Battery temperature |
| Sensor       | `battery_state`              | -                | Battery status (charging/discharging/idle) |

</details>

---

## 🛠️ Local MQTT Operation
- Enable local MQTT support in the configuration.
- Works offline, independent from the cloud.
- Direct communication over Wi-Fi.
- Bluetooth backup scanning (planned).

> Note: A running MQTT Broker (e.g., Mosquitto) is required.

---

## 🔧 Troubleshooting
- **Connection failed:** Check cloud credentials or local broker setup.
- **Device not found:** Ensure it is registered via the Zendure App.
- **Missing entity:** Reload the integration or restart Home Assistant.

Find known issues and open points here: [Issue Tracker](https://github.com/FireSon/Zendure-HA/issues)

---

## 💼 License
This project is licensed under the [MIT License](LICENSE).


## 👨‍💻 Credits
Integration developed by [**fireson**](https://github.com/fireson)

Based on Zendure API analysis, MQTT reverse engineering, and Home Assistant best practices.

---

Thank you for using this integration! ❤️

---

**For questions, feedback, or contributions — feel free to open a GitHub Issue or Pull Request!** 🚀

