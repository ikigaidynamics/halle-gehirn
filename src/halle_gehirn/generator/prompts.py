"""SYSTEM_PROMPT_DE, Refusal, Few-Shot, Citation -- Phase 5.

Zentrale Prompt-Templates fuer die Generierung. Persona: Jarvis --
praezise, sachlich, belegt jede Aussage mit Quellen-IDs [S1]/[S2],
weist Fehlendes offen aus statt zu raten. Anti-Halluzination explizit.
"""
from __future__ import annotations

from typing import Any

SYSTEM_PROMPT_DE = """\
Du bist Jarvis, der KI-Assistent des Lehrstuhls fuer KI-gestuetzte \
Automatisierungstechnik (BTU Cottbus-Senftenberg, Prof. Berger).

Regeln:
1. Antworte AUSSCHLIESSLICH auf Basis der bereitgestellten Quellen. \
Erfinde NIEMALS Fakten, Zahlen, Details oder Quellen. \
Jeder einzelne Satz muss sich direkt aus dem Quellentext ableiten lassen.
2. Belege JEDE Aussage mit einer Quellen-ID: [S1], [S2] usw. \
Saetze ohne Quellenbeleg sind VERBOTEN. \
Schreibe KEINEN Satz, den du nicht mit einem konkreten Textabschnitt \
aus den Quellen belegen kannst.
3. Wenn die Quellen eine Frage nicht oder nur teilweise beantworten, \
sage das offen: "Dazu liegen mir keine ausreichenden Belege vor." \
Erfinde NICHTS, rate NICHT, schliesse NICHT ueber den Quelleninhalt hinaus.
4. Antworte auf Deutsch, praezise und sachlich.
5. Ziellaenge: 3-6 Saetze. Lieber kuerzer und korrekt als laenger und \
unbelegt. Nur bei komplexen Fragen mit vielen belegbaren Fakten mehr.
6. Vermeide Wiederholungen, Fuellwoerter und allgemeine Einleitungen. \
Keine Aussagen wie "spielt eine zentrale Rolle" oder "wird in \
verschiedenen Bereichen eingesetzt" ohne konkreten Quellenbeleg.
7. Nenne am Ende kurz die verwendeten Quellen mit Titel und — falls in \
der Quelle angegeben — Seite und Kapitel (z.B. "S. 42, Kap. 3.2").
8. Verwende NUR URLs, die in den Quellen stehen. Erfinde keine Links.
9. Paraphrasiere den Quelleninhalt eng. Fuege KEIN Weltwissen, keine \
Interpretationen und keine Schlussfolgerungen hinzu, die nicht \
explizit in den Quellen stehen."""

REFUSAL_TEMPLATE_DE = """\
Zu dieser Frage liegen mir leider keine ausreichend belegten \
Informationen vor. Ich moechte keine unbelegten Aussagen treffen.

Bitte wenden Sie sich an den Lehrstuhl: {contact_url}"""

HEDGE_PREFIX_DE = """\
Hinweis: Die verfuegbaren Quellen decken diese Frage nur teilweise ab. \
Die folgende Antwort stuetzt sich auf begrenzte Belege:

"""

# Few-Shot-Beispiele fuer konsistente Citation-Nutzung
FEW_SHOT_EXAMPLES: list[dict[str, str]] = [
    {
        "role": "user",
        "content": (
            "Quellen:\n"
            "[S1] UR10e Datenblatt\n"
            "Der UR10e hat eine Nutzlast von 10 kg und eine Reichweite "
            "von 1300 mm.\n\n"
            "[S2] Sicherheitskonzept Modellfabrik\n"
            "Die Sicherheitszone um kollaborative Roboter betraegt "
            "mindestens 500 mm.\n\n"
            "Frage: Welche Nutzlast hat der UR10e?"
        ),
    },
    {
        "role": "assistant",
        "content": (
            "Der UR10e ist ein kollaborativer Roboterarm mit einer "
            "Nutzlast von 10 kg [S1]. Seine Reichweite betraegt "
            "1300 mm [S1]. Beim Betrieb ist eine Sicherheitszone von "
            "mindestens 500 mm einzuhalten [S2].\n\n"
            "Quellen: [S1] UR10e Datenblatt, [S2] Sicherheitskonzept "
            "Modellfabrik"
        ),
    },
    {
        "role": "user",
        "content": (
            "Quellen:\n"
            "[S1] MES-Dokumentation\n"
            "Das MES-System protokolliert Produktionsdaten in Echtzeit.\n\n"
            "Frage: Wie hoch ist der Stromverbrauch der Anlage?"
        ),
    },
    {
        "role": "assistant",
        "content": (
            "Dazu liegen mir keine ausreichenden Belege vor. Die "
            "verfuegbaren Quellen enthalten keine Angaben zum "
            "Stromverbrauch der Anlage.\n\n"
            "Quellen: keine passenden Quellen verfuegbar"
        ),
    },
]

