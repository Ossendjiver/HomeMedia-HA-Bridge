# MLGW address discovery repair

Live reproduction confirmed crossed feedback attribution between two products: individually addressed harmless LIGHT TIMEOUT probes returned consistent bus addresses, but HA attached each to the other entity. The installed startup discovery broadcasts probes in a burst and pairs replies by arrival position. Reordered or missing replies can therefore corrupt the room-to-address map.

`address-discovery.patch` changes MLGW 2024.8.2 discovery to probe one product at a time. It stops on timeout, missing address, or duplicate address, and always removes the listener. Source IDs and existing source/power feedback semantics are preserved.

Back up the installed module and apply only if the patch matches its exact source. Restart HA while routing is idle, then verify each target with separate harmless probes and a controlled transfer. Home Media Bridge does not install this companion patch automatically.

Six offline tests cover normal assignment, timeout, duplicate address, disabled logging, absent ML connection, and cancellation. The reported transfer was reproduced before deployment; post-deployment results are recorded separately.

## Earlier proposal remains on hold

Do not deploy `source-request-power.patch`. It was an investigative proposal and changes power-feedback semantics. Address attribution, rather than the source-to-power inference, was directly shown to be wrong in the reproduced incident.
