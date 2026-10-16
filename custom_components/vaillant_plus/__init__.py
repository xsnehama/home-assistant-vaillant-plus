"""The Vaillant Plus integration."""
from __future__ import annotations

import logging
import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.typing import ConfigType
from vaillant_plus_cn_api import Token

from .client import VaillantClient
from .const import (
    API_CLIENT,
    CONF_DID,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_USERNAME,
    DISPATCHERS,
    DOMAIN,
    EVT_TOKEN_UPDATED,
)

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.WATER_HEATER,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(
        DOMAIN,
        {API_CLIENT: {}, DISPATCHERS: {}},
    )
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate legacy token payloads to the current serialized format."""
    if entry.version >= 2:
        return True
    try:
        token = Token.deserialize(entry.data[CONF_TOKEN])
        data = {**entry.data, CONF_TOKEN: token.serialize()}
    except (KeyError, TypeError, ValueError) as error:
        _LOGGER.error("Unable to migrate Vaillant config entry token: %s", error)
        return False
    hass.config_entries.async_update_entry(entry, data=data, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Vaillant Plus from a config entry."""
    token = Token.deserialize(entry.data.get(CONF_TOKEN))
    device_id = entry.data.get(CONF_DID)
    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)

    @callback
    def on_auth_failed() -> None:
        entry.async_start_reauth(hass)

    client = VaillantClient(
        hass,
        token,
        device_id,
        username,
        password,
        on_auth_failed=on_auth_failed,
        entry_id=entry.entry_id,
    )

    async def close_client(_):
        await client.close()

    hass.data[DOMAIN][API_CLIENT][entry.entry_id] = client

    @callback
    def on_token_update(token_new: Token) -> None:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_TOKEN: token_new.serialize()}
        )

    unsub = async_dispatcher_connect(
        hass,
        EVT_TOKEN_UPDATED.format(entry.entry_id),
        on_token_update,
    )

    # Keyed by entry so a second config entry can never touch this one's handles.
    dispatchers = hass.data[DOMAIN][DISPATCHERS].setdefault(entry.entry_id, [])
    dispatchers.append(unsub)

    unsub_stop = hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, close_client)
    dispatchers.append(unsub_stop)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    task = hass.loop.create_task(client.start())
    dispatchers.append(task)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        if (
            entry.entry_id in hass.data[DOMAIN][API_CLIENT]
            and hass.data[DOMAIN][API_CLIENT][entry.entry_id] is not None
        ):
            try:
                await hass.data[DOMAIN][API_CLIENT][entry.entry_id].close()
            except Exception as error:
                _LOGGER.debug("Failed to close Vaillant client during unload: %s", error)
        hass.data[DOMAIN][API_CLIENT].pop(entry.entry_id)

    dispatchers = hass.data[DOMAIN][DISPATCHERS].pop(entry.entry_id, [])
    for unsub_or_task in dispatchers:
        if isinstance(unsub_or_task, asyncio.Task):
            unsub_or_task.cancel()
        else:
            unsub_or_task()

    return unload_ok
