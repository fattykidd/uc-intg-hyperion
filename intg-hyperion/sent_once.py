"""
Keeps an entity from repeating itself to the Remote.

The framework's update() sends only the attributes that differ from the entity's own copy. Select and
media-player entities also carry lists (options, sources) that the Remote must receive in full, so they send
everything with ``force=True``. Every device change makes every entity refresh, so without this the Remote
was sent identical copies of those entities many times a second.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class SendsOnlyWhenChanged:
    """Mixin for entities that send all their attributes, but only when they differ from the last time."""

    _last_sent: dict[str, Any] | None = None

    def send_complete(self, attributes: dict[str, Any]) -> None:
        """Send every attribute (lists included), unless the Remote already has exactly this."""
        if attributes == self._last_sent:
            return
        self._last_sent = deepcopy(attributes)
        self.update(attributes, force=True)  # type: ignore[attr-defined]

    def forget_last_sent(self) -> None:
        """Send everything again next time, e.g. after the entity was unavailable."""
        self._last_sent = None
