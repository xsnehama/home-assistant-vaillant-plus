"""Config flow for Vaillant Plus integration."""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
import logging
from typing import Any

from aiohttp import ClientError
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from vaillant_plus_cn_api import (
    Device,
    InvalidAuthError,
    InvalidCredentialsError,
    RequestError,
    Token,
)
import voluptuous as vol

from .utils import VaillantApiClient, get_aiohttp_session
from .const import (
    CONF_DID,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_USERNAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class VaillantPlusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vaillant Plus."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize."""
        self._cloud_token: Token | None = None
        self._cloud_device_info: Device | None = None
        self._cloud_devices: dict[str, Device] = {}
        self._username: str | None = None
        self._password: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

        client = VaillantApiClient(
            session=get_aiohttp_session(self.hass)
        )

        try:
            user_info = await client.login(
                user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
        except (InvalidCredentialsError, InvalidAuthError):
            errors["base"] = "invalid_auth"
        except (RequestError, ClientError, asyncio.TimeoutError):
            _LOGGER.exception("Cannot reach the Vaillant cloud")
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            self._cloud_token = user_info
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]
            try:
                device_list = await client.get_device_list()
            except (InvalidCredentialsError, InvalidAuthError):
                errors["base"] = "invalid_auth"
            except (RequestError, ClientError, asyncio.TimeoutError):
                _LOGGER.exception("Cannot reach the Vaillant cloud")
                errors["base"] = "cannot_connect"
            except (TypeError, KeyError, IndexError, AttributeError):
                _LOGGER.exception("The cloud returned an unsupported device")
                errors["base"] = "unsupported_device"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                if not device_list:
                    errors["base"] = "no_devices"
                else:
                    self._cloud_devices.clear()
                    for device_info in device_list:
                        product_name = device_info.product_name
                        device_id = device_info.id
                        device_name = f"{product_name}_{device_id}"
                        self._cloud_devices[device_name] = device_info
                    return await self.async_step_select()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> FlowResult:
        """Reauthenticate the configured account without selecting another device."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Validate replacement credentials for the original device."""
        entry = self._get_reauth_entry()
        device_id = entry.data.get(CONF_DID) or entry.unique_id
        username = entry.data.get(CONF_USERNAME)
        if not username and entry.data.get(CONF_TOKEN):
            try:
                username = Token.deserialize(entry.data[CONF_TOKEN]).username
            except (AttributeError, KeyError, TypeError, ValueError):
                pass

        errors: dict[str, str] = {}
        if user_input is not None:
            if username and user_input[CONF_USERNAME] != username:
                errors["base"] = "wrong_account"
            else:
                client = VaillantApiClient(session=get_aiohttp_session(self.hass))
                try:
                    token = await client.login(
                        user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                    )
                    devices = await client.get_device_list()
                except (InvalidCredentialsError, InvalidAuthError):
                    errors["base"] = "invalid_auth"
                except (RequestError, ClientError, asyncio.TimeoutError):
                    _LOGGER.exception("Cannot reach the Vaillant cloud")
                    errors["base"] = "cannot_connect"
                except (TypeError, KeyError, IndexError, AttributeError):
                    _LOGGER.exception("The cloud returned an unsupported device")
                    errors["base"] = "unsupported_device"
                except Exception:
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"
                else:
                    if not device_id or not any(
                        device.id == device_id for device in devices
                    ):
                        errors["base"] = "reauth_device_not_found"
                    else:
                        await self.async_set_unique_id(
                            device_id, raise_on_progress=False
                        )
                        self._abort_if_unique_id_mismatch()
                        return self.async_update_reload_and_abort(
                            entry,
                            data_updates={
                                CONF_USERNAME: user_input[CONF_USERNAME],
                                CONF_PASSWORD: user_input[CONF_PASSWORD],
                                CONF_TOKEN: token.serialize(),
                            },
                        )

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_USERNAME, default=username or vol.UNDEFINED
                ): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=data_schema, errors=errors
        )

    async def async_step_select(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle multiple cloud devices found."""
        errors: dict[str, str] = {}
        if user_input is not None:
            cloud_device = self._cloud_devices[user_input["select_device"]]
            self._cloud_device_info = cloud_device

            unique_id = cloud_device.id
            existing_entry = await self.async_set_unique_id(
                unique_id, raise_on_progress=False
            )

            if existing_entry:
                data = existing_entry.data.copy()
                data[CONF_DID] = unique_id
                data[CONF_TOKEN] = self._cloud_token.serialize()
                data[CONF_USERNAME] = self._username
                data[CONF_PASSWORD] = self._password

                if self.hass.config_entries.async_update_entry(
                    existing_entry, data=data
                ):
                    await self.hass.config_entries.async_reload(existing_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

            return self.async_create_entry(
                title=cloud_device.product_name,
                data={
                    CONF_DID: unique_id,
                    CONF_TOKEN: self._cloud_token.serialize(),
                    CONF_USERNAME: self._username,
                    CONF_PASSWORD: self._password,
                },
            )

        select_schema = vol.Schema(
            {vol.Required("select_device"): vol.In(list(self._cloud_devices))}
        )

        return self.async_show_form(
            step_id="select", data_schema=select_schema, errors=errors
        )
