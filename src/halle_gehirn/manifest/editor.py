"""Manifest-Editor: reine Funktionen fuer Bestandspflege.

Liest/schreibt ``data/manifest.yaml``, validiert Facetten gegen
``schema.py``-Enums und ``data/vokabular.yaml``. Keine UI-Abhaengigkeiten —
alle Funktionen sind ohne Streamlit testbar.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog
import yaml

from halle_gehirn.pipeline.ingest import (
    IngestError,
    ManifestEntry,
    VokabularValidationError,
    load_manifest,
    load_vokabular,
    validate_enums,
    validate_manifest_against_vokabular,
)
from halle_gehirn.vector_store.schema import (
    Bereich,
    DocType,
    Grad,
    Herkunft,
    Quelltyp,
    Status,
    Vertraulichkeit,
)

logger = structlog.get_logger(__name__)

_DATA_DIR = Path("data")
_MANIFEST_PATH = _DATA_DIR / "manifest.yaml"
_VOKABULAR_PATH = _DATA_DIR / "vokabular.yaml"
_MANUAL_DIR = _DATA_DIR / "manual"


# ────────────────────────── Enum-Labels ──────────────────────────

_ENUM_LABELS: dict[str, str] = {
    # Bereich
    "transfer": "Transfer",
    "forschung": "Forschung",
    "lehre": "Lehre",
    "infrastruktur": "Infrastruktur",
    # DocType
    "abschlussarbeit": "Abschlussarbeit",
    "promotion": "Promotion",
    "projektbericht": "Projektbericht",
    "anlagendoku": "Anlagendokumentation",
    "handbuch": "Handbuch",
    "flyer": "Flyer",
    "online_beitrag": "Online-Beitrag",
    "workshop_slides": "Workshop-Slides",
    "lehrbuch": "Lehrbuch",
    "experten_transkript": "Experten-Transkript",
    "video_transkript": "Video-Transkript",
    "zusammenfassung": "Zusammenfassung",
    "sonstiges": "Sonstiges",
    # Herkunft
    "lehrstuhl_at": "Lehrstuhl AT",
    "mdz": "MDZ",
    "edih": "EDIH",
    "btu": "BTU",
    "extern": "Extern",
    # Quelltyp
    "primaer": "Primär",
    "kuratiert": "Kuratiert",
    "synthetisch": "Synthetisch",
    # Vertraulichkeit
    "offen": "Offen",
    "intern": "Intern",
    "vertraulich": "Vertraulich",
    # Status
    "final": "Final",
    "in_arbeit": "In Arbeit",
    # Grad
    "bachelor": "Bachelor",
    "master": "Master",
}


# ────────────────────────── Choices ──────────────────────────


def load_vokabular_choices(
    vokabular_path: Path | None = None,
) -> dict[str, dict[str, str]]:
    """Liefert je Facette die erlaubten Werte als ``{slug: label}``-Dict.

    Enum-basierte Facetten (bereich, doc_type, herkunft, quelltyp,
    vertraulichkeit, status, grad) kommen aus ``schema.py`` mit
    menschenlesbaren Labels.
    Registry-basierte Facetten (thema, anlage, projekt, ansprechperson)
    kommen aus ``data/vokabular.yaml``.

    Args:
        vokabular_path: Optionaler Pfad zur vokabular.yaml.

    Returns:
        Dict mit Facetten-Name -> {slug: label}.
    """
    choices: dict[str, dict[str, str]] = {}

    # Enum-Facetten: slug -> menschenlesbares Label
    choices["bereich"] = {e.value: _ENUM_LABELS[e.value] for e in Bereich}
    choices["doc_type"] = {e.value: _ENUM_LABELS[e.value] for e in DocType}
    choices["herkunft"] = {e.value: _ENUM_LABELS[e.value] for e in Herkunft}
    choices["quelltyp"] = {e.value: _ENUM_LABELS[e.value] for e in Quelltyp}
    choices["vertraulichkeit"] = {
        e.value: _ENUM_LABELS[e.value] for e in Vertraulichkeit
    }
    choices["status"] = {e.value: _ENUM_LABELS[e.value] for e in Status}
    choices["grad"] = {e.value: _ENUM_LABELS[e.value] for e in Grad}

    # Registry-Facetten: slug -> menschenlesbares Label (aus YAML)
    vok_path = vokabular_path or _VOKABULAR_PATH
    if vok_path.exists():
        raw = yaml.safe_load(vok_path.read_text(encoding="utf-8"))
        for key in ("thema", "anlage", "projekt", "ansprechperson"):
            section = raw.get(key, {})
            choices[key] = dict(section) if section else {}
    else:
        for key in ("thema", "anlage", "projekt", "ansprechperson"):
            choices[key] = {}

    return choices


# ────────────────────────── Read ──────────────────────────


def load_manifest_entries(
    manifest_path: Path | None = None,
) -> list[ManifestEntry]:
    """Laedt alle Eintraege aus manifest.yaml.

    Args:
        manifest_path: Optionaler Pfad (Default: data/manifest.yaml).

    Returns:
        Liste von ManifestEntry-Objekten.
    """
    return load_manifest(manifest_path or _MANIFEST_PATH)


def list_manifest_entries(
    manifest_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Liefert Manifest-Eintraege als Dicts fuer tabellarische Anzeige.

    Zeigt menschenlesbare Labels statt roher Slugs.

    Args:
        manifest_path: Optionaler Pfad (Default: data/manifest.yaml).

    Returns:
        Liste von Dicts mit Anzeige-Feldern.
    """
    entries = load_manifest_entries(manifest_path)
    return [
        {
            "datei": e.datei,
            "titel": e.titel,
            "doc_type": _ENUM_LABELS.get(e.doc_type, e.doc_type),
            "bereich": ", ".join(
                _ENUM_LABELS.get(b, b) for b in e.bereich
            ),
            "thema": ", ".join(e.thema) if e.thema else "",
            "anlage": ", ".join(e.anlage) if e.anlage else "",
            "vertraulichkeit": _ENUM_LABELS.get(
                e.vertraulichkeit, e.vertraulichkeit
            ),
        }
        for e in entries
    ]


