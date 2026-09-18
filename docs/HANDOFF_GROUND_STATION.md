# Ground Station Domain

Back to [`HANDOFF.md`](./HANDOFF.md).

**Status: first-pass doc for a previously undocumented domain — written 2026-09-17.** Ground
Station had zero dedicated handoff doc before this; it only got passing mentions inside
[`HANDOFF_LMS.md`](./HANDOFF_LMS.md)'s mission-kind coverage. Everything below was verified
directly against the code on this date: `backend/app/{models,services,routers}/ground_station/`
in full, the frontend under `frontend/src/pages/ground-station/`, `frontend/src/pages/learn/
GroundStationAttemptPage.tsx`, `frontend/src/pages/operations/GroundStationDevices.tsx`,
`frontend/src/lib/groundStationWebSerial.ts`, `frontend/src/hooks/useGroundStationSocket.ts`,
`frontend/src/api/groundStation.ts`, the four `ground_station*` Alembic migrations, and
`backend/tests/routers/ground_station/test_ground_station.py` (18 passing-as-read tests covering
ownership, ingest, commands, alerts scoping, and the checklist-completion path). Also read
`docs/HANDOFF_LMS.md` and `docs/HANDOFF_VPS_DEPLOYMENT.md` read-only, as instructed, and note
below exactly what they do and don't confirm about this domain.

---

## 0. What this domain actually is

