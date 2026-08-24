from sqlalchemy.orm import Session

from backend import models


def normalize_text(value: str) -> str:
    return " ".join(value.split())


def resolve_anchor(response: models.AIResponse, selected_text: str, start_offset: int, end_offset: int) -> tuple[int, int]:
    response_text = response.response_text
    if start_offset < 0 or end_offset <= start_offset:
        raise ValueError("anchor offsets are invalid")
    if end_offset <= len(response_text):
        anchored = response_text[start_offset:end_offset]
        if anchored == selected_text or normalize_text(anchored) == normalize_text(selected_text):
            return start_offset, end_offset

    nearby_start = max(0, start_offset - 600)
    nearby_end = min(len(response_text), end_offset + 600)
    nearby_match = response_text.find(selected_text, nearby_start, nearby_end)
    if nearby_match != -1:
        return nearby_match, nearby_match + len(selected_text)

    best_match: tuple[int, int] | None = None
    search_from = 0
    while True:
        found = response_text.find(selected_text, search_from)
        if found == -1:
            break
        candidate = (found, found + len(selected_text))
        if best_match is None or abs(candidate[0] - start_offset) < abs(best_match[0] - start_offset):
            best_match = candidate
        search_from = found + 1
    if best_match is not None:
        return best_match

    raise ValueError("selected_text does not match response text at the provided offsets")


def validate_anchor(response: models.AIResponse, selected_text: str, start_offset: int, end_offset: int) -> None:
    resolve_anchor(response, selected_text, start_offset, end_offset)


def find_matching_thread(
    db: Session,
    *,
    response_id: str,
    selected_text: str,
    start_offset: int,
    end_offset: int,
) -> models.Thread | None:
    return (
        db.query(models.Thread)
        .filter(
            models.Thread.response_id == response_id,
            models.Thread.start_offset == start_offset,
            models.Thread.end_offset == end_offset,
            models.Thread.selected_text == selected_text,
        )
        .first()
    )
