"""Google Slides: create, inspect, extend and fill presentations."""

import logging
from typing import Dict, List, Optional

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config
from ..text import clean_text

LAYOUTS = {
    "BLANK",
    "CAPTION_ONLY",
    "TITLE",
    "TITLE_AND_BODY",
    "TITLE_AND_TWO_COLUMNS",
    "TITLE_ONLY",
    "SECTION_HEADER",
    "SECTION_TITLE_AND_DESCRIPTION",
    "ONE_COLUMN_TEXT",
    "MAIN_POINT",
    "BIG_NUMBER",
}

EMU_PER_PIXEL = 9525  # 96 dpi
SLIDE_TEXT_LIMIT = 200


def _service(config: Config):
    return build("slides", "v1", credentials=get_creds(config))


def _slide_text(slide: dict) -> str:
    chunks: List[str] = []
    for element in slide.get("pageElements", []):
        shape = element.get("shape") or {}
        for run in (shape.get("text") or {}).get("textElements", []):
            content = clean_text(
                (run.get("textRun") or {}).get("content", ""), single_line=True
            )
            if content:
                chunks.append(content)
    return " / ".join(chunks)


def _count_occurrences(presentation: dict, keys: List[str]) -> Dict[str, int]:
    counts = {key: 0 for key in keys}
    for slide in presentation.get("slides", []):
        for element in slide.get("pageElements", []):
            shape = element.get("shape") or {}
            for run in (shape.get("text") or {}).get("textElements", []):
                content = (run.get("textRun") or {}).get("content", "")
                for key in keys:
                    if key:
                        counts[key] += content.count(key)
    return counts


def _emu(pixels: float) -> Dict[str, object]:
    return {"magnitude": int(round(float(pixels) * EMU_PER_PIXEL)), "unit": "EMU"}


def slides_create_handler(config: Config, logger: logging.Logger, title: str) -> str:
    try:
        presentation = _service(config).presentations().create(
            body={"title": title}
        ).execute()
        presentation_id = presentation.get("presentationId")
        return (
            f"Presentation created: {presentation.get('title')} "
            f"(ID: {presentation_id})\n"
            f"URL: https://docs.google.com/presentation/d/{presentation_id}/edit"
        )
    except Exception as e:
        return f"Error creating presentation: {str(e)}"


