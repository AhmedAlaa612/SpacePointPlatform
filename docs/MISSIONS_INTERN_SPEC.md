# Proposing a Mission

Back to [`HANDOFF.md`](./HANDOFF.md).

This is for interns who want to turn something they've built — a game, a
simulator, a small interactive tool — into a real mission students can play
inside the platform. It was written *after* we did this for real once
(porting a satellite ground-station simulator called SatKit into the
"Operate Your Satellite" mission, Missions Phase 2B stage 7B-3/4/5), using
what actually slowed that integration down. If this doc had existed before
that port, it would have been faster. That's the bar the next one should
clear too — update it when you learn something new.

## The flow, in short

1. **You submit** — a repo link or a zip, plus a description of what it
   does and what students would learn. `POST /missions/proposals`
   (or the form at `/interns/propose-mission`). You don't need a finished,
   polished thing — a rough prototype that clearly demonstrates the idea is
   enough to start a conversation.
2. **Staff reviews it** — someone reads your description, looks at what you
   built, and either starts a conversation with you or passes on it. This
   is a human decision, not an automatic check.
3. **Staff integrates it** — this is the part people usually underestimate.
   Nothing about your submission becomes a real mission automatically.
   Someone extracts the actual logic from what you built and re-wires it
   against this platform's own conventions (see "What actually gets
   ported" below). This is real engineering work, and it's also where you
   might get pulled in to help, since you know the domain best.
