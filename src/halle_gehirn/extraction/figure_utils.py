"""Figure-Extraktion und -Speicherung (Shared Helper).

Gemeinsamer Code fuer lokale und Serve-basierte Bild-Extraktion.
Bilder werden als PNG unter ``{figures_dir}/{source_hash}/`` gespeichert.
Pfade in FigureBlocks sind RELATIV zu ``figures_dir`` (host-portabel).
"""
from __future__ import annotations

import base64
import io
import re
from pathlib import Path
from typing import Any

import structlog

from halle_gehirn.config import Settings
from halle_gehirn.extraction.base import FigureBlock

logger = structlog.get_logger(__name__)

_DATA_URI_RE = re.compile(r"^data:[^;]+;base64,(.+)$", re.DOTALL)


def save_figures(
    images_with_meta: list[dict[str, Any]],
    source_hash: str,
    settings: Settings,
) -> list[FigureBlock]:
    """Speichert Bilder als PNG und erzeugt FigureBlocks.

    Gemeinsamer Helper fuer lokale und Serve-Extraktion (DRY).
    Jedes Dict in ``images_with_meta`` muss ``image_bytes`` (bytes)
    enthalten; ``page``, ``caption``, ``fig_index`` sind optional.

    Pfade werden RELATIV zu ``figures_dir`` gespeichert (host-portabel):
    ``{source_hash}/fig_{index:03d}.png``.

    Args:
        images_with_meta: Bild-Daten mit Metadaten.
        source_hash: Ersten 16 Zeichen des SHA256-Hashs der Quelldatei.
        settings: Settings-Instanz (fuer figures_dir).

    Returns:
        Liste von FigureBlock-Objekten mit relativen Pfaden.
    """
    if not images_with_meta:
        return []

    fig_dir = Path(settings.figures_dir) / source_hash
    fig_dir.mkdir(parents=True, exist_ok=True)

    figures: list[FigureBlock] = []
    for item in images_with_meta:
        idx = item.get("fig_index", 0)
        image_bytes = item.get("image_bytes")
        if not image_bytes:
            continue
        filename = f"fig_{idx:03d}.png"
        img_path = fig_dir / filename
        try:
            img_path.write_bytes(image_bytes)
        except Exception as exc:
            logger.warning(
                "figure_save_failed", index=idx, error=str(exc),
            )
            continue
        rel_path = f"{source_hash}/{filename}"
        figures.append(FigureBlock(
            image_path=rel_path,
            page=item.get("page"),
            caption=item.get("caption"),
            fig_index=idx,
        ))

    logger.info(
        "figures_saved",
        total=len(images_with_meta),
        saved=len(figures),
        directory=str(fig_dir),
    )
    return figures


def extract_figures_local(
    docling_doc: Any,
    source_hash: str,
    settings: Settings,
    get_page_number: Any = None,
) -> list[FigureBlock]:
    """Extrahiert Abbildungen aus dem lokalen Docling-Dokument.

    Konvertiert PIL-Images zu Bytes und delegiert an ``save_figures``.

    Args:
        docling_doc: Das konvertierte Docling-Dokument.
        source_hash: Hash der Quelldatei (fuer Verzeichnisname).
        settings: Settings-Instanz (fuer figures_dir).
        get_page_number: Callable zum Lesen der Seitennummer.

    Returns:
        Liste von FigureBlock-Objekten.
    """
    pictures = getattr(docling_doc, "pictures", [])
    if not pictures:
        return []

    items: list[dict[str, Any]] = []
    for idx, pic in enumerate(pictures):
        image = getattr(pic, "image", None)
        if image is None:
            continue
        buf = io.BytesIO()
        try:
            image.save(buf, format="PNG")
        except Exception as exc:
            logger.warning(
                "figure_pil_export_failed", index=idx, error=str(exc),
            )
            continue
        page_no = None
        if get_page_number is not None:
            page_no = get_page_number(pic)
        caption = getattr(pic, "caption", None)
        caption_str = str(caption).strip() if caption else None
        items.append({
            "image_bytes": buf.getvalue(),
            "page": page_no,
            "caption": caption_str,
            "fig_index": idx,
        })

    return save_figures(items, source_hash, settings)


def extract_figures_from_serve(
    jc: dict[str, Any],
    source_hash: str,
    settings: Settings,
    resolve_ref_text: Any = None,
) -> list[FigureBlock]:
    """Extrahiert Abbildungen aus der Docling-Serve json_content.

    Liest ``pictures`` mit ``image.uri`` (data-URI, Base64-encoded PNG),
    dekodiert und delegiert an ``save_figures``.

    Args:
        jc: Das ``json_content``-Dict aus der Serve-Response.
        source_hash: Hash der Quelldatei (fuer Verzeichnisname).
        settings: Settings-Instanz (fuer figures_dir).
        resolve_ref_text: Callable zum Aufloesen von $ref-Verweisen.

    Returns:
        Liste von FigureBlock-Objekten.
    """
    pictures = jc.get("pictures", [])
    if not pictures:
        return []

    items: list[dict[str, Any]] = []
    for idx, pic in enumerate(pictures):
        uri = (pic.get("image") or {}).get("uri", "")
        if not uri.startswith("data:"):
            continue
        image_bytes = _decode_data_uri(uri)
        if not image_bytes:
            logger.warning(
                "figure_decode_failed", index=idx, uri_len=len(uri),
            )
            continue
        prov = pic.get("prov", [])
        page_no = prov[0].get("page_no") if prov else None
        caption = _resolve_picture_caption(jc, pic, resolve_ref_text)
        items.append({
            "image_bytes": image_bytes,
            "page": page_no,
            "caption": caption,
            "fig_index": idx,
        })

    return save_figures(items, source_hash, settings)


def _decode_data_uri(uri: str) -> bytes | None:
    """Dekodiert eine ``data:image/...;base64,...`` URI zu Bytes."""
    match = _DATA_URI_RE.match(uri)
    if not match:
        return None
    try:
        return base64.b64decode(match.group(1))
    except Exception:
        return None


def _resolve_picture_caption(
    jc: dict[str, Any],
    pic: dict[str, Any],
    resolve_ref_text: Any = None,
) -> str | None:
    """Loest die Caption eines Pictures aus der Serve-Response auf."""
    captions = pic.get("captions", [])
    if not captions:
        return None
    ref = captions[0].get("$ref", "")
    if resolve_ref_text is not None:
        result: str | None = resolve_ref_text(jc, ref)
        return result
    return None
