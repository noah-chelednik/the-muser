"""Pluggable audio engines for The Muser Studio.

Every tool (generation models, stem splitters, denoisers, mastering, MIDI
transcription, effects) is described by an :class:`~.registry.EngineSpec` with
capability tags, licence facts, hardware needs, install recipe and a health
check. :mod:`.selector` picks the best installed engine for a job and
:mod:`.installer` performs one-click installs into the Studio's own venv.
"""

from .errors import FriendlyError, friendly_message  # noqa: F401
