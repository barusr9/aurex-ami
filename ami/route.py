"""Model routing (S6): send the easy turns to a cheaper model.

Every turn used to pay the same per-token rate. A policy lookup ("what's
your return policy?") and a multi-tool account action are not the same
difficulty, so they should not cost the same.

The signal is deliberately cheap — it runs before the model does, so it
cannot itself be a model call. Two things decide the tier:

  - the PUBLIC/PRIVATE split we already compute for auth. A PUBLIC question
    (generic policy/info) is the easy case; a PRIVATE one touches an account
    and usually needs tools and care.
  - a short difficulty heuristic for the PUBLIC case, so a long or clearly
    multi-part public question still gets the strong model.

Routing is OFF by default: with no cheap tier configured, every turn uses
config.MODEL exactly as before. Configure MODEL_CHEAP / MODEL_STRONG to
turn it on. This keeps the change safe to ship before it is measured.
"""

from ami.config import config
from ami.query_classifier import classify_query

# A PUBLIC question longer than this (characters) is treated as hard enough
# to deserve the strong model — a crude but effective "this isn't a one-liner"
# signal that needs no model call.
_LONG_PUBLIC_CHARS = 200

# Words that mark a public question as genuinely involved even when short.
_HARD_MARKERS = ("compare", "difference between", "step by step", "why",
                 "explain", "vs ", "versus", "walk me through")


def _strong():
    """The capable model: an explicit strong tier, else the default."""
    return config.MODEL_STRONG or config.MODEL


def _cheap():
    """The cheap tier, or "" if none configured (routing disabled)."""
    return config.MODEL_CHEAP


def pick_model(text, query_type=None):
    """Choose the model for this turn's text.

    query_type: pass a precomputed "PUBLIC"/"PRIVATE" to avoid reclassifying;
                otherwise it is derived here.

    Returns a model name. With no cheap tier set, always returns the strong/
    default model — i.e. current behaviour, unchanged.
    """
    cheap = _cheap()
    if not cheap:
        return _strong()                      # routing disabled -> no change

    qt = query_type or classify_query(text or "")
    if qt == "PRIVATE":
        return _strong()                      # account work: keep the strong model

    # PUBLIC: cheap by default, but promote the clearly-involved ones.
    lowered = (text or "").lower()
    if len(text or "") > _LONG_PUBLIC_CHARS or any(m in lowered for m in _HARD_MARKERS):
        return _strong()
    return cheap