# Kontext-Formatierung fuer den User-Prompt
_CONTEXT_TEMPLATE = """\
Quellen:
{sources}

Frage: {query}"""

_SOURCE_TEMPLATE = "[S{idx}] {titel}{location}\n{text}"


def _format_location(payload: dict[str, Any]) -> str:
    """Baut den Fundstellen-Zusatz „ (S. 42 · Kap > Unterkap)" einer Quelle.

    Seite und Breadcrumb stammen aus dem Qdrant-Payload (WP3/WP1) und
    erlauben dem LLM praezise Fundstellen-Angaben in der Antwort.
    """
    parts: list[str] = []
    page = payload.get("page")
    if page is not None:
        parts.append(f"S. {page}")
    breadcrumb = payload.get("breadcrumb")
    if breadcrumb:
        parts.append(str(breadcrumb))
    if not parts:
        return ""
    return " (" + " · ".join(parts) + ")"


def format_context(hits: list[Any]) -> str:
    """Formatiert RetrievalHits als nummerierten Quellen-Block.

    Jede Quelle traegt — falls vorhanden — Seite und Kapitel-Breadcrumb,
    damit das LLM Fundstellen benennen kann. Citation-Format bleibt
    ``[S1]`` (Vorgabe des CitationValidators).

    Args:
        hits: Liste von RetrievalHit-Objekten mit payload.

    Returns:
        Formatierter Quellen-Text mit [S1], [S2] etc.
    """
    parts: list[str] = []
    for i, hit in enumerate(hits, start=1):
        payload = getattr(hit, "payload", {}) or {}
        titel = payload.get("titel", "Unbekannt")
        text = payload.get("text", "")
        parts.append(_SOURCE_TEMPLATE.format(
            idx=i,
            titel=titel,
            location=_format_location(payload),
            text=text,
        ))
    return "\n\n".join(parts)


def build_messages(
    query: str,
    hits: list[Any],
    memory_messages: list[dict[str, str]] | None = None,
    confidence: str = "gruen",
    contact_url: str = "",
) -> list[dict[str, str]]:
    """Baut die Chat-Messages fuer den LLM-Aufruf.

    Integriert System-Prompt, Few-Shot-Beispiele, Conversation-History,
    Kontext und Query. Bei confidence=rot wird direkt ein Refusal
    zurueckgegeben (kein LLM-Call noetig).

    Args:
        query: Die Benutzeranfrage.
        hits: RetrievalHit-Objekte als Kontext.
        memory_messages: Optionale Conversation-History.
        confidence: Ampelstufe ('gruen'/'gelb'/'rot').
        contact_url: Kontakt-URL fuer Refusal.

    Returns:
        Liste von Message-Dicts (role/content).
    """
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT_DE},
    ]

    # Few-Shot-Beispiele einfuegen
    messages.extend(FEW_SHOT_EXAMPLES)

    # Conversation-History einfuegen
    if memory_messages:
        messages.extend(memory_messages)

    # Refusal bei rot
    if confidence == "rot" or not hits:
        refusal = REFUSAL_TEMPLATE_DE.format(contact_url=contact_url)
        messages.append({"role": "user", "content": query})
        messages.append({"role": "assistant", "content": refusal})
        return messages

    # Kontext + Query
    context_text = format_context(hits)
    user_content = _CONTEXT_TEMPLATE.format(
        sources=context_text,
        query=query,
    )

    # Hedge bei gelb
    if confidence == "gelb":
        user_content = HEDGE_PREFIX_DE + user_content

    messages.append({"role": "user", "content": user_content})
    return messages
