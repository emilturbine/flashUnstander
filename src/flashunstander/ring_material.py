"""Stable, per-conversation ring structures for the GPU renderer."""
from dataclasses import dataclass
from functools import lru_cache
from random import Random

from .cosmic import ring_for_conversation


@dataclass(frozen=True)
class RingProfile:
    inner: float
    outer: float
    bands: int
    gaps: int
    seed: int
    reflectivity: float

    @property
    def extent(self):
        return self.outer + .045


@lru_cache(maxsize=128)
def ring_profile_for_conversation(conversation_id):
    if ring_for_conversation(conversation_id) is None:
        return None
    rng = Random(f"{conversation_id}:ring-structure")
    inner = rng.uniform(1.15, 1.46)
    width = rng.uniform(.36, .98)
    return RingProfile(
        inner=inner,
        outer=inner + width,
        bands=rng.randint(3, 8),
        gaps=rng.randint(1, 3),
        seed=rng.randrange(1, 4096),
        reflectivity=rng.uniform(.42, .86),
    )
