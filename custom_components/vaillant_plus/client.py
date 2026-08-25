"""Vaillant Plus client."""
from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from vaillant_plus_cn_api import (
    EVT_DEVICE_ATTR_UPDATE,
    Device,
    InvalidAuthError,
    Token,
    VaillantApiClient,
    VaillantWebsocketClient,
)

from .utils import get_aiohttp_session
from .const import EVT_DEVICE_CONNECTED, EVT_DEVICE_UPDATED, EVT_TOKEN_UPDATED

_LOGGER = logging.getLogger(__name__)

TOKEN_REFRESH_INTERVAL = 50 * 60
TOKEN_REFRESH_MIN_INTERVAL = 15 * 60
TOKEN_REFRESH_MAX_INTERVAL = 55 * 60
TOKEN_REFRESH_EARLY_MARGIN = 5 * 60
TOKEN_RECONNECT_BASE_DELAY = 5
TOKEN_RECONNECT_MAX_DELAY = 5 * 60


class AuthState(Enum):
    INITED = "INITED"
    CONNECTING = "CONNECTING"
    HEALTHY = "HEALTHY"
    EXPIRING = "EXPIRING"
    REFRESHING = "REFRESHING"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"
    CLOSED = "CLOSED"

class VaillantClient:
    """API client for communicating with the cloud."""

    def __init__(
        self,
        hass: HomeAssistant,
        token: Token,
        device_id: str,
        username: str = None,
        password: str = None,
    ) -> None:
        self._hass = hass
        self._device_id = device_id
        self._username = username
        self._password = password
        self._device_attrs: dict[str, Any] = {}
        self._device: Device | None = None
        self._token = token

        self._api_client = VaillantApiClient(session=get_aiohttp_session(self._hass))

        self._websocket_client: VaillantWebsocketClient | None = None

        self._sleep_task: asyncio.Task | None = None
        self._token_refresh_handle: asyncio.TimerHandle | None = None
        self._refresh_lock = asyncio.Lock()
        self._auth_state = AuthState.INITED
        self._state = self._auth_state.value
        self._reconnect_delay = TOKEN_RECONNECT_BASE_DELAY
        self._token_refresh_interval = TOKEN_REFRESH_INTERVAL
        self._token_last_refresh_monotonic: float | None = None

    @property
    def device(self) -> Device:
        return self._device

    @property
    def device_attrs(self) -> dict[str, Any]:
        return self._device_attrs

    @property
    def auth_state(self) -> AuthState:
        return self._auth_state

    @property
    def is_connected(self) -> bool:
        """Return whether the websocket is actively subscribed."""
        return (
            self._auth_state is AuthState.HEALTHY
            and self._websocket_client is not None
            and self._websocket_client.state == "subscribed"
        )

    def _set_auth_state(self, state: AuthState) -> None:
        self._auth_state = state
        self._state = state.value

    def _notify_state_changed(self) -> None:
        """Refresh entity availability without discarding cached values."""
        if self._device is not None and self._device_attrs:
            async_dispatcher_send(
                self._hass,
                EVT_DEVICE_UPDATED.format(self._device.id),
                self._device_attrs.copy(),
            )

    def _reset_reconnect_delay(self) -> None:
        self._reconnect_delay = TOKEN_RECONNECT_BASE_DELAY

    def _increase_reconnect_delay(self) -> None:
        self._reconnect_delay = min(self._reconnect_delay * 2, TOKEN_RECONNECT_MAX_DELAY)

    def _schedule_reconnect_sleep(self) -> None:
        if self._state == "CLOSED":
            return

        delay = self._reconnect_delay
        self._sleep_task = asyncio.create_task(asyncio.sleep(delay))

    async def _connect(self) -> None:
        self._set_auth_state(AuthState.CONNECTING)
        self._notify_state_changed()

        device_list = await self._api_client.get_device_list()
        filtered_device_list = [device for device in device_list if device.id == self._device_id]
        if len(filtered_device_list) == 0:
            raise ShouldUpdateConfigEntry

        self._device = filtered_device_list[0]

        if self._websocket_client is not None:
            try:
                await self._websocket_client.close()
            except Exception as error:
                _LOGGER.debug("Failed to close previous websocket: %s", error)
            finally:
                self._websocket_client = None

        @callback
        def device_connected(device_attrs: dict[str, Any]):
            self._device_attrs = device_attrs.copy()
            self._set_auth_state(AuthState.HEALTHY)
            self._reset_reconnect_delay()
            async_dispatcher_send(
                self._hass, EVT_DEVICE_CONNECTED.format(self._device_id), device_attrs.copy()
            )

        @callback
        def device_update(event: str, data: dict[str, Any]):
            if event == EVT_DEVICE_ATTR_UPDATE:
                device_attrs: dict[str, Any] = data.get("data", {})
                if len(device_attrs) > 0:
                    self._device_attrs.update(device_attrs)
                    async_dispatcher_send(
                        self._hass, EVT_DEVICE_UPDATED.format(self._device.id), self._device_attrs.copy()
                    )

        self._websocket_client = VaillantWebsocketClient(
            token=self._token,
            device=self._device,
            session=get_aiohttp_session(self._hass),
        )
        self._websocket_client.on_subscribe(device_connected)
        self._websocket_client.on_update(device_update)

        await self._websocket_client.connect()
        if self._auth_state is not AuthState.CLOSED:
            self._set_auth_state(AuthState.CONNECTING)
            self._notify_state_changed()

    async def _get_token(self) -> None:
        if not self._username or not self._password:
            _LOGGER.error("Cannot refresh token: username/password not configured")
            return
        self._set_auth_state(AuthState.REFRESHING)
        token_new = await self._api_client.login(self._username, self._password)
        self._token = token_new
        self._api_client.update_token(token_new)
        self._token_last_refresh_monotonic = time.monotonic()
        async_dispatcher_send(
            self._hass, EVT_TOKEN_UPDATED.format(token_new.username), token_new
        )
        self._set_auth_state(AuthState.HEALTHY)
        self._reset_reconnect_delay()

    def _adjust_refresh_interval_after_failure(self) -> None:
        """Shorten the proactive refresh interval if auth still expires too early."""
        if self._token_last_refresh_monotonic is None:
            self._token_refresh_interval = max(
                TOKEN_REFRESH_MIN_INTERVAL,
                min(self._token_refresh_interval, TOKEN_REFRESH_INTERVAL),
            )
            return

        age = time.monotonic() - self._token_last_refresh_monotonic
        candidate = max(TOKEN_REFRESH_MIN_INTERVAL, int(age * 0.8))
        self._token_refresh_interval = min(self._token_refresh_interval, candidate)
        _LOGGER.info(
            "Adjusted token refresh interval to %s seconds after early auth failure",
            self._token_refresh_interval,
        )

    def _mark_reauth_required(self) -> None:
        self._set_auth_state(AuthState.REAUTH_REQUIRED)
        self._adjust_refresh_interval_after_failure()
        self._increase_reconnect_delay()

    async def _refresh_token_and_reconnect(self) -> None:
        """Refresh token proactively and reconnect websocket with the new token."""
        async with self._refresh_lock:
            try:
                await self._get_token()
            except Exception as error:
                self._mark_reauth_required()
                _LOGGER.warning("Proactive token refresh failed: %s", error)
                return

            if self._websocket_client is not None:
                try:
                    await self._websocket_client.close()
                except Exception as error:
                    _LOGGER.debug("Failed to close websocket during token refresh: %s", error)

    def _schedule_token_refresh(self, delay_sec: int = TOKEN_REFRESH_INTERVAL) -> None:
        """Schedule the next proactive token refresh."""
        if self._token_refresh_handle is not None:
            self._token_refresh_handle.cancel()

        delay_sec = max(
            TOKEN_REFRESH_MIN_INTERVAL,
            min(delay_sec, TOKEN_REFRESH_MAX_INTERVAL),
        )
        self._token_refresh_interval = delay_sec
        self._token_refresh_handle = self._hass.loop.call_later(
            delay_sec,
            lambda: self._hass.loop.create_task(self._token_refresh_async()),
        )

    async def _token_refresh_async(self) -> None:
        """Refresh token before it expires and reschedule the next run."""
        try:
            if self._state == "CLOSED":
                return
            await self._refresh_token_and_reconnect()
        except asyncio.CancelledError:
            return
        except Exception as error:
            _LOGGER.warning("Unhandled token refresh exception: %s", error)
        finally:
            if self._state != "CLOSED":
                self._schedule_token_refresh(self._token_refresh_interval)

    async def start(self) -> None:
        """Start connection to cloud."""
        if self._token_refresh_handle is None:
            await self._refresh_token_and_reconnect()
            self._schedule_token_refresh(self._token_refresh_interval - TOKEN_REFRESH_EARLY_MARGIN)

        while self._state != "CLOSED":
            try:
                await self._connect()
            except InvalidAuthError:
                self._mark_reauth_required()
                await self._refresh_token_and_reconnect()
                self._schedule_token_refresh(self._token_refresh_interval - TOKEN_REFRESH_EARLY_MARGIN)
            except Exception as error:
                _LOGGER.warning("Unhandled client exception: %s", error)
                self._increase_reconnect_delay()

            self._schedule_reconnect_sleep()
            await self._sleep_task

    async def close(self) -> None:
        """Close connection to cloud."""
        self._set_auth_state(AuthState.CLOSED)
        self._notify_state_changed()

        if self._websocket_client is not None:
            try:
                await self._websocket_client.close()
            except Exception as error:
                _LOGGER.exception("Failed to close websocket: %s", error)

        if self._sleep_task is not None:
            self._sleep_task.cancel()
            try:
                await self._sleep_task
            except asyncio.CancelledError:
                pass

        if self._token_refresh_handle is not None:
            self._token_refresh_handle.cancel()
            self._token_refresh_handle = None

    async def control_device(self, attrs: dict[str, Any]) -> bool:
        """Send command to control device."""
        retry_times = 0
        while retry_times < 3:
            try:
                await self._api_client.control_device(self._device_id, attrs)
                return True
            except InvalidAuthError:
                await self._get_token()
                await asyncio.sleep(retry_times * 5)
                retry_times = retry_times + 1
                _LOGGER.warning("Control device failed due to invalid token, retry %d time", retry_times)

        return False



class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class UnknownException(HomeAssistantError):
    """Error that is not known."""


class ShouldUpdateConfigEntry(HomeAssistantError):
    """Error to reconfigure entry"""
