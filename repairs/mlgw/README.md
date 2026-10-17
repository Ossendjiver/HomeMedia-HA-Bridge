# MLGW feedback investigation — ON HOLD

Do not deploy `source-request-power.patch`. It is an investigative proposal, not a confirmed repair for the reported room-status problem. Home Media Bridge does not apply it automatically.

The incident logs show an HA room-status change immediately after a source telegram. They do not establish whether the cause is incorrect commands, routing/automation side effects, ML-address attribution, or the existing feedback implementation. An offline listener reproduction demonstrates a possible code path; it does not establish the cause on the installed system. Previously working physical-remote feedback is important counter-evidence.

The proposed patch changes how inactive receivers handle source requests and can leave real physical-remote activations unconfirmed. Preserve the installed MLGW behaviour while command provenance and device mapping are investigated. Keep intentional LINK/TV source mappings unchanged.

The patch and event tests are retained only for investigation. It must not be included in a routine HA deployment. Any future change needs evidence identifying the faulty layer and targeted physical validation when live tests are authorized.
