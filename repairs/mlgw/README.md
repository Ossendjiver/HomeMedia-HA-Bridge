# MLGW address discovery repair

Live reproduction confirmed crossed feedback attribution between two products: individually addressed harmless LIGHT TIMEOUT probes returned consistent bus addresses, but HA attached each to the other entity. The installed startup discovery broadcasts probes in a burst and pairs replies by arrival position. Reordered or missing replies can therefore corrupt the room-to-address map.

`address-discovery.patch` changes MLGW 2024.8.2 discovery to probe one product at a time. It stops on timeout, missing address, or duplicate address, and always removes the listener. Source IDs and existing source/power feedback semantics are preserved.

Back up the installed module and apply only if the patch matches its exact source. Restart HA while routing is idle, then verify each target with separate harmless probes and a controlled transfer. Home Media Bridge does not install this companion patch automatically.

Six offline tests cover normal assignment, timeout, duplicate address, disabled logging, absent ML connection, and cancellation. After SSD-backed deployment and one HA restart, repeated product probes matched their correct entities. Repeating the same Bedroom Mini song-radio transfer to Ensuite moved all 21 items in 2.64 seconds, with no Dining activation event and all unrelated rooms remaining off. Test playback was stopped and original volumes restored. Physical receiver screens were not independently observed.

## Earlier proposal remains on hold

Do not deploy `source-request-power.patch`. It was an investigative proposal and changes power-feedback semantics. Address attribution, rather than the source-to-power inference, was directly shown to be wrong in the reproduced incident.

To run the six offline discovery tests against an installed or patched source copy: `MLGW_MEDIA_PLAYER_SOURCE=/path/to/media_player.py python -m unittest discover -s tests -p test_mlgw_address_discovery.py`. Without a source path, these optional companion tests skip.
