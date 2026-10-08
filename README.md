# Home Media Bridge

A small Home Assistant integration that connects Home Media's remote Mood Wheel and Pattern Play features to the existing BS5c library service. The recommendation engine and queue maintenance continue to run on the BS5c device.

## Installation

This repository contains only the Home Assistant bridge. HomeMedia app development remains separate. Add `https://github.com/Ossendjiver/HomeMedia-HA-Bridge` to HACS as a custom **Integration** repository.

For manual installation, copy `custom_components/home_media_bridge` into HA's `config/custom_components/`, restart HA, then add **Home Media Bridge** under Settings → Devices & services. The prepared ZIP preserves that directory layout.

Add this repository in HACS → Custom repositories → Integration, download it, restart HA, and add the integration.

Enter the BS5c host (`192.168.4.103` by default) and library port (`8788`). These are LAN addresses reached by HA, not public endpoints. Initial validation reads the mood suggestion only; it does not start playback. If BS5c is temporarily unavailable after an HA restart, HA retries setup. Remove and re-add the integration to change its backend address.

## Home Media login

Install/configure the integration first. In Home Media open Settings → Connections → Remote Home Assistant login. Paste your HTTPS HA remote address; an existing `/auth/authorize?...` link is accepted and reduced to its server origin. Sign in in the browser with an HA administrator account, return to Home Media, test the bridge, then enable **Use bridge when BS5c is unreachable**.

The app prefers the local BS5c service after a bounded read-only reachability check and uses HA when that service is unreachable, including on cellular or another Wi-Fi network. A failed mutation is never retried through the other route.

The app uses the integration's static OAuth client page and `homemedia://ha/auth` callback. Credentials are encrypted under a dedicated Android Keystore key. Remote account data is separate from local HA/MA settings and omitted from settings backups. Disconnect clears local credentials before attempting server-side refresh-token revocation.

## Boundary

- `GET /api/home_media_bridge`: authenticated protocol/configuration status.
- `POST /api/home_media_bridge`: HA administrator only; fixed operations `recommend`, `mood`, `mix_state`, `mix`, `suggestions`, `context`, `event`, and `action`.
- `GET /api/home_media_bridge/auth-client`: unauthenticated static callback registration only. No device addresses, history, tokens or user state.
- HA connects to the configured private BS5c library address. Callers cannot supply a target URL, HTTP method, HA script or raw MA command.
- No redirects are followed, HA authorization headers are not forwarded to BS5c, payload/response sizes are bounded, and failed mutations are not automatically replayed.
- Music Assistant retains its own remote connection and audio streaming. This bridge does not proxy audio, video, Kodi RPC, BLE or general HA room controls.
- The LAN-only BS5c services do not need independent remote exposure.

## Offline verification

Tested against Home Assistant 2026.9.4. The test suite uses a fake local BS5c server and HA's actual authentication middleware, including unsigned/read-only rejection, command allowlisting, no credential forwarding, no redirect following, response limits and unload behavior. No live HA installation or playback tests are performed by this package.

```sh
PYTHONPATH=. python -W ignore -m unittest discover -s tests -v
```
