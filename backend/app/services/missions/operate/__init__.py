"""Operate mission kind (Phase 2B / Stage 7B-3) — "fly the satellite you
designed," ported from the intern's SatKit prototype
(`C:\\Users\\ahmed\\Downloads\\satkit-platform-fastapi.zip`).

Per the porting rule (MISSIONS_PHASE2B_PLAN.md D4): only the domain logic
survives — the telemetry math and the telecommand vocabulary. SatKit's own
stack (plaintext passwords, a single mutable state object shared by every
user, an unauthenticated endpoint that could permanently kill the
simulation for everyone, a telemetry table that was never actually
written to) is not ported at all; this module rebuilds the same *behavior*
as pure functions against this platform's own attempt/variant model.
"""
