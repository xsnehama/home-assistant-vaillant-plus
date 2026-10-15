import inspect
import socket
from aiohttp import ClientError
from homeassistant.helpers import aiohttp_client
from vaillant_plus_cn_api import (
    InvalidAuthError, InvalidCredentialsError, RequestError,
    VaillantApiClient as BaseVaillantApiClient,
)
from vaillant_plus_cn_api.const import API_HOST


class VaillantApiClient(BaseVaillantApiClient):
    """Classify HTTP failures without logging response bodies containing tokens."""

    async def _request(self, method, url, **kwargs):
        kwargs.setdefault("params", {})
        headers = kwargs.setdefault("headers", {})
        headers["appkey"] = self._application_key
        headers["User-Agent"] = self._user_agent
        if "Authorization" not in headers and self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        shared = self._session is not None and not self._session.closed
        session = self._session if shared else self._new_session()
        try:
            async with session.request(method, f"{API_HOST}/{url}", **kwargs) as response:
                status = response.status
                if status in (401, 403) and url.startswith("auth/oauth/token"):
                    raise InvalidCredentialsError
                if status == 400 and url.startswith("auth/oauth/token"):
                    data = await response.json(content_type=None)
                    if isinstance(data, dict) and data.get("error") in ("invalid_grant", "access_denied"):
                        raise InvalidCredentialsError
                    raise RequestError("Vaillant login request was rejected (HTTP 400)")
                if status in (401, 403, 424):
                    raise InvalidAuthError
                if status != 200:
                    raise RequestError(f"Vaillant request failed (HTTP {status})")
                data = await response.json(content_type=None)
                if not isinstance(data, dict):
                    raise RequestError("Vaillant returned an unsupported response")
                return data
        except (ClientError, TimeoutError) as error:
            raise RequestError("Vaillant request could not be completed") from error
        except ValueError as error:
            raise RequestError("Vaillant returned an invalid response") from error
        finally:
            if not shared:
                await session.close()

def get_aiohttp_session(hass):
    if len(inspect.signature(aiohttp_client.async_get_clientsession).parameters) < 3:
        return aiohttp_client.async_get_clientsession(hass)
    else:
        return aiohttp_client.async_get_clientsession(hass, True, socket.AF_INET)
