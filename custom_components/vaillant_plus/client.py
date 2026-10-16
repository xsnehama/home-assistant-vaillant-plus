"""Vaillant Plus client."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from enum import Enum
import logging
import time
from typing import Any

from aiohttp import ClientError
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from vaillant_plus_cn_api import (
    EVT_DEVICE_ATTR_UPDATE, EVT_DEVICE_EVENT, Device, InvalidAuthError, InvalidCredentialsError,
    RequestError, Token, VaillantWebsocketClient,
)
from .utils import VaillantApiClient, get_aiohttp_session
from .const import EVT_DEVICE_CONNECTED, EVT_DEVICE_EVENT as HA_EVT_DEVICE_EVENT, EVT_DEVICE_UPDATED, EVT_TOKEN_UPDATED

_LOGGER = logging.getLogger(__name__)
TOKEN_REFRESH_INTERVAL = 45 * 60
TOKEN_REFRESH_MIN_INTERVAL = 15 * 60
TOKEN_REFRESH_RETRY_DELAY = 60
TOKEN_RECONNECT_BASE_DELAY = 5
TOKEN_RECONNECT_MAX_DELAY = 5 * 60
WEBSOCKET_SUBSCRIBE_TIMEOUT = 30
RECONNECT_AVAILABILITY_GRACE = 10


class AuthState(Enum):
    INITED = "INITED"
    CONNECTING = "CONNECTING"
    HEALTHY = "HEALTHY"
    EXPIRING = "EXPIRING"
    REFRESHING = "REFRESHING"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"
    CLOSED = "CLOSED"


class VaillantClient:
    """Maintain a live subscription while serializing authentication."""

    def __init__(self, hass: HomeAssistant, token: Token, device_id: str,
                 username: str | None = None, password: str | None = None,
                 *, on_auth_failed: Callable[[], None] | None = None,
                 entry_id: str) -> None:
        self._hass = hass
        self._device_id = device_id
        self._username = username or token.username
        self._password = password or token.password
        self._on_auth_failed = on_auth_failed
        self._entry_id = entry_id
        self._device_attrs: dict[str, Any] = {}
        self._device: Device | None = None
        self._token = token
        self._api_client = VaillantApiClient(session=get_aiohttp_session(hass))
        self._api_client.update_token(token)
        self._websocket_client = None
        self._websocket_task = None
        self._websocket_token = None
        self._pending_websocket = None
        self._pending_task = None
        self._token_refresh_handle = None
        self._token_refresh_task = None
        self._refresh_lock = asyncio.Lock()
        self._connect_lock = asyncio.Lock()
        self._stopped = asyncio.Event()
        self._auth_state = AuthState.INITED
        self._state = self._auth_state.value
        self._reconnect_delay = TOKEN_RECONNECT_BASE_DELAY
        self._token_refresh_interval = TOKEN_REFRESH_INTERVAL
        self._token_last_refresh_monotonic: float | None = None
        self._stable_refreshes = 0
        self._reauth_started = False
        self._reconnect_grace_until: float | None = None
        self._reconnect_grace_handle: asyncio.TimerHandle | None = None

    @property
    def device(self) -> Device | None:
        return self._device

    @property
    def device_id(self) -> str:
        """Configured id; never depends on a live cloud object."""
        return self._device_id

    @property
    def entry_id(self) -> str:
        """Owning config entry; scopes cleanup bookkeeping per entry."""
        return self._entry_id

    @property
    def device_attrs(self) -> dict[str, Any]:
        return self._device_attrs

    @property
    def auth_state(self) -> AuthState:
        return self._auth_state

    @property
    def is_connected(self) -> bool:
        """A refreshing token does not invalidate a live subscription."""
        if self._stopped.is_set():
            return False
        active = (self._websocket_client is not None
                  and self._websocket_client.state == "subscribed"
                  and self._websocket_task is not None
                  and not self._websocket_task.done())
        if active:
            return True
        return (self._reconnect_grace_until is not None
                and time.monotonic() < self._reconnect_grace_until
                and bool(self._device_attrs))

    def _begin_reconnect_grace(self, source: str) -> None:
        """Keep entities available briefly while replacing a live socket."""
        if not self._device_attrs or self._stopped.is_set():
            return
        self._reconnect_grace_until = time.monotonic() + RECONNECT_AVAILABILITY_GRACE
        if self._reconnect_grace_handle is not None:
            self._reconnect_grace_handle.cancel()

        @callback
        def expire() -> None:
            self._reconnect_grace_handle = None
            self._reconnect_grace_until = None
            _LOGGER.info("Vaillant reconnect availability grace expired (source=%s)", source)
            self._notify_state_changed()

        self._reconnect_grace_handle = self._hass.loop.call_later(
            RECONNECT_AVAILABILITY_GRACE, expire
        )

    def _end_reconnect_grace(self) -> None:
        if self._reconnect_grace_handle is not None:
            self._reconnect_grace_handle.cancel()
            self._reconnect_grace_handle = None
        self._reconnect_grace_until = None

    def _set_auth_state(self, state: AuthState) -> None:
        if self._auth_state is AuthState.CLOSED and state is not AuthState.CLOSED:
            return
        self._auth_state = state
        self._state = state.value

    def _notify_state_changed(self) -> None:
        if self._device is not None and self._device_attrs:
            async_dispatcher_send(self._hass, EVT_DEVICE_UPDATED.format(self._device_id),
                                  self._device_attrs.copy())

    async def _close_connection(self, websocket, task) -> None:
        # Cancelling the task also stops a handshake that close() alone misses.
        try:
            if task is not None:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        finally:
            if websocket is not None:
                try:
                    await asyncio.wait_for(websocket.close(), timeout=10)
                except Exception as error:
                    _LOGGER.debug("Websocket cleanup failed (%s)", type(error).__name__)

    async def _stop_connections(self) -> None:
        active = self._websocket_client, self._websocket_task
        pending = self._pending_websocket, self._pending_task
        self._websocket_client = self._websocket_task = self._websocket_token = None
        self._pending_websocket = self._pending_task = None
        await self._close_connection(*pending)
        await self._close_connection(*active)

    async def _connect(self) -> None:
        """Subscribe a replacement before retiring the previous socket."""
        async with self._connect_lock:
            if self._stopped.is_set():
                return
            if self.is_connected and self._websocket_token is self._token:
                return
            if not self.is_connected:
                _LOGGER.info(
                    "Vaillant connection inactive before replacement; old_websocket_state=%s",
                    getattr(self._websocket_client, "state", None),
                )
                self._begin_reconnect_grace("connect")
                self._set_auth_state(AuthState.CONNECTING)
                self._notify_state_changed()
            if self._device is None:
                devices = await self._api_client.get_device_list()
                self._device = next((d for d in devices if d.id == self._device_id), None)
                if self._device is None:
                    raise ShouldUpdateConfigEntry("Configured Vaillant device was not found")
            if self._stopped.is_set():
                return
            token = self._token
            websocket = VaillantWebsocketClient(token=token, device=self._device,
                                               session=get_aiohttp_session(self._hass))
            ready = asyncio.Event()
            candidate_attrs: dict[str, Any] = {}

            @callback
            def device_connected(attrs: dict[str, Any]) -> None:
                if not self._stopped.is_set():
                    candidate_attrs.update(attrs)
                    ready.set()

            @callback
            def device_update(event: str, data: dict[str, Any]) -> None:
                if self._stopped.is_set():
                    return
                if event == EVT_DEVICE_EVENT:
                    _LOGGER.info("Received Vaillant device event: %s", data.get("data", {}))
                    async_dispatcher_send(
                        self._hass,
                        HA_EVT_DEVICE_EVENT.format(self._device_id),
                        data.copy(),
                    )
                    return
                if event != EVT_DEVICE_ATTR_UPDATE:
                    return
                attrs = data.get("data", {})
                candidate_attrs.update(attrs)
                if websocket is self._websocket_client and attrs:
                    self._device_attrs.update(attrs)
                    self._notify_state_changed()

            websocket.on_subscribe(device_connected)
            websocket.on_update(device_update)
            task = self._hass.loop.create_task(websocket.connect())
            self._pending_websocket, self._pending_task = websocket, task
            ready_task = self._hass.loop.create_task(ready.wait())
            promoted = False
            try:
                await asyncio.wait({ready_task, task}, timeout=WEBSOCKET_SUBSCRIBE_TIMEOUT,
                                   return_when=asyncio.FIRST_COMPLETED)
                if self._stopped.is_set():
                    return
                if task.done():
                    try:
                        task.result()
                    except InvalidAuthError as error:
                        raise SubscriptionAuthError from error
                    raise ConnectionError("Vaillant websocket ended before subscription")
                # The API sets subscribed after returning from on_subscribe.
                if not ready.is_set() or websocket.state != "subscribed":
                    raise TimeoutError("Vaillant websocket subscription timed out")
                old = self._websocket_client, self._websocket_task
                self._websocket_client, self._websocket_task = websocket, task
                self._websocket_token = token
                self._end_reconnect_grace()
                self._device_attrs.update(candidate_attrs)
                self._pending_websocket = self._pending_task = None
                self._set_auth_state(AuthState.HEALTHY)
                self._reconnect_delay = TOKEN_RECONNECT_BASE_DELAY
                promoted = True
                async_dispatcher_send(self._hass, EVT_DEVICE_CONNECTED.format(self._device_id),
                                      self._device_attrs.copy())
                self._notify_state_changed()
                await self._close_connection(*old)
            finally:
                ready_task.cancel()
                await asyncio.gather(ready_task, return_exceptions=True)
                if not promoted:
                    await self._close_connection(websocket, task)
                if self._pending_websocket is websocket:
                    self._pending_websocket = self._pending_task = None

    def _adjust_refresh_interval_after_failure(self) -> None:
        """Only a known early token rejection can shorten its refresh interval."""
        self._stable_refreshes = 0
        if self._token_last_refresh_monotonic is not None:
            age = time.monotonic() - self._token_last_refresh_monotonic
            self._token_refresh_interval = min(self._token_refresh_interval,
                max(TOKEN_REFRESH_MIN_INTERVAL, int(age * 0.8)))

    def _record_successful_refresh(self) -> None:
        self._stable_refreshes += 1
        if self._stable_refreshes >= 2:
            self._token_refresh_interval = min(TOKEN_REFRESH_INTERVAL,
                                              self._token_refresh_interval + 5 * 60)
            self._stable_refreshes = 0

    async def _mark_reauth_required(self) -> None:
        if self._stopped.is_set():
            return
        self._set_auth_state(AuthState.REAUTH_REQUIRED)
        self._stopped.set()
        if self._token_refresh_handle is not None:
            self._token_refresh_handle.cancel()
            self._token_refresh_handle = None
        self._notify_state_changed()
        await self._stop_connections()
        if not self._reauth_started and self._on_auth_failed is not None:
            self._reauth_started = True
            self._on_auth_failed()

    async def _refresh_token(self, expected_token: Token) -> bool:
        """Share one login between requests rejected with the same token."""
        async with self._refresh_lock:
            if self._stopped.is_set():
                raise InvalidAuth("Vaillant authentication requires attention")
            if self._token is not expected_token:
                return False
            if not self._username or not self._password:
                await self._mark_reauth_required()
                raise InvalidAuth("Vaillant credentials must be entered again")
            self._set_auth_state(AuthState.REFRESHING)
            try:
                token = await self._api_client.login(self._username, self._password)
            except InvalidCredentialsError as error:
                await self._mark_reauth_required()
                raise InvalidAuth("Vaillant credentials were rejected; sign in again") from error
            except Exception as error:
                # API 2.0.1 also maps rate limits and other HTTP 4xx to
                # InvalidAuthError. This alone is not proof of a bad password.
                self._set_auth_state(AuthState.HEALTHY if self.is_connected else AuthState.CONNECTING)
                raise HomeAssistantError("Cannot refresh Vaillant authentication; try again later") from error
            if self._stopped.is_set():
                raise HomeAssistantError("Vaillant integration has stopped")
            self._token = token
            self._api_client.update_token(token)
            self._token_last_refresh_monotonic = time.monotonic()
            async_dispatcher_send(self._hass, EVT_TOKEN_UPDATED.format(self._entry_id), token)
            self._set_auth_state(AuthState.HEALTHY if self.is_connected else AuthState.CONNECTING)
            return True

    async def _refresh_token_and_reconnect(self) -> bool:
        # A failed replacement must retry its subscription, not log in again.
        refreshed = False
        if self._websocket_token is self._token or self._token_last_refresh_monotonic is None:
            refreshed = await self._refresh_token(self._token)
        rejected_token = self._token
        try:
            await self._connect()
        except InvalidAuthError as error:
            if isinstance(error, SubscriptionAuthError) and rejected_token is self._token:
                self._adjust_refresh_interval_after_failure()
            refreshed = await self._refresh_token(rejected_token) or refreshed
            # Only one extra login per timer run; failures retain the retry delay.
            await self._connect()
        return refreshed

    def _schedule_token_refresh(self, delay_sec: float | None = None) -> None:
        """Retry timing never writes back into the adaptive interval."""
        if self._stopped.is_set():
            return
        if self._token_refresh_handle is not None:
            self._token_refresh_handle.cancel()

        @callback
        def run_refresh() -> None:
            self._token_refresh_handle = None
            if not self._stopped.is_set():
                if self._token_refresh_task is not None and not self._token_refresh_task.done():
                    self._schedule_token_refresh(TOKEN_REFRESH_RETRY_DELAY)
                    return
                self._token_refresh_task = self._hass.loop.create_task(self._token_refresh_async())

        self._token_refresh_handle = self._hass.loop.call_later(
            self._token_refresh_interval if delay_sec is None else delay_sec, run_refresh)

    async def _token_refresh_async(self) -> None:
        delay = None
        try:
            if self._stopped.is_set():
                return
            refreshed = await self._refresh_token_and_reconnect()
            if refreshed:
                self._record_successful_refresh()
            _LOGGER.info("Proactive authentication refresh completed; subscription=%s, next=%ss",
                         self.is_connected, self._token_refresh_interval)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            delay = TOKEN_REFRESH_RETRY_DELAY
            _LOGGER.warning(
                "Proactive authentication refresh failed (%s): %s",
                type(error).__name__,
                error,
                exc_info=True,
            )
        finally:
            self._schedule_token_refresh(delay)

    async def start(self) -> None:
        """Follow socket replacements without treating retirement as an outage."""
        if self._stopped.is_set():
            return
        self._schedule_token_refresh()
        try:
            while not self._stopped.is_set():
                token = self._token
                subscription_auth_failure = False
                try:
                    await self._connect()
                    task = self._websocket_task
                    token = self._websocket_token or token
                    if task is None or self._stopped.is_set():
                        break
                    # Retiring a listener must not cancel its supervisor.
                    await asyncio.wait({task})
                    if task is not self._websocket_task:
                        continue
                    websocket = self._websocket_client
                    _LOGGER.info(
                        "Vaillant websocket supervisor clearing active slot; old_websocket_state=%s",
                        getattr(websocket, "state", None),
                    )
                    self._begin_reconnect_grace("supervisor")
                    self._websocket_client = self._websocket_task = self._websocket_token = None
                    self._set_auth_state(AuthState.CONNECTING)
                    self._notify_state_changed()
                    try:
                        subscription_auth_failure = True
                        task.result()
                    finally:
                        await self._close_connection(websocket, task)
                except InvalidAuthError as error:
                    if (subscription_auth_failure or isinstance(error, SubscriptionAuthError)) and token is self._token:
                        self._adjust_refresh_interval_after_failure()
                    try:
                        await self._refresh_token(token)
                        self._schedule_token_refresh()
                    except HomeAssistantError:
                        self._schedule_token_refresh(TOKEN_REFRESH_RETRY_DELAY)
                except ShouldUpdateConfigEntry:
                    _LOGGER.error("Configured Vaillant device is missing; check its cloud binding")
                    await self.close()
                    break
                except Exception as error:
                    _LOGGER.warning(
                        "Vaillant connection failed (%s): %s",
                        type(error).__name__,
                        error,
                        exc_info=True,
                    )
                if self._stopped.is_set():
                    break
                try:
                    await asyncio.wait_for(self._stopped.wait(), timeout=self._reconnect_delay)
                except TimeoutError:
                    pass
                self._reconnect_delay = min(self._reconnect_delay * 2, TOKEN_RECONNECT_MAX_DELAY)
        except asyncio.CancelledError:
            await self.close()
            raise

    async def close(self) -> None:
        """Stop timers, pending handshakes and active listeners before unloading."""
        self._set_auth_state(AuthState.CLOSED)
        self._stopped.set()
        self._notify_state_changed()
        if self._token_refresh_handle is not None:
            self._token_refresh_handle.cancel()
            self._token_refresh_handle = None
        self._end_reconnect_grace()
        task = self._token_refresh_task
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await self._stop_connections()

    async def control_device(self, attrs: dict[str, Any]) -> bool:
        """Send a command with bounded retries and consistent service errors."""
        for attempt in range(3):
            if self._stopped.is_set():
                raise HomeAssistantError("Vaillant integration is stopped or needs sign-in")
            token = self._token
            try:
                await self._api_client.control_device(self._device_id, attrs)
                return True
            except InvalidAuthError as error:
                if attempt == 2:
                    raise HomeAssistantError("Vaillant rejected the command after authentication retries") from error
                try:
                    await self._refresh_token(token)
                    self._schedule_token_refresh(TOKEN_REFRESH_RETRY_DELAY)
                except HomeAssistantError:
                    self._schedule_token_refresh(TOKEN_REFRESH_RETRY_DELAY)
                    raise
            except (RequestError, ClientError, TimeoutError) as error:
                raise HomeAssistantError("Cannot reach Vaillant to send the command") from error
            except Exception as error:
                raise HomeAssistantError("Vaillant control command failed") from error
        return False


class InvalidAuth(HomeAssistantError):
    """Authentication requires attention."""


class SubscriptionAuthError(InvalidAuthError):
    """A websocket handshake explicitly rejected its token."""


class ShouldUpdateConfigEntry(HomeAssistantError):
    """The configured device is no longer bound to this account."""
