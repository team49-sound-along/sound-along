"""All the word cards an uploaded English passage gets: pictures for everyday nouns (word_pictures) and definitions for its harder words
(word_definitions). The same function is used by the local runner and the Lambda."""
from __future__ import annotations

from typing import Any, Callable, Optional

from word_definitions import definition_cards
from word_pictures import word_picture_cards


def word_cards(
    passage_id: str, text: str, pictures: Callable[..., tuple[dict[str, Any], dict[str, bytes]]] = word_picture_cards,
    definitions: Callable[..., dict[str, dict[str, Any]]] = definition_cards, existing: Optional[dict[str, dict[str, Any]]] = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, bytes]]:
    """(cards, picture files). A word with both gets one card with its picture and its definition. Each part fails alone: no pictures still gives
    definitions and the other way round."""
    try:
        cards, images = pictures(passage_id, text, existing=existing)
    except Exception:  # noqa: BLE001 (word pictures are optional)
        cards, images = {}, {}
    merged = {**(existing or {}), **cards}
    try:
        defined = definitions(text, existing=merged)
    except Exception:  # noqa: BLE001
        defined = {}
    return {**cards, **defined}, images
