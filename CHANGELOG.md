# Changelog

<!--next-version-placeholder-->
## v1.4.0.post3 (2026-10-15)
* Key the dispatcher bookkeeping and the token-update signal by `entry.entry_id`, so a second config entry can no longer unsubscribe the first entry's handles.
* Take entity unique IDs, device identifiers and the device-update subscription from the configured device id, and omit device name/model until the cloud device object resolves.
* Pass `verify_ssl` and `family` by name when creating the shared aiohttp session, keeping IPv4 without depending on positional arguments.

## v1.4.0.post2 (2026-10-15)
* Keep a healthy websocket subscription during proactive authentication refresh and restore the normal refresh interval after successful recovery.
* Add the Home Assistant reauthentication flow and unify authentication, network and exhausted-retry control errors.
* Preserve numeric zero gas consumption; expose missing or invalid gas data through an empty value and Chinese status attributes without inferring a missing meter.
* Keep existing gas names and unique IDs; leave units and statistics metadata unset until the protocol's units and scaling are verified.
* Update maintenance ownership and support links to the Chinese fork while keeping the vaillant_plus domain.

## v1.4.0.post1 (2026-10-15)
* Selectively incorporate upstream v1.4.0 fixes into the Chinese maintenance fork.
* Discover entities from accumulated attributes on every gateway update and from the initial cache.
* Raise a Home Assistant error when control retries fail, and advertise climate and water-heater on/off services.
* Require vaillant-plus-cn-api 2.0.1 and distinguish authentication, network and unsupported-device configuration errors.
* Reuse the saved token on startup while preserving proactive refresh, refresh locking, reconnection backoff and actual subscription-state availability.
* Add redacted diagnostics, the central-heating mode sensor and domestic-hot-water temperature-limit fallbacks.
* Preserve existing entity names and unique IDs, numeric statistics, Chinese diagnostic mappings and invalid tank-temperature handling.
* Require Home Assistant 2024.2 or later.

## v1.2.4 (2024-04-05)
* [#13](https://github.com/daxingplay/home-assistant-vaillant-plus/issues/13) Support to disable IPv6 in this integration for Home Assistant version >= `2023.10.0`.
* Add Github actions for more HA versions.

## v0.6.0 (2023-05-13)
* Refactor to use new API. Resolve [#5](https://github.com/daxingplay/home-assistant-vaillant-plus/issues/5)

## v0.6.0 (2023-05-13)
### Others
* Re-tag to match HACS requirements.

## v0.5.1 (2023-05-13)
### Bug
* Fix login failed issues when auth token expired.

## v0.3.1 (2023-02-27)
### Bug
* Fix custom components cannot be installed due to dependency conflict.