4. **You might get to manage it** — once your mission is live, staff can
   assign you as its manager (`mission_managers`, Phase 2B stage 7B-7).
   That gets you a dashboard showing who's attempted it, pass rates, and a
   review queue for anything that needs a human grade — without needing
   general staff access to the whole platform. You still can't edit the
   mission's own content or thresholds once it's published; that stays
   frozen until it goes back to draft, on purpose (see "What you *can't*
   do" below).

## What a good submission includes

- **A working prototype**, in whatever stack you're comfortable with. See
  "preferred tech" below for why the stack barely matters.
- **A plain-language description** of what a student does, step by step,
  and what they're supposed to learn or practice. If you can't explain the
  win condition in one sentence, that's worth fixing before you submit —
  see the SatKit story below for why this specific thing is the single
  biggest time sink in an integration.
- **What state your mission needs to remember.** Concretely: what does one
  attempt need to track while it's in progress, and what does "done, here's
  your score" look like? You don't need to design a database for this —
  just describe it in plain terms (see "You probably don't need a
  database" below).

You do **not** need to write it in this platform's stack, integrate with
its auth, or touch its database yourself. That part is explicitly not your
job — see the next section.

## What actually gets ported (and what doesn't)

**We keep:** your actual game logic — calculations, rules, state machines,
the vocabulary of your domain (what a "command" is, what an "anomaly" is,
what counts as a pass). If it's a pure function or a clean rule ("if X then
Y"), it usually ports almost unchanged, regardless of what language you
wrote it in.

**We throw away and rebuild fresh:** your auth, your web framework, your
database, your API routes. This platform has its own login system, its own
async Python/FastAPI backend, its own React frontend, its own database
schema — and your mission gets wired into all of those from scratch, using
this platform's own conventions, not yours. This isn't a comment on your
code; it's true of *every* port, even from a well-built source. Don't
spend effort making your auth/deployment/hosting production-ready — it
will not survive the port, and that effort would be wasted.

This means: **your prototype's own tech stack barely matters.** Node,
Python, a static HTML/JS page, Unity — whatever's fastest for you to build
in is fine. What matters is whether the *logic* is written in a way that's
easy to lift out. Plain functions and explicit state are easy. Logic that's
deeply tangled into a specific framework's request lifecycle, or that
lives entirely in database triggers, or that depends on global mutable
state, is harder — not impossible, but harder, and that difficulty is
exactly what cost us the most time on the first port (see below).

## You probably don't need a database

The SatKit port needed **zero new database tables.** Every attempt's state
— what commands were issued, what happened, the current score — lives in
one JSON field (`mission_attempts.payload`) that already exists for every
mission on this platform. Live telemetry wasn't stored at all: it's
computed fresh, live, as a pure function of "how many seconds since this
attempt started" (`compute_telemetry(elapsed_seconds)`). No background
job, no polling loop writing to a table, no per-tick state to keep in sync.

If your mission's state can be described as "an ordered list of events
that happened" (commands issued, choices made, steps completed) plus "a
rule for turning that list into a score," you very likely don't need new
tables either — just describe the events and the scoring rule, and staff
can almost certainly fit it into the existing shape. Only flag it if your
mission genuinely needs to persist something across attempts (a shared
leaderboard beyond the platform's existing one, a persistent world state)
— that's the actual signal for "this needs new schema," not "it has more
than one moving part."

## Your win condition is the thing to nail down before you submit

The single biggest thing that slowed the SatKit integration down: **SatKit,
as built, had no way to win or lose.** It was a pure simulator — you could
send commands and watch numbers change, forever, with nothing that ever
resolved into "you passed" or "you failed." Every other mission on this
platform (quizzes, the CubeSat design mission) already had a scoring model
to lean on. This one didn't, so an entire scoring mechanic — anomaly
injection, a set of "fix" commands that didn't exist in the original,
the rule for turning "how many anomalies did you resolve" into a 0–100
score — had to be designed from scratch, as new content, not ported from
anything you'd find in the SatKit repo.

If your prototype already resolves to a score or a pass/fail, say so
explicitly and describe the rule. If it doesn't yet, spend your prototyping
time adding *some* rule — even a rough one — before you submit. It doesn't
need to be the final tuning; a first cut of "here's how a run ends and
here's what determines success" is worth far more to the integration than
another visual polish pass. This platform's existing missions all express
their result as a score against a threshold (`variant.pass_threshold`,
0–100) — if your mission's result can fit that shape, it plugs straight
into points, leaderboards, and prerequisites with no extra work from
anyone.

## Small things that cost real time for no real reason

- **Naming consistency.** SatKit's frontend used `camelCase` keys and its
  backend used a different convention in places, so every field had to be
  manually reconciled during the port. Pick one naming convention (snake_case
  is what this platform uses end to end) and use it consistently between
  whatever you call "frontend" and "backend" in your prototype — it costs
  you nothing to do up front and it's pure friction to untangle later.
- **Test your own submit buttons.** A real bug we caught during the port
  (not in SatKit — in *our own rebuild* of it): a form that only submitted
  on pressing Enter, with no visible button, is both an accessibility gap
  and something automated testing tools trip on. If a student (or a test)
  can look at your screen and not know how to submit something, that's
  worth fixing regardless of which side of the port it's on.
- **Don't build your own security.** SatKit had a real, working
  unauthenticated "kill everything" endpoint and stored passwords in plain
  text. None of that gets ported — this platform's auth replaces it
  entirely — but it's also just not worth your time to build in a
  prototype. Assume none of your own login/access code will be used.

## What you *can't* do, even as a mission manager

Once a mission is published, its thresholds and content are frozen until
it's moved back to `draft`. This is deliberate, not a permissions
oversight: editing a live mission's grading criteria retroactively changes
what an already-graded attempt actually meant — a student who passed
yesterday under one threshold shouldn't silently fail it in retrospect
because someone tightened the bar today. If your mission needs a real
tuning change after launch, that's a conversation with staff, not something
you (or staff, for that matter) do live against a published mission.

## Where to look if you want the technical detail

- `backend/app/services/missions/operate/` — the SatKit port's actual pure
  functions (telemetry, commands, scoring), as a worked example of "logic
  in, framework out."
- `backend/app/models/missions/mission.py` — the shapes every mission
  fits into (`Mission`, `MissionVariant`, `MissionAttempt`): template vs.
  instance, same split as courses/enrollments.
- `backend/app/schemas/missions_proposals.py` and
  `backend/app/routers/missions/proposals.py` — the submission pipeline
  itself, if you want to see exactly what a proposal record looks like.