# ────────────────────────── Write ──────────────────────────


def save_manifest_entry(
    entry: ManifestEntry,
    manifest_path: Path | None = None,
) -> None:
    """Haengt einen neuen Eintrag an manifest.yaml an.

    Bestehende Eintraege und Kommentare bleiben erhalten.

    Args:
        entry: Der neue ManifestEntry.
        manifest_path: Optionaler Pfad (Default: data/manifest.yaml).
    """
    p = manifest_path or _MANIFEST_PATH
    yaml_block = _entry_to_yaml_text(entry)

    if p.exists():
        content = p.read_text(encoding="utf-8")
        if not content.endswith("\n"):
            content += "\n"
        content += "\n" + yaml_block
    else:
        content = (
            "# data/manifest.yaml — Kurations-Metadaten je Quelldokument.\n"
            "\ndokumente:\n" + yaml_block
        )

    p.write_text(content, encoding="utf-8")
    logger.info("manifest_entry_saved", datei=entry.datei, titel=entry.titel)


def _entry_to_yaml_text(entry: ManifestEntry) -> str:
    """Formatiert einen ManifestEntry als YAML-Text-Block.

    Erzeugt 2-Space-Indent, Flow-Style-Listen, Double-Quoted-Strings
    fuer datei/titel — passend zum bestehenden manifest.yaml-Format.
    """
    lines: list[str] = [
        f'  - datei: "{_escape_yaml_str(entry.datei)}"',
        f'    titel: "{_escape_yaml_str(entry.titel)}"',
        f"    doc_type: {entry.doc_type}",
    ]
    if entry.grad:
        lines.append(f"    grad: {entry.grad}")
    lines.append(f"    bereich: [{', '.join(entry.bereich)}]")
    if entry.thema:
        lines.append(f"    thema: [{', '.join(entry.thema)}]")
    if entry.anlage:
        lines.append(f"    anlage: [{', '.join(entry.anlage)}]")
    if entry.projekt:
        lines.append(f"    projekt: [{', '.join(entry.projekt)}]")
    if entry.ansprechperson:
        lines.append(f"    ansprechperson: [{', '.join(entry.ansprechperson)}]")
    if entry.jahr is not None:
        lines.append(f"    jahr: {entry.jahr}")
    lines.extend([
        f"    herkunft: {entry.herkunft}",
        f"    quelltyp: {entry.quelltyp}",
        f"    vertraulichkeit: {entry.vertraulichkeit}",
        f"    status: {entry.status}",
    ])
    return "\n".join(lines) + "\n"


