"""Live games domain (Live Games Phase 2C) — a Kahoot-style synchronous
multiplayer quiz, standalone from `lms.courses` and `missions` (own
top-level surface, D5).

- `games` / `game_questions` — the authored template (8-3)
- `game_session_assignments` / `game_session_questions` — a template
  attached to one delivery session, with its own editable snapshot of the
  question list (8-4)
- `game_runs` / `game_participants` / `game_answers` — one live play-through
  and everyone/everything in it (8-6)

Everything keys on `users`, same as `lms`/`missions` — `MERGE_FK_REGISTRY`
is untouched.
"""

from app.models.games.game import Game, GameQuestion

__all__ = ["Game", "GameQuestion"]
