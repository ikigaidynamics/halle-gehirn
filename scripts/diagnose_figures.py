"""Diagnose: Was liefert Docling Serve fuer Abbildungen?

Sendet die Porsch-PDF an Docling Serve und prueft, ob 'pictures'
im JSON vorhanden sind, wie viele, und ob sie data-URIs enthalten.
"""
import httpx
import json
import sys
from pathlib import Path

SERVE_URL = "http://141.43.76.21:5001"
PDF_PATH = Path(__file__).resolve().parents[1] / "data" / "manual" / "abschlussarbeiten" / "Masterarbeit_Ronny_Porsch.pdf"


def main() -> None:
    if not PDF_PATH.exists():
        print(f"FEHLER: {PDF_PATH} nicht gefunden")
        sys.exit(1)

    print(f"PDF:    {PDF_PATH.name} ({PDF_PATH.stat().st_size / 1024:.0f} KB)")
    print(f"Serve:  {SERVE_URL}")
    print()

    # 1. Request an Docling Serve (identisch zum Produktionscode)
    print("--- Request an Docling Serve ---")
    with httpx.Client(timeout=httpx.Timeout(600.0)) as client, PDF_PATH.open("rb") as f:
        resp = client.post(
            f"{SERVE_URL}/v1/convert/file",
            files=[("files", (PDF_PATH.name, f, "application/octet-stream"))],
            data={
                "to_formats": ["md", "json"],
                "do_ocr": "true",
                "table_mode": "accurate",
                "image_export_mode": "embedded",
                "include_images": "true",
                "md_page_break_placeholder": "<!-- PAGE_BREAK -->",
            },
        )
    resp.raise_for_status()
    payload = resp.json()

    status = payload.get("status", "")
    print(f"  Status: {status}")
    print(f"  Processing time: {payload.get('processing_time', '?')}")
    print()

    # 2. JSON-Content inspizieren
    doc = payload.get("document", {})
    jc = doc.get("json_content") or {}

    # Top-level keys
    print(f"--- json_content Top-Level Keys ---")
    for key in sorted(jc.keys()):
        val = jc[key]
        if isinstance(val, list):
            print(f"  {key}: list[{len(val)}]")
        elif isinstance(val, dict):
            print(f"  {key}: dict[{len(val)} keys]")
        else:
            print(f"  {key}: {type(val).__name__} = {str(val)[:80]}")
    print()

    # 3. Pictures analysieren
    pictures = jc.get("pictures", [])
    print(f"--- Pictures: {len(pictures)} ---")

    if not pictures:
        print("  KEINE pictures im JSON! Docling Serve liefert keine Bilder.")
        print()
        # Markdown auf Data-URIs pruefen
        md = doc.get("md_content") or ""
        data_uri_count = md.count("data:image")
        print(f"  Data-URIs im Markdown: {data_uri_count}")
        if data_uri_count > 0:
            print("  => Bilder sind im Markdown eingebettet, aber NICHT in json_content.pictures!")
    else:
        for idx, pic in enumerate(pictures[:10]):
            uri = (pic.get("image") or {}).get("uri", "")
            prov = pic.get("prov", [])
            page = prov[0].get("page_no") if prov else None
            captions = pic.get("captions", [])
            has_data = uri.startswith("data:image")
            uri_len = len(uri)
            print(f"  [{idx}] page={page}  has_data_uri={has_data}  uri_len={uri_len}  captions={len(captions)}")

        if len(pictures) > 10:
            print(f"  ... und {len(pictures) - 10} weitere")
    print()

    # 4. Response-Payload-Schluessel auf oberster Ebene
    print(f"--- Payload Top-Level Keys ---")
    for key in sorted(payload.keys()):
        val = payload[key]
        if isinstance(val, (dict, list)):
            print(f"  {key}: {type(val).__name__}[{len(val)}]")
        else:
            print(f"  {key}: {str(val)[:100]}")
    print()

    # 5. Serve API-Info holen
    try:
        info = httpx.get(f"{SERVE_URL}/health", timeout=5.0)
        print(f"--- Serve Health ---")
        print(f"  Status: {info.status_code}")
        print(f"  Body: {info.text[:200]}")
    except Exception as e:
        print(f"  Health-Check fehlgeschlagen: {e}")

    print()
    print("FERTIG.")


if __name__ == "__main__":
    main()