A live CubeSat ground-station telemetry/command console, ported from a legacy standalone app
(the "Madar" platform's `LoRa-Dashboard-V3`) and wired into Missions as a real, ownable mission
kind. Two docstrings in the code disagree about this and only one is current — worth flagging
explicitly:

- `backend/app/models/ground_station/__init__.py`'s module docstring still says Ground Station is
  "deliberately NOT a `missions` kind: no attempts, no scoring, no pass/fail." That was true
  before the 2026-09-14 rework.
- `backend/app/models/ground_station/device.py`'s docstring and every router/service file's own
  docstring (dated 2026-09-14) describe the *current* shape: a rig is now provisioned per
  `MissionAttempt` (solo or team), ownership flows through the attempt, and `Mission.kind ==
  "ground_station"` is a real mission kind the routes check for
  (`services/ground_station/access.py::require_ground_station_attempt`).

**Take the 2026-09-14 shape as current and the `models/__init__.py` docstring as stale** — it
wasn't updated when the rework landed. There is still no scoring/pass-fail: `complete_attempt`
(§4) sets `status="passed"` with `score` staying `null`, so "no grading" from the old docstring is
still accurate, just not "no attempts."

One rig per attempt, created lazily. Telemetry/alerts/photos are genuinely persisted (unlike
commands, which are pure Redis pub/sub — see §2 and §3).

---

## 1. Data model

Two model files, five tables. `backend/app/models/ground_station/device.py`:

- **`ground_station_devices`** (`GroundStationDevice`) — `id` (UUID PK), `label`, `secret_hash`
  (nullable — a leftover from a device-secret auth scheme that ingest no longer checks; kept only
  so existing rows don't need a migration), `mission_attempt_id` (UUID FK →
  `mission_attempts.id`, `ondelete=CASCADE`, **nullable and unique** — nullable means a
  staff-provisioned orphan/shared rig with no student owner; unique enforces one rig per attempt),
  `status` (`"online"|"offline"`, flipped by the ingest endpoints on every successful call),
  `last_seen_at`, `created_at`.

`backend/app/models/ground_station/telemetry.py` — ported verbatim in shape from the legacy app's
own `telemetry`/`alert_thresholds`/`alerts`/`images` tables (per that file's own docstring,
referencing the legacy `backend/serial_reader.py`'s `CREATE TABLE` statements):

- **`ground_station_telemetry`** (`GroundStationTelemetry`) — `id`, `device_id` (FK, CASCADE),
  `recorded_at`, then typed float columns `temp`, `voltage`, `current`, `power`, `rssi`, `snr`,
  `uptime` (int), `lat`, `lon`, `alt`, `pitch`, `roll`, `yaw`, plus a `data` JSONB column holding
  the full raw frame (nothing about a frame's shape is lost even though only some fields get typed
  columns). Indexed on `(device_id, recorded_at)`.
- **`ground_station_alert_thresholds`** (`GroundStationAlertThreshold`) — **`device_id` is the
  primary key** (one row per device, upserted lazily by `get_thresholds`/`set_thresholds`).
  Columns: `temp_max` (35.0 default), `temp_min` (0.0), `voltage_max` (5.5), `voltage_min` (3.0),
  `current_max` (1.0), `power_max` (2.0). No `voltage`/`current`/`power` *min* fields — only max
  thresholds exist for those three.
- **`ground_station_alerts`** (`GroundStationAlert`) — `id`, `device_id` (FK, CASCADE),
  `occurred_at`, `alert_type` (`temp|voltage|current|power`), `threshold`, `current_value`,
  `severity` (default `"critical"` — the only severity value the code ever produces, see §3),
  `acknowledged` (bool, default `false`). Indexed on `(device_id, occurred_at)`.
- **`ground_station_images`** (`GroundStationImage`) — `id`, `device_id` (FK, CASCADE), `bucket`
  (default `"ground-station"`), `path`, `lat`/`lon`/`alt` (nullable), `captured_at`. Indexed on
  `(device_id, captured_at)`.

Migrations, in order: `16162b6766ae_ground_station_devices.py` →
`7964f705a198_ground_station_history_alerts_images.py` →
`b726e963875f_merge_ground_station_and_submission_.py` (a plain Alembic branch merge, no schema
change of its own) → `cacc3b82a3ee_ground_station_mission_ownership.py` (2026-09-14 — adds
`mission_attempt_id`, makes `secret_hash` nullable; this is the rework migration referenced
throughout).

**Commands have no table.** `services/ground_station/devices.py`'s module docstring is explicit
about this: a queued command is a JSON blob pushed onto a per-device Redis list
(`ground-station:device:{id}:commands:pending`) until the on-site agent or a browser tab's Web
Serial connection pops it. If Redis is down, `queue_command` isn't reached defensively — the route
(`console.py::send_command`) 503s up front ("Real-time link unavailable — command not sent")
rather than silently dropping the command, unlike telemetry broadcast which is fire-and-forget
(§3).

---

## 2. Roles and permissions

**The staff-bypass convention, `services/ground_station/access.py`** — this is the reference
implementation other domains model their staff-check logic on (confirmed still present and
unchanged in shape):

```python
async def require_device_access(db, *, device, user) -> None:
    if is_staff(user):
        return
    if device.mission_attempt_id is None:
        raise HTTPException(404, detail="Device not found")
    attempt = await db.get(MissionAttempt, device.mission_attempt_id)
    if attempt is None or not await _owns_attempt(db, attempt, user):
        raise HTTPException(404, detail="Device not found")
```

`is_staff` itself lives in `services/missions/authorization.py` (imported and re-exported from
`access.py`, not duplicated):

```python
_STAFF_ROLES = {"operations", "facilitator"}

def is_staff(user: User) -> bool:
    roles = user.role_values
    return "admin" in roles or bool(_STAFF_ROLES & set(roles))
```

That function's own docstring says it's "the one admin-or-staff check every domain's
per-resource access helper composes with (mission managers, cohort instructors, **ground station
device owners**, ...)" — Ground Station is literally named in the source of truth as the pattern's
reference user.

The shape used everywhere in this domain: **staff bypass, else an ownership check, and 404 (not
403) on denial** — deliberately, so an unauthorized caller can't tell a device/attempt exists at
all. `access.py` exposes four helpers built on this:

- `require_device_access(db, *, device, user)` — used by the console router's
  `get_authorized_device` dependency (`routers/ground_station/deps.py`) and by the WebSocket
  handler (`routers/ground_station/realtime.py`).
- `require_attempt_access(db, *, attempt, user)` — plain ownership check on an attempt.
- `require_ground_station_attempt(db, *, attempt, user)` — `require_attempt_access` **plus** a
  `mission.kind == "ground_station"` check. This extra check exists specifically because, without
  it, an owner (or staff acting for one) could point `/ground-station/attempts/*` routes at *any*
  attempt they can see — including, via `complete_attempt`, self-passing an unrelated quiz/design
  run by flipping its status to `"passed"`. Confirmed covered by
  `test_complete_attempt_rejects_a_non_ground_station_attempt` and
  `test_get_attempt_device_rejects_a_non_ground_station_attempt` in the test file.
- `visible_device_ids(db, *, user)` — returns `None` for staff (unrestricted) or the actual set of
  device ids the caller owns (solo attempt or as a team member via `MissionAttemptMember`), used
  by `GET /ground-station/devices` to filter the list.

Ownership resolution (`_owns_attempt`): the caller owns an attempt if `attempt.user_id ==
user.id`, or if a `MissionAttemptMember` row exists for `(attempt.id, user.id)` — i.e. any member
of the team that started the attempt, not just whoever clicked "start."

**Two distinct role checks, not one** — worth being precise about, since they look similar but
aren't identical:

- **Viewing/using a device or attempt** (console routes, the WebSocket) uses `is_staff`:
  `admin`, `operations`, or `facilitator`.
- **The ops admin endpoints** (`routers/ground_station/admin.py` — `POST
  /ground-station/admin/devices` to register an orphan rig, `GET /ground-station/admin/attempts`
  for the monitoring list) use `require_operations = RequireRole(["operations"])`
  (`core/dependencies.py`), which allows `admin` or `operations` **only** — a `facilitator` can
  view any device via `is_staff` but cannot register a new orphan device or list the ops attempts
  summary. Confirmed by `test_admin_register_device_requires_operations_role` (a plain `student`
  gets 403; no facilitator-role test exists in the suite, but the `RequireRole(["operations"])`
  construction itself doesn't include `"facilitator"`).

**Ingest has no auth at all** — this is deliberate, not an oversight. `routers/ground_station/
deps.py::get_open_device` docstring: "Operator directive — the whole Ground Station surface is
already private (attempt-owner + staff only, ...), so the ESP32 side stays a plain
unauthenticated POST to a hard-to-guess device UUID. No secret to bake into firmware, no rotation,
no header — the tradeoff is explicit and accepted: anyone who somehow learns a specific device id
could inject fake data for it." Confirmed by `test_ingest_requires_no_auth_at_all` (POST with no
`Authorization` header succeeds) and `test_ingest_rejects_unknown_device` (still 404s an
unrecognized device id — the only check that remains).

---

## 3. How telemetry actually flows

Three independent paths feed the same ingest endpoint, all landing on `POST /ground-station/
devices/{device_id}/telemetry` (`routers/ground_station/ingest.py`, no auth, see §2):

1. **On-site agent / ESP32 firmware** — posts directly to that endpoint over the network. Its
   frame shape supports dual field names on purpose (`services/ground_station/telemetry.py`'s
   `_field()` helper checks `temp_C` or `temp`, `bus_voltage_V` or `voltage`, `current_mA` or
   `current`, `power_mW` or `power`, `lon` or `lng`) because real firmware in the wild used both
   conventions and the legacy backend accepted either.
2. **On-site agent polling for commands** — `GET /ground-station/devices/{device_id}/
   commands/pending` drains up to 20 queued Redis commands per call
   (`services/ground_station/devices.py::pop_pending_commands`), and `POST .../commands/
   {command_id}/ack` reports back what happened.
3. **Browser-side Web Serial direct connect** (`frontend/src/lib/groundStationWebSerial.ts`) —
   lets a student's own Chrome/Edge tab talk straight to the ESP32 over USB with no on-site agent
   at all. See the module-level connection lifecycle detail in §6 — this is the source of the
   documented gotcha.

**Web Serial → backend, concretely:** `connectWebSerial()` opens the serial port at baud 115200,
starts a read loop that buffers incoming bytes and splits on `\n`. Each line is stripped of a
`TX: `/`TX `/`ACK TX: ` prefix if present (`parseTelemetryLine`), then `JSON.parse`d. If the
parsed object has both `temp` and `voltage` defined, it's treated as a valid frame and forwarded
via `callbacks.onTelemetry`; if it also has `yaw`, a second `onAdcsTelemetry` callback fires with
attitude/position data. Non-JSON or malformed lines are silently ignored — same behavior as the
legacy parser, per the file's own comment. `WebSerialConnect.tsx` wires `onTelemetry`/
`onAdcsTelemetry` straight to `sendBrowserTelemetry(deviceId, entry.data)`
(`frontend/src/api/groundStation.ts`), which POSTs to the exact same `/telemetry` endpoint the
agent uses — **not** a `/telemetry/browser` variant. (`groundStationWebSerial.ts`'s own top-of-file
comment says frames are "POSTed to `/ground-station/devices/{id}/telemetry/browser`" — that
`/browser` suffix does not exist anywhere in the backend; the comment is stale. The real, current
endpoint, confirmed from `sendBrowserTelemetry` and `routers/ground_station/ingest.py`, is the
plain `/telemetry` route, identical to what the agent/ESP32 use.) One JSON POST is sent **per
parsed serial line while connected** — see §7 for the production-log implication.

**Backend ingest → broadcast:** `ingest_telemetry()` calls `touch_last_seen` (flips `status` to
`"online"`, updates `last_seen_at`), then `_ingest_and_broadcast()`:
`persist_telemetry` (INSERT into `ground_station_telemetry`) → `check_thresholds` (compares the
frame against that device's `GroundStationAlertThreshold` row, creating debounced `GroundStationAlert`
rows for any violation — 5-second debounce window, matching the legacy app's own "avoid
overwhelming the user" behavior, per `_DEBOUNCE_SECONDS` in `services/ground_station/
telemetry.py`) → `db.commit()` → `safe_publish_to_device(..., "telemetry_frame", ...)` (Redis
`PUBLISH` on channel `ground-station:device:{device_id}`) → one more `safe_publish_to_device(...,
"alert", ...)` per newly created alert. `safe_publish_to_device` never raises — a dropped
broadcast must not undo the DB write that triggered it, so a Redis outage degrades to "no live
update" rather than a 500.

**Backend → dashboard:** `routers/ground_station/realtime.py`, `GET /ws/ground-station/
{device_id}` (note: under `/ws/`, not `/ground-station/`, mounted as its own router with that
prefix). Auth is via `get_ws_user` — the frontend passes the JWT as a query string (`?token=...`)
since a browser `WebSocket()` constructor can't set an `Authorization` header
(`frontend/src/hooks/useGroundStationSocket.ts`). The handler resolves the device, runs the same
`require_device_access` check as the REST console routes, subscribes to that device's Redis
pub/sub channel, and forwards every message verbatim to the socket via `pubsub.listen()`. It also
tracks a live-viewer count per device with `INCR`/`DECR` on a `ground-station:device:{id}:
connections` Redis key (`services/ground_station/realtime.py`), read back by `GET .../stats`'s
`active_connections` field. `useGroundStationSocket` reconnects with exponential backoff (1s base,
30s cap, ±25% jitter) on any close.

**Message types on the wire** (`MessageType` in `services/ground_station/realtime.py`, mirrored in
the frontend's `GroundStationMessage` union): `telemetry_frame`, `command_queued`, `command_ack`,
`device_status`, `photo_added`, and `alert` (the last is used by the router but not listed in the
backend `MessageType` Literal — a minor drift between the type alias and what's actually
published; not a bug, since `publish_to_device` takes the type as a plain string, but worth
knowing if you're type-checking against `MessageType`).

**Command relay is peer-to-peer through the dashboard, not agent-only:** when `DeviceConsole`
(`frontend/src/pages/ground-station/GroundStationPage.tsx`) receives a `command_queued` message
over the WebSocket, it checks `isWebSerialConnected()` — if *this* browser tab happens to have an
open Web Serial connection to the rig, it writes the command down the wire
(`writeSerialCommand`) and acks it (`ackCommand`). This is fire-and-forget by design: `ok` only
means the serial write succeeded, not that the firmware executed it, per that code's own comment.
Every other open viewer tab is a no-op for this branch.

---

## 4. Mission integration (`mission_kind` gating)

Ground Station is a real `Mission` (`Mission.kind == "ground_station"`, a plain `String(16)`
column, not a DB enum), started/tracked through the normal Missions attempt machinery — see
[`HANDOFF_LMS.md`](./HANDOFF_LMS.md) for how `MissionAttempt`/checklist items/`mission_kind`
gating work in general; this section only covers what's specific to Ground Station.

- **Console entry point:** `GET /ground-station/attempts/{attempt_id}/device`
  (`routers/ground_station/attempts.py::get_attempt_device`) resolves (or lazily creates, via
  `get_or_create_device_for_attempt`) the one rig for that attempt, after
  `require_ground_station_attempt` confirms ownership and mission kind. Device creation is lazy —
  on first console visit, not at attempt-start — specifically so starting the mission never fails,
  and a unique constraint on `mission_attempt_id` makes a concurrent duplicate-insert race resolve
  to a clean re-fetch rather than a 500 (`IntegrityError` caught in
  `get_or_create_device_for_attempt`).
- **No `Design` row:** unlike a `design`-kind attempt, a `ground_station` attempt never gets a
  `Design` row — there's no wizard, no scoring, no pass/fail path. This is exactly why the LMS
  checklist UI has to branch on `mission_kind` rather than always offering a generic "View run."
- **The actual branch, `frontend/src/pages/lms-authoring/components/
  LmsProgressAndMissions.tsx`** (confirmed current, lines ~692–699):
  ```tsx
  const canViewRun = isMissionRun && item.mission_kind === "design"
  const canOpenConsole = isMissionRun && item.mission_kind === "ground_station"
  ```
  with the comment directly above it explaining why: "`DesignRunDetail` replicates the Design
  wizard off a `Design` row that only a design-kind attempt ever has — a Ground Station (or any
  other non-design) run has no such row, so pointing it there just 404s ('Couldn't load this run's
  detail.')." `canOpenConsole` renders an "Open console" button that navigates straight to
  `/learn/missions/ground-station/$attemptId` instead of the design run-detail panel. This is the
  fix for the real production bug referenced in the task brief (a bare "View run" 500ing on
  ground_station attempts, fixed in PR #87) — the checklist-item mechanics themselves (how
  `mission_run` items resolve `status`/auto-completion) are LMS's, not Ground Station's; see
  `HANDOFF_LMS.md` rather than this doc for that side.
- **Self-serve completion, no grading:** `POST /ground-station/attempts/{attempt_id}/complete`
  (`routers/ground_station/attempts.py::complete_attempt`) is the *only* way a Ground Station
  attempt's status changes. It sets `status = "passed"` and stamps `submitted_at`/`decided_at`,
  idempotently, but never touches `score` (stays `null`) and never runs through
  `decide_attempt`/`award_points` — per its own docstring, "marking this never mints points, it
  just flips the one field the checklist's own auto-tracking already reads." Confirmed by
  `test_complete_attempt_sets_passed_with_no_score`.
- **Route redirect on entry:** `frontend/src/pages/learn/MissionPage.tsx` auto-redirects an
  active-but-undecided attempt straight to `/learn/missions/ground-station/$attemptId` when
  `mission.kind === "ground_station"` — same "own route, keyed on the attempt" treatment as the
  `operate` mission kind, except with no `decided` guard, since Ground Station attempts are never
  "decided" in the scored sense.

---

## 5. Ops / admin view

`frontend/src/pages/operations/GroundStationDevices.tsx`, backed by
`routers/ground_station/admin.py` (both gated by `require_operations` — admin or operations role
only, see §2):

- **"Mission runs"** — every `ground_station` mission attempt with its owner label (student's
  `full_name`, or the team's `name` if it's a team attempt) and rig status/last-seen, newest
  first. Backed by `GET /ground-station/admin/attempts` →
  `services/ground_station/devices.py::list_ground_station_attempts`, which joins
  `MissionAttempt` → `Mission` (filtered to `kind == "ground_station"`) → `User`/`Team` (outer,
  whichever applies) → `GroundStationDevice` (outer — an attempt technically could have no device
  yet, if no one has opened its console). Each row links straight into that attempt's live console
  at `/learn/missions/ground-station/$attemptId`.
- **"Shared / demo rigs"** — devices with `mission_attempt_id IS NULL`, i.e. staff-registered
  orphan rigs (a booth/demo kit not tied to any student's run). Registered via `POST
  /ground-station/admin/devices` → `services/ground_station/devices.py::register_device`, which
  takes only a `label` — no secret, since ingest doesn't check one. The device id itself, shown
  and copyable in the UI, is the entire "address" a booth rig's firmware needs.
- The frontend derives the orphan list client-side (`devices.filter(d =>
  !d.mission_attempt_id)`) from the plain `GET /ground-station/devices` list rather than a
  dedicated orphan-only endpoint — worth knowing if you're looking for a backend filter that
  isn't there.

---

## 6. The Web Serial connection-lifecycle gotcha (confirmed from the code)

**Confirmed as of 2026-09-17, by reading `frontend/src/lib/groundStationWebSerial.ts` and
`frontend/src/components/ground-station/WebSerialConnect.tsx` directly — this is still the actual
behavior, not just an assumption carried over from an earlier note:**

`groundStationWebSerial.ts` holds its connection state in **module-level variables** —
`serialPort`, `serialWriter`, `serialReader`, `readerKeepAlive` — not React state, not anything
scoped to a component instance:

```ts
let serialPort: SerialPort | null = null;
let serialWriter: WritableStreamDefaultWriter<string> | null = null;
let serialReader: ReadableStreamDefaultReader<string> | null = null;
let readerKeepAlive = true;
```

`WebSerialConnect.tsx`, the only component that calls `connectWebSerial`/`disconnectWebSerial`,
has **no `useEffect` cleanup** that calls `disconnectWebSerial()` on unmount — `connect()`/
`disconnect()` only run from the two buttons' `onClick` handlers. Nothing in `DeviceConsole`
(`GroundStationPage.tsx`) or `GroundStationAttemptPage.tsx` calls `disconnectWebSerial` either.

**Net effect, confirmed by tracing the actual code paths:**

- **Closing or reloading the browser tab** does stop telemetry — the JS execution context is
  destroyed, the underlying serial port connection dies with it (browser/OS reclaims the USB
  handle), and the read loop simply can't continue.
- **Navigating away within the SPA** (e.g. clicking back to the missions list, or to a different
  attempt) does **not** stop it. Since `DeviceConsole`/`WebSerialConnect` unmounting never calls
  `disconnectWebSerial()`, the module-level `serialPort`/`readLoop()` simply keeps running in the
  background, continuing to POST every parsed serial line to whatever `deviceId` closure it
  captured at connect time — even though that device's console is no longer the active page. The
  read loop only stops when `readerKeepAlive` is flipped to `false`, which only happens inside
  `disconnectWebSerial()` — i.e. only an explicit "Disconnect" click, or the tab closing outright,
  actually ends it.
- This is a real "why is this still transmitting" trap for ops/students: a student who plugs in,
  watches telemetry, then clicks away to browse other missions (without hitting "Disconnect"
  first) is still silently streaming that rig's serial output to the backend, tagged to the
  original `deviceId`, for as long as that tab stays open — potentially well after they've stopped
  looking at the console.
- One partial mitigation elsewhere in the same file tree, for contrast: `SimToggle.tsx`'s
  simulated-telemetry interval **does** clean up correctly (`useEffect` returns a `clearInterval`)
  — so the "no cleanup" problem is specific to the Web Serial module-level singleton, not a
  blanket pattern across this domain's frontend code.

---

## 7. Gotchas / "if you see X in prod, that's normal"

- **High-frequency per-line telemetry POSTs while a device is connected are expected, not a
  bug or an attack.** Confirmed from the code: every single parsed serial line from an ESP32 (or
  every 1-second tick of `SimToggle`'s simulated mode, per its `INTERVAL_MS = 1000`) triggers one
  full `POST /ground-station/devices/{id}/telemetry` round-trip — parse → DB insert → threshold
  check → Redis publish, unthrottled, with no batching or debounce on the ingest side itself (the
  5-second debounce in `check_thresholds` only suppresses *repeated alert rows*, not repeated
  telemetry POSTs). Real ESP32 firmware and the Web Serial browser path both produce this pattern.
  If prod logs show a burst of near-identical POSTs to the same `/ground-station/devices/{id}/
  telemetry` path while a rig is actively connected, that's the domain working as designed, not a
  malfunction to chase.
- **Ingest is intentionally unauthenticated.** A 202-Accepted POST to `/ground-station/devices/
  {id}/telemetry` with no `Authorization` header is correct, not a security hole someone forgot to
  close — see §2's `get_open_device` discussion. The only real trust boundary is the device UUID
  itself being hard to guess.
- **§6's Web Serial persistence-across-navigation issue** is the other big one — see that section
  in full; don't assume a still-transmitting rig after a student "left" its console page is a
  leak or a bug report worth escalating on its own — it's the documented current behavior.
- **`GroundStationDevice.secret_hash` is dead weight, not a bug.** It's `nullable=True` and never
  read anywhere on the ingest path (per `device.py`'s own docstring) — a pre-2026-09-14 leftover
  kept only to avoid a needless migration on existing rows. Don't be surprised it's unused; don't
  try to "fix" it into being checked again without confirming that's actually wanted, since the
  no-auth-on-ingest decision was an explicit operator directive.
- **The `models/ground_station/__init__.py` docstring is stale** (see §0) — it still describes the
  pre-rework, attempt-less shape. Don't trust it over the newer per-file docstrings or this doc.
- **`groundStationWebSerial.ts`'s own top comment references a `/telemetry/browser` endpoint that
  does not exist.** The real call (`sendBrowserTelemetry` in `api/groundStation.ts`) posts to the
  plain `/telemetry` route — see §3. Don't go looking for a `/browser` variant; there isn't one.
- **The `MessageType` Literal doesn't include `"alert"`**, even though the ingest router
  publishes messages of that type and the frontend's `GroundStationMessage` union handles it. Not
  a runtime bug (the publish function takes a plain string), just a type-definition gap — see §3.
- **Two different staff-ish checks, not one** — `is_staff` (admin/operations/facilitator) gates
  viewing a device or attempt; `require_operations` (admin/operations only) gates the admin
  register-device and attempts-list endpoints. A facilitator can watch any run's console but
  cannot register an orphan device or pull the ops attempts summary. See §2.

**What I could not fully confirm:**

- **How the WebSocket connection traverses nginx/the reverse proxy in production.**
  `docs/HANDOFF_VPS_DEPLOYMENT.md` (read in full for this doc) documents `portal.spacepoint.ae`'s
  nginx config proxying `/api/` to `http://127.0.0.1:8000/` (`location /api/ { proxy_pass
  http://127.0.0.1:8000/; }`), but that file's shown nginx examples don't include an explicit
  `location /ws/` block or the `proxy_set_header Upgrade $http_upgrade; proxy_set_header
  Connection "upgrade";` pair a WebSocket proxy needs. It's plausible the same `/api/` block (or a
  broader catch-all) already covers `/ws/ground-station/*` in the real, live nginx config, but
  that specific detail isn't present in either doc I was told to read, and I did not have access
  to the actual production nginx files to check directly. Flagging this rather than guessing — a
  future agent debugging "the dashboard falls back to failed reconnects in prod but works
  locally" should verify the live nginx config's WebSocket-upgrade handling for `/ws/` directly on
  the VPS.
- **`test_admin_register_device_requires_operations_role`** only proves a plain `student` is
  rejected; I did not find a test proving a `facilitator` is specifically rejected from the admin
  endpoints (as opposed to `operations`/`admin` being accepted). The `RequireRole(["operations"])`
  construction itself is unambiguous in code, so this is a low-risk gap, but it's untested as far
  as I could find.
