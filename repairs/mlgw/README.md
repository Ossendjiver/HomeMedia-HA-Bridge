# MLGW source-request power feedback

Optional companion patch for the MLGW 2024.8.2 media-player integration. This does not apply automatically when Home Media Bridge is installed.

A shared MasterLink GOTO_SOURCE telegram alone does not prove that its mapped room is powered. Inactive receivers now remain unconfirmed (`unknown`) until a targeted source action or existing picture/sound power feedback confirms activation. Active receivers continue receiving source changes. Source selection IDs, including intentional LINK/TV mappings, are unchanged.

The integration exposes pending-source, ML address and MLN attributes for diagnosis. Unknown feedback must not be treated as idle or as a confirmed listener. A physical remote may leave a room unconfirmed until device power feedback arrives. Check ML address attribution before enabling this on a live installation.

Back up the installed media-player module, check the patch against that exact source, and apply it only during an approved HA maintenance window. Existing local modifications must be preserved. Do not restart the gateway during playback. This patch is staged and has only offline event tests; physical receiver confirmation requires later validation.

Offline validation: set `MLGW_MEDIA_PLAYER_SOURCE` to the patched media-player file, then run `python -m unittest discover -s tests -p test_mlgw_feedback.py`. The test extracts only the listener/power methods and uses fake events; it never imports or connects to HA.