def slides_get_handler(
    config: Config, logger: logging.Logger, presentation_id: str
) -> str:
    try:
        presentation = (
            _service(config).presentations().get(presentationId=presentation_id).execute()
        )
        slides = presentation.get("slides", [])

        lines = [
            f"Presentation: {presentation.get('title')} (ID: {presentation_id})",
            f"Slides: {len(slides)}",
            "",
        ]
        for index, slide in enumerate(slides, start=1):
            text = _slide_text(slide)
            if len(text) > SLIDE_TEXT_LIMIT:
                text = text[:SLIDE_TEXT_LIMIT].rstrip() + "…"
            lines.append(f"{index}. [{slide.get('objectId')}] {text or '(no text)'}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error reading presentation: {str(e)}"


def slides_add_slide_handler(
    config: Config,
    logger: logging.Logger,
    presentation_id: str,
    layout: str = "TITLE_AND_BODY",
    insertion_index: Optional[int] = None,
) -> str:
    try:
        name = str(layout or "TITLE_AND_BODY").strip().upper()
        if name not in LAYOUTS:
            return (
                f"Error: unknown layout '{layout}'. "
                f"Valid layouts: {', '.join(sorted(LAYOUTS))}."
            )

        create_slide: Dict[str, object] = {
            "slideLayoutReference": {"predefinedLayout": name}
        }
        if insertion_index is not None:
            create_slide["insertionIndex"] = int(insertion_index)

        response = (
            _service(config)
            .presentations()
            .batchUpdate(
                presentationId=presentation_id,
                body={"requests": [{"createSlide": create_slide}]},
            )
            .execute()
        )
        reply = (response.get("replies") or [{}])[0].get("createSlide", {})
        return f"Slide added (ID: {reply.get('objectId')}) using layout {name}."
    except Exception as e:
        return f"Error adding slide: {str(e)}"


def slides_replace_text_handler(
    config: Config,
    logger: logging.Logger,
    presentation_id: str,
    replacements: Dict[str, str],
    confirm: bool = False,
) -> str:
    try:
        if not replacements:
            return "Error: replacements map is required."

        service = _service(config)

        if not confirm:
            presentation = (
                service.presentations().get(presentationId=presentation_id).execute()
            )
            counts = _count_occurrences(presentation, list(replacements))
            total = sum(counts.values())
            preview = "\n".join(
                f"  {key} → {value} ({counts[key]} occurrence(s))"
                for key, value in replacements.items()
            )
            return (
                "⚠️ CONFIRMATION REQUIRED\n\n"
                f"This will rewrite text in presentation {presentation_id} "
                f"({len(presentation.get('slides', []))} slides, {total} occurrence(s)).\n"
                f"{preview}\n\n"
                "To proceed, call again with confirm=True."
            )

        requests = [
            {
                "replaceAllText": {
                    "containsText": {"text": key, "matchCase": True},
                    "replaceText": str(value),
                }
            }
            for key, value in replacements.items()
        ]
        response = (
            service.presentations()
            .batchUpdate(presentationId=presentation_id, body={"requests": requests})
            .execute()
        )
        changed = sum(
            int((reply.get("replaceAllText") or {}).get("occurrencesChanged", 0))
            for reply in response.get("replies", [])
        )

        logger.info("Slides text replaced: %s keys=%s", presentation_id, len(replacements))
        return f"Replaced text in presentation {presentation_id}: {changed} occurrence(s)."
    except Exception as e:
        return f"Error replacing text in presentation: {str(e)}"


def slides_insert_image_handler(
    config: Config,
    logger: logging.Logger,
    presentation_id: str,
    slide_id: str,
    image_url: str,
    width: Optional[float] = None,
    height: Optional[float] = None,
    left: Optional[float] = None,
    top: Optional[float] = None,
) -> str:
    try:
        if not image_url or not str(image_url).startswith(("http://", "https://")):
            return "Error: image_url must be a public http(s) URL."

        element_properties: Dict[str, object] = {"pageObjectId": slide_id}

        size: Dict[str, object] = {}
        if width is not None:
            size["width"] = _emu(width)
        if height is not None:
            size["height"] = _emu(height)
        if size:
            element_properties["size"] = size

        if left is not None or top is not None:
            element_properties["transform"] = {
                "scaleX": 1,
                "scaleY": 1,
                "translateX": int(round(float(left or 0) * EMU_PER_PIXEL)),
                "translateY": int(round(float(top or 0) * EMU_PER_PIXEL)),
                "unit": "EMU",
            }

        response = (
            _service(config)
            .presentations()
            .batchUpdate(
                presentationId=presentation_id,
                body={
                    "requests": [
                        {
                            "createImage": {
                                "url": image_url,
                                "elementProperties": element_properties,
                            }
                        }
                    ]
                },
            )
            .execute()
        )
        reply = (response.get("replies") or [{}])[0].get("createImage", {})
        return f"Image inserted on slide {slide_id} (ID: {reply.get('objectId')})."
    except Exception as e:
        return f"Error inserting image: {str(e)}"


def delete_slide_handler(
    config: Config,
    logger: logging.Logger,
    presentation_id: str,
    slide_id: str,
    confirm: bool = False,
) -> str:
    try:
        if not presentation_id or not slide_id:
            return "Error: presentation_id and slide_id are required."

        service = _service(config)
        if not confirm:
            presentation = (
                service.presentations().get(presentationId=presentation_id).execute()
            )
            slides = presentation.get("slides", [])
            index = next(
                (
                    position
                    for position, slide in enumerate(slides, start=1)
                    if slide.get("objectId") == slide_id
                ),
                None,
            )
            if index is None:
                return f"Error: slide {slide_id} not found in this presentation."

            title = _slide_text(slides[index - 1])[:120] or "(no text)"
            return (
                "CONFIRMATION REQUIRED\n\n"
                f"Delete slide {index} of {len(slides)}: {title}\n"
                f"ID: {slide_id}\n\n"
                "Deletion cannot be undone from the API.\n"
                "Call again with confirm=true to proceed."
            )

        service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={"requests": [{"deleteObject": {"objectId": slide_id}}]},
        ).execute()
        logger.info("Deleted slide %s from %s", slide_id, presentation_id)
        return f"Slide {slide_id} deleted from presentation {presentation_id}."
    except Exception as e:
        return f"Error deleting slide: {str(e)}"

