"""Vaillant sensors - merged: user token-refresh improvements + upstream 1.2.5 diagnostic keys."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    REVOLUTIONS_PER_MINUTE,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import VaillantClient
from .const import CONF_DID, DISPATCHERS, DOMAIN, EVT_DEVICE_CONNECTED, API_CLIENT
from .entity import VaillantEntity

_LOGGER = logging.getLogger(__name__)
# --- Fault code translations ---
FAULT_CODE_MAP = {
    0: "F.0 供水温度传感器故障",
    1: "F.1 回水温度传感器故障",
    2: "F.2 生活热水温度传感器故障",
    3: "F.3 排烟温度传感器故障",
    10: "F.10 供水温度传感器短路",
    11: "F.11 回水温度传感器短路",
    12: "F.12 生活热水温度传感器短路",
    13: "F.13 排烟温度传感器短路",
    18: "F.18 排烟温度传感器开路",
    20: "F.20 过热保护触发",
    22: "F.22 干烧保护(水压过低/缺水)",
    23: "F.23 供水/回水温差过大",
    24: "F.24 水泵卡死或堵塞",
    25: "F.25 排烟温度过高",
    26: "F.26 燃气阀步进电机故障",
    27: "F.27 火焰检测离子电流异常",
    28: "F.28 点火失败",
    29: "F.29 运行中火焰熄灭",
    33: "F.33 风压开关故障",
    35: "F.35 排气温度传感器故障",
    49: "F.49 eBUS电压过低",
    50: "F.50 生活热水板换温度过高",
    56: "F.56 燃气计量模块故障",
    57: "F.57 燃气压力过低",
    61: "F.61 燃气阀驱动故障",
    62: "F.62 燃气阀关闭延迟",
    67: "F.67 火焰信号异常(点火前)",
    68: "F.68 火焰信号异常(运行中)",
    70: "F.70 无效的设备配置",
    71: "F.71 供水温度传感器信号无效",
    72: "F.72 供水或回水温度传感器故障",
    73: "F.73 水压传感器信号无效",
    74: "F.74 水压传感器故障",
    77: "F.77 凝结水排放故障",
    80: "F.80 循环泵故障",
    83: "F.83 三通阀故障",
    89: "F.89 室外温度传感器故障",
    90: "F.90 通信总线故障",
    91: "F.91 eBUS通信超时",
    92: "F.92 网关与壁挂炉通信中断",
    93: "F.93 网关固件异常",
    110: "F.110 烟气排放故障",
    116: "F.116 凝结水pH值异常",
}

BURN_STATUS_BITS = {
    0: "运行",
    1: "采暖模式",
    2: "热水模式",
    3: "点火中",
    4: "调制运行",
}




SENSOR_DESCRIPTIONS = (
    # === Temperature sensors (original user set + DHW_readSetPoint from upstream) ===
    SensorEntityDescription(
        key="Room_Temperature_Setpoint_Comfort",
        name="\u8212\u9002\u6a21\u5f0f\u5ba4\u6e29\u8bbe\u5b9a",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="Room_Temperature_Setpoint_ECO",
        name="ECO \u6a21\u5f0f\u5ba4\u6e29\u8bbe\u5b9a",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="Outdoor_Temperature",
        name="\u5ba4\u5916\u6e29\u5ea6",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="Room_Temperature",
        name="\u5ba4\u5185\u6e29\u5ea6",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="DHW_setpoint",
        name="\u751f\u6d3b\u70ed\u6c34\u8bbe\u5b9a\u6e29\u5ea6",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="DHW_readSetPoint",
        name="\u751f\u6d3b\u70ed\u6c34\u5b9e\u9645\u8bbe\u5b9a\u6e29\u5ea6",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="Lower_Limitation_of_CH_Setpoint",
        name="\u91c7\u6696\u8bbe\u5b9a\u6e29\u5ea6\u4e0b\u9650",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="Upper_Limitation_of_CH_Setpoint",
        name="\u91c7\u6696\u8bbe\u5b9a\u6e29\u5ea6\u4e0a\u9650",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="Lower_Limitation_of_DHW_Setpoint",
        name="\u751f\u6d3b\u70ed\u6c34\u6e29\u5ea6\u4e0b\u9650",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="Upper_Limitation_of_DHW_Setpoint",
        name="\u751f\u6d3b\u70ed\u6c34\u6e29\u5ea6\u4e0a\u9650",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="Current_DHW_Setpoint",
        name="\u5f53\u524d\u751f\u6d3b\u70ed\u6c34\u8bbe\u5b9a\u6e29\u5ea6",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="Flow_Temperature_Setpoint",
        name="\u4f9b\u6c34\u8bbe\u5b9a\u6e29\u5ea6",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="Flow_temperature",
        name="\u4f9b\u6c34\u6e29\u5ea6",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="return_temperature",
        name="\u56de\u6c34\u6e29\u5ea6",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="Tank_temperature",
        name="\u6c34\u7bb1\u6e29\u5ea6",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # === Pressure ===
    SensorEntityDescription(
        key="water_pressure",
        name="\u6c34\u538b",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement="bar",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # === Gas consumption (upstream key set - granular today/yesterday/monthly/yearly) ===
    SensorEntityDescription(
        key="gas_ch_consumption_today",
        name="\u91c7\u6696\u71c3\u6c14\u6d88\u8017(\u4eca\u65e5)",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="gas_ch_consumption_yesterday",
        name="\u91c7\u6696\u71c3\u6c14\u6d88\u8017(\u6628\u65e5)",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="gas_ch_consumption_monthly",
        name="\u91c7\u6696\u71c3\u6c14\u6d88\u8017(\u6708)",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="gas_ch_consumption_yearly",
        name="\u91c7\u6696\u71c3\u6c14\u6d88\u8017(\u5e74)",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="gas_dhw_consumption_today",
        name="\u70ed\u6c34\u71c3\u6c14\u6d88\u8017(\u4eca\u65e5)",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="gas_dhw_consumption_yesterday",
        name="\u70ed\u6c34\u71c3\u6c14\u6d88\u8017(\u6628\u65e5)",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="gas_dhw_consumption_monthly",
        name="\u70ed\u6c34\u71c3\u6c14\u6d88\u8017(\u6708)",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="gas_dhw_consumption_yearly",
        name="\u70ed\u6c34\u71c3\u6c14\u6d88\u8017(\u5e74)",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="gas_consumption",
        name="\u71c3\u6c14\u6d88\u8017\u603b\u91cf",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # === Work time / start count ===
    SensorEntityDescription(
        key="CH_workTime",
        name="\u91c7\u6696\u7d2f\u8ba1\u5de5\u4f5c\u65f6\u957f",
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="CH_startTimes",
        name="\u91c7\u6696\u7d2f\u8ba1\u542f\u52a8",
        native_unit_of_measurement="\u6b21",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="DHW_workTime",
        name="\u70ed\u6c34\u7d2f\u8ba1\u5de5\u4f5c\u65f6\u957f",
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="DHW_startTimes",
        name="\u70ed\u6c34\u7d2f\u8ba1\u542f\u52a8",
        native_unit_of_measurement="\u6b21",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # === Power ===
    SensorEntityDescription(
        key="CH_power",
        name="\u91c7\u6696\u529f\u7387",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="DHW_power",
        name="\u70ed\u6c34\u529f\u7387",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # === Heating system ===
    SensorEntityDescription(
        key="Heating_Curve",
        name="\u91c7\u6696\u66f2\u7ebf",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="Heating_System_Setting",
        name="\u91c7\u6696\u7cfb\u7edf\u8bbe\u7f6e",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # === Hardware status ===
    SensorEntityDescription(
        key="burn_status",
        name="\u71c3\u70e7\u72b6\u6001",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="pump_status",
        name="\u6c34\u6cf5\u72b6\u6001",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="fan_status",
        name="\u98ce\u6247\u72b6\u6001",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="fan_speed",
        name="\u98ce\u6247\u8f6c\u901f",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="ebus_status",
        name="eBUS \u72b6\u6001",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="modbus_status",
        name="Modbus \u72b6\u6001",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # === Wi-Fi signal ===
    SensorEntityDescription(
        key="WiFi_RSSI",
        name="Wi-Fi \u4fe1\u53f7\u5f3a\u5ea6",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement="dBm",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # === Maintenance ===
    SensorEntityDescription(
        key="maintainence_remainTime",
        name="\u7ef4\u62a4\u5269\u4f59\u65f6\u95f4",
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # === Fault lists ===
    SensorEntityDescription(
        key="Fault_List_1",
        name="\u6545\u969c\u5217\u8868 1",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="Fault_List_2",
        name="\u6545\u969c\u5217\u8868 2",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="Fault_List_3",
        name="\u6545\u969c\u5217\u8868 3",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="Fault_List_4",
        name="\u6545\u969c\u5217\u8868 4",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="Fault_List_5",
        name="\u6545\u969c\u5217\u8868 5",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="Gateway_Fault_List_1",
        name="\u7f51\u5173\u6545\u969c\u5217\u8868 1",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="Gateway_Fault_List_2",
        name="\u7f51\u5173\u6545\u969c\u5217\u8868 2",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="Gateway_Fault_List_3",
        name="\u7f51\u5173\u6545\u969c\u5217\u8868 3",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="Gateway_Fault_List_4",
        name="\u7f51\u5173\u6545\u969c\u5217\u8868 4",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="Gateway_Fault_List_5",
        name="\u7f51\u5173\u6545\u969c\u5217\u8868 5",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> bool:
    """Set up Vaillant sensors."""
    device_id = entry.data.get(CONF_DID)
    client: VaillantClient = hass.data[DOMAIN][API_CLIENT][
        entry.entry_id
    ]

    added_entities: set[str] = set()

    def _build_new_entities(device_attrs: dict[str, Any]) -> list:
        new_entities = []
        for description in SENSOR_DESCRIPTIONS:
            if (
                description.key in device_attrs
                and description.key not in added_entities
            ):
                new_entities.append(VaillantSensorEntity(client, description))
                added_entities.add(description.key)
                _LOGGER.debug("ADDING SENSOR: %s", description.key)
        _LOGGER.debug(
            "Built %d new sensor entities; %d total registered",
            len(new_entities),
            len(added_entities),
        )
        return new_entities

    @callback
    def async_new_entities(device_attrs: dict[str, Any]) -> None:
        _LOGGER.debug("add vaillant sensor entities via dispatcher. device attrs keys: %s", list(device_attrs.keys()))
        new_entities = _build_new_entities(device_attrs)
        if new_entities:
            # Schedule entity addition in next event loop iteration to avoid callback context issues
            hass.async_create_task(
                _async_add_entities_wrapper(new_entities)
            )

    async def _async_add_entities_wrapper(entities: list) -> None:
        _LOGGER.debug("Adding %d sensor entities", len(entities))
        async_add_entities(entities)

    # If device already has data (e.g. from a previous connection this session),
    # add entities immediately during setup
    if client.device_attrs:
        _LOGGER.debug("Adding sensors from cached device attributes during setup")
        initial_entities = _build_new_entities(client.device_attrs)
        if initial_entities:
            async_add_entities(initial_entities)

    unsub = async_dispatcher_connect(
        hass, EVT_DEVICE_CONNECTED.format(device_id), async_new_entities
    )

    hass.data[DOMAIN][DISPATCHERS][device_id].append(unsub)

    return True



class VaillantSensorEntity(VaillantEntity, SensorEntity):
    """Define a Vaillant sensor entity."""

    def __init__(
        self,
        client: VaillantClient,
        description: SensorEntityDescription,
    ):
        super().__init__(client)
        self.entity_description = description
        # Use description's unit if set; otherwise default to Celsius for backward compat
        if description.native_unit_of_measurement:
            self._attr_native_unit_of_measurement = description.native_unit_of_measurement

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self.device.id}_{self.entity_description.key}"

    @property
    def extra_state_attributes(self) -> dict | None:
        return getattr(self, "_attr_extra_state_attributes", None)

    @staticmethod
    def _as_number(value: Any) -> int | float | None:
        """Convert numeric API values while preserving integer counters."""
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return value
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return int(number) if number.is_integer() else number

    @callback
    def update_from_latest_data(self, data: dict[str, Any]) -> None:
        """Update the entity from the latest data."""
        if self.entity_description.key not in data:
            return

        value = data.get(self.entity_description.key)
        key = self.entity_description.key

        # --- Translate temperature sentinels ---
        if key == "Outdoor_Temperature":
            if value is not None and float(value) <= -40:
                self._attr_native_value = None
                self._attr_extra_state_attributes = {"状态": "未接室外传感器"}
            else:
                self._attr_native_value = value
                self._attr_extra_state_attributes = None
        elif key == "Room_Temperature_Setpoint_Comfort":
            if value is not None and float(value) == 0:
                self._attr_native_value = None
                self._attr_extra_state_attributes = {"状态": "未设置(无室内温控器)"}
            else:
                self._attr_native_value = value
                self._attr_extra_state_attributes = None
        elif key == "Room_Temperature_Setpoint_ECO":
            if value is not None and float(value) == 0:
                self._attr_native_value = None
                self._attr_extra_state_attributes = {"状态": "未设置(无室内温控器)"}
            else:
                self._attr_native_value = value
                self._attr_extra_state_attributes = None

        # --- Fault list codes ---
        elif key.startswith("Fault_List_") or key.startswith("Gateway_Fault_List_"):
            if value == 65535 or value == "65535":
                self._attr_native_value = "无故障"
            else:
                code = int(value) if value is not None else 65535
                self._attr_native_value = FAULT_CODE_MAP.get(code, f"未知故障码 F.{code}")
        elif key == "maintainence_remainTime":
            if value == 65535 or value == "65535":
                self._attr_native_value = None
                self._attr_extra_state_attributes = {"状态": "无需维护"}
            else:
                self._attr_native_value = self._as_number(value)
                self._attr_extra_state_attributes = None
        elif key == "burn_status":
            if value is not None:
                bits = int(value)
                if bits == 0:
                    self._attr_native_value = "停止"
                else:
                    active = []
                    for bit, label in BURN_STATUS_BITS.items():
                        if bits & (1 << bit):
                            active.append(label)
                    self._attr_native_value = " + ".join(active) if active else f"停止 ({bits})"
            else:
                self._attr_native_value = value
        elif key == "pump_status":
            self._attr_native_value = "运行" if int(value or 0) > 0 else "停止"
        elif key == "fan_status":
            self._attr_native_value = "运行" if int(value or 0) > 0 else "停止"
        elif key == "fan_speed":
            self._attr_native_value = self._as_number(value)
        elif key == "ebus_status":
            self._attr_native_value = "正常" if int(value or 0) == 1 else "断开"
        elif key == "modbus_status":
            self._attr_native_value = "正常" if int(value or 0) == 0 else f"错误 ({value})"
        elif key == "Heating_System_Setting":
            mode_map = {"radiator": "暖气片", "floor": "地暖", "mix": "混合"}
            self._attr_native_value = mode_map.get(str(value), str(value))
        elif key == "Time_slot_type":
            ts_map = {"CH": "采暖时段", "DHW": "热水时段", "CH+DHW": "采暖+热水时段"}
            self._attr_native_value = ts_map.get(str(value), str(value))
        elif key == "Mode_Setting_CH":
            mode_map = {"Cruising": "巡航模式", "Comfort": "舒适模式", "Eco": "节能模式"}
            self._attr_native_value = mode_map.get(str(value), str(value))
        elif key == "Mode_Setting_DHW":
            mode_map = {"Cruising": "巡航模式", "Comfort": "舒适模式", "Eco": "节能模式"}
            self._attr_native_value = mode_map.get(str(value), str(value))
        elif key == "DHW_Function":
            func_map = {"not_setted": "未设置", "eco": "节能", "comfort": "舒适"}
            self._attr_native_value = func_map.get(str(value), str(value))
        elif key in {
            "CH_workTime",
            "DHW_workTime",
            "CH_startTimes",
            "DHW_startTimes",
            "CH_power",
            "DHW_power",
        }:
            self._attr_native_value = self._as_number(value)

        # --- Translate gas consumption (always zero = sensor not installed) ---
        elif key.startswith("gas_") or key == "gas_consumption":
            if value is None or value == 0 or value == "0" or str(value) == "00000000":
                self._attr_native_value = "未接入燃气计"
            else:
                self._attr_native_value = value

        else:
            self._attr_native_value = value

        self._attr_available = value is not None
