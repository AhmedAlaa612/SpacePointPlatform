"""Live games — avatar presets (world-class rework, avatar/nickname picker).

Icon presets only, no "use my photo" — the operator's own call: a real
photo sitting next to a fake nickname would quietly undercut the whole
D9 pseudonymity guarantee (real name stays a staff-only reveal), even
though a photo isn't literally the name field. Kept as a small fixed set
so the frontend can map each key to one `lucide-react` icon it already
depends on, with no icon-library growth.
"""

AVATAR_PRESETS: frozenset[str] = frozenset({
    "rocket", "satellite", "telescope", "orbit", "star",
    "moon", "zap", "flame", "compass", "bot",
})