def _escape_yaml_str(s: str) -> str:
    """Escaped Double-Quotes in YAML-Strings."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


# ────────────────────────── Delete ──────────────────────────


def delete_manifest_entry(
    datei: str,
    manifest_path: Path | None = None,
    delete_file: bool = False,
) -> bool:
    """Entfernt einen Eintrag aus manifest.yaml (text-basiert).

    Erhaelt Kommentare und Formatierung. Loescht optional auch die
    Datei aus data/manual/.

    Args:
        datei: Der Dateipfad des zu loeschenden Eintrags.
        manifest_path: Optionaler Pfad (Default: data/manifest.yaml).
        delete_file: Auch die physische Datei loeschen.

    Returns:
        True wenn Eintrag gefunden und geloescht wurde.
    """
    p = manifest_path or _MANIFEST_PATH
    if not p.exists():
        return False

    text = p.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    # Finde den Eintrag: Zeile mit '- datei: "..."' die unsere datei enthaelt
    entry_start = -1
    entry_end = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("- datei:") and datei in stripped:
            entry_start = i
            # Finde das Ende: naechster '- datei:' oder Ende der Datei
            for j in range(i + 1, len(lines)):
                sj = lines[j].strip()
                if sj.startswith("- datei:") or (
                    sj and not sj.startswith("#") and not lines[j][0].isspace()
                ):
                    entry_end = j
                    break
            if entry_end == -1:
                entry_end = len(lines)
            break

    if entry_start == -1:
        return False

    # Kommentare VOR dem Eintrag entfernen (gehoeren zum Eintrag)
    while entry_start > 0 and lines[entry_start - 1].strip().startswith("#"):
        entry_start -= 1

    # Leere Zeilen nach dem Eintrag aufraemen
    while entry_end < len(lines) and not lines[entry_end].strip():
        entry_end += 1

    new_lines = lines[:entry_start] + lines[entry_end:]
    p.write_text("".join(new_lines), encoding="utf-8")

    logger.info("manifest_entry_deleted", datei=datei)

    # Optionale Dateiloeschung
    if delete_file:
        file_path = _MANUAL_DIR / datei
        if file_path.exists():
            file_path.unlink()
            logger.info("file_deleted", path=str(file_path))

    return True


# ────────────────────────── Validate ──────────────────────────


def validate_entry(
    entry: ManifestEntry,
    vokabular_path: Path | None = None,
) -> list[str]:
    """Validiert einen ManifestEntry und gibt Fehler als Liste zurueck.

    Nutzt die bestehende Validierungslogik aus ``ingest.py``
    (Enum-Pruefung + Vokabular-Registry), wirft aber nicht,
    sondern sammelt Fehler fuer UI-Anzeige.

    Args:
        entry: Der zu pruefende Eintrag.
        vokabular_path: Optionaler Pfad zur vokabular.yaml.

    Returns:
        Liste von Fehler-Strings (leer = valide).
    """
    errors: list[str] = []

    # Pflichtfeld-Pruefung
    if not entry.datei:
        errors.append("'datei' ist ein Pflichtfeld.")
    if not entry.titel:
        errors.append("'titel' ist ein Pflichtfeld.")
    if not entry.doc_type:
        errors.append("'doc_type' ist ein Pflichtfeld.")
    if not entry.bereich:
        errors.append("'bereich' ist ein Pflichtfeld (mind. ein Wert).")
    if not entry.herkunft:
        errors.append("'herkunft' ist ein Pflichtfeld.")
    if not entry.vertraulichkeit:
        errors.append("'vertraulichkeit' ist ein Pflichtfeld.")

    if errors:
        return errors

    # Enum-Validierung (schema.py)
    try:
        validate_enums([entry])
    except IngestError as exc:
        for line in str(exc).splitlines():
            if line and not line.startswith("Enum-Validierung"):
                errors.append(line)

    # Vokabular-Validierung (vokabular.yaml)
    try:
        registry = load_vokabular(vokabular_path or _VOKABULAR_PATH)
        validate_manifest_against_vokabular([entry], registry)
    except VokabularValidationError as exc:
        for line in str(exc).splitlines():
            if line and not line.startswith("Vokabular-Validierung"):
                errors.append(line)
    except IngestError:
        errors.append("Vokabular konnte nicht geladen werden.")

    return errors


# ────────────────────────── Vokabular ──────────────────────────

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_REGISTRY_FACETTEN = ("thema", "anlage", "projekt", "ansprechperson")


def save_vokabular_entry(
    facet: str,
    slug: str,
    label: str,
    vokabular_path: Path | None = None,
) -> None:
    """Fuegt einen neuen Slug zur vokabular.yaml hinzu.

    Bestehende Eintraege und Kommentare bleiben erhalten (Texteinfuegung).

    Args:
        facet: Facetten-Name (thema, anlage, projekt, ansprechperson).
        slug: Neuer Slug (snake_case, z.B. 'neuer_roboter').
        label: Menschenlesbares Label (z.B. 'Neuer Roboter XY').
        vokabular_path: Optionaler Pfad zur vokabular.yaml.

    Raises:
        ValueError: Ungueltige Facette, Slug oder Duplikat.
    """
    if facet not in _REGISTRY_FACETTEN:
        raise ValueError(f"Unbekannte Facette: '{facet}'")
    if not _SLUG_RE.match(slug):
        raise ValueError(
            f"Ungültiger Slug: '{slug}' (nur a-z, 0-9, _ erlaubt, "
            f"muss mit Buchstabe beginnen)"
        )
    if not label.strip():
        raise ValueError("Label darf nicht leer sein.")

    p = vokabular_path or _VOKABULAR_PATH
    text = p.read_text(encoding="utf-8")

    # Duplikat-Pruefung
    raw = yaml.safe_load(text)
    if slug in (raw.get(facet) or {}):
        raise ValueError(f"Slug '{slug}' existiert bereits in '{facet}'.")

    # Einfuegepunkt: letzte indentierte Zeile der Sektion
    lines = text.splitlines(keepends=True)
    insert_idx = _find_section_end(lines, facet)
    new_line = f'  {slug}: "{label}"\n'
    lines.insert(insert_idx, new_line)

    p.write_text("".join(lines), encoding="utf-8")
    logger.info("vokabular_entry_saved", facet=facet, slug=slug, label=label)


def _find_section_end(lines: list[str], facet: str) -> int:
    """Findet den Einfuegepunkt nach dem letzten Eintrag einer Sektion."""
    section_found = False
    last_entry_idx = 0
    for i, line in enumerate(lines):
        if line.rstrip() == f"{facet}:":
            section_found = True
            last_entry_idx = i + 1
            continue
        if section_found:
            stripped = line.strip()
            # Naechster Top-Level-Key → Sektion endet
            if stripped and not stripped.startswith("#") and not line[0].isspace():
                break
            # Indentierter Eintrag mit Key: Value
            if line.startswith("  ") and ":" in line and not stripped.startswith("#"):
                last_entry_idx = i + 1
    return last_entry_idx


# ────────────────────────── File-Upload ──────────────────────────


def list_upload_sorten(manual_dir: Path | None = None) -> list[str]:
    """Listet verfuegbare Dokumentsorten (Unterverzeichnisse von data/manual/).

    Args:
        manual_dir: Optionaler Pfad (Default: data/manual).

    Returns:
        Sortierte Liste von Verzeichnisnamen.
    """
    base = manual_dir or _MANUAL_DIR
    if not base.exists():
        return []
    return sorted(d.name for d in base.iterdir() if d.is_dir())


def save_uploaded_file(
    file_data: bytes,
    filename: str,
    sorte: str,
    manual_dir: Path | None = None,
) -> Path:
    """Speichert eine hochgeladene Datei nach data/manual/<sorte>/.

    Args:
        file_data: Dateiinhalt als Bytes.
        filename: Originaler Dateiname.
        sorte: Zielverzeichnis (z.B. 'anlagen', 'transfer').
        manual_dir: Optionaler Basispfad (Default: data/manual).

    Returns:
        Pfad der gespeicherten Datei.

    Raises:
        FileExistsError: Datei existiert bereits.
        ValueError: Unbekannte Sorte.
    """
    base = manual_dir or _MANUAL_DIR
    target_dir = base / sorte
    if not target_dir.is_dir():
        raise ValueError(f"Unbekannte Sorte: '{sorte}'")

    target = target_dir / filename
    if target.exists():
        raise FileExistsError(f"Datei existiert bereits: {target}")

    target.write_bytes(file_data)
    logger.info("file_uploaded", path=str(target), size=len(file_data))
    return target
