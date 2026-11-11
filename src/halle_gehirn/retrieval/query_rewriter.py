"""Conversational Query Rewriting -- Phase 6.

Loest Pronomen und Kontextreferenzen in Follow-up-Fragen auf, um eine
eigenstaendige Suchanfrage zu erzeugen. Greift auf die Conversation-History
zu. FAIL-OPEN: bei Fehler/Timeout wird die Original-Query unveraendert
verwendet. Ein kaputter Rewriter darf NIE eine Anfrage blockieren.

Dreifache Think-Absicherung: /no_think-Prefix + think=False + _strip_think_tags()
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

import structlog

from halle_gehirn.config import Settings, get_settings
from halle_gehirn.generator.llm_client import get_llm_client

logger = structlog.get_logger(__name__)

# Pronomen-Signale: Referenzen auf vorherigen Kontext
_PRONOUN_RE = re.compile(
    r"\b(er|sie|es|ihn|ihm|ihr|ihnen|dessen|deren|"
    r"das|dies|diese|dieser|diesem|diesen|jene[rsmn]?|"
    r"dort|da|darueber|dazu|davon|dabei|damit|daran|darauf|"
    r"welche[rsmn]?|solche[rsmn]?)\b",
    re.IGNORECASE,
)

# Ellipse-Signale: Folgefragen ohne explizites Pronomen
_ELLIPSE_START_RE = re.compile(
    r"^\s*(und\b|auch\b|was ist mit\b|wie sieht es aus\b|"
    r"wie steht es um\b|gilt das\b|geht das\b)",
    re.IGNORECASE,
)
_ELLIPSE_WORDS_RE = re.compile(
    r"\b(ausserdem|ebenfalls|au(ss|ß)erdem|"
    r"der zweite|die zweite|das zweite|"
    r"der erste|die erste|das erste|"
    r"der dritte|die dritte|das dritte|"
    r"die andere[rsmn]?|der andere[rsmn]?|das andere)\b",
    re.IGNORECASE,
)

_MAX_LENGTH_FACTOR = 2
_MAX_ABSOLUTE_LEN = 500
_SHORT_QUERY_WORDS = 6

# Inhaltswörter: alles ab 4 Buchstaben, keine Stoppwörter
_CONTENT_WORD_RE = re.compile(r"\b[a-zäöüß]{4,}\b", re.IGNORECASE)

# Stoppwörter, die keine inhaltlichen Signale tragen
_STOP_WORDS: frozenset[str] = frozenset({
    "aber", "alle", "allem", "allen", "aller", "also", "andere", "anderem",
    "anderen", "anderer", "anderes", "auch", "bedeutet", "beide", "beiden",
    "beim", "bereits", "beschreibt", "bevor", "bitte", "dabei", "damit",
    "dann", "darf", "dass", "dazu", "dein", "deine", "deinem", "deinen",
    "deiner", "denn", "deren", "derer", "deshalb", "dessen", "dies",
    "diese", "dieselbe", "diesem", "diesen", "dieser", "doch", "dort",
    "drin", "eine", "einem", "einen", "einer", "einige", "einigen",
    "einiger", "einiges", "erst", "etwa", "etwas", "euch", "euer",
    "eure", "eurem", "euren", "eurer", "falls", "fuer", "gibt",
    "habe", "haben", "halt", "hast", "hier", "ihre", "ihrem",
    "ihren", "ihrer", "immer", "indem", "jede", "jedem", "jeden",
    "jeder", "jedes", "jedoch", "jene", "jenem", "jenen", "jener",
    "jenes", "kann", "kein", "keine", "keinem", "keinen", "keiner",
    "mehr", "mein", "meine", "meinem", "meinen", "meiner", "mich",
    "muss", "nach", "nein", "nicht", "noch", "oder", "ohne", "sein",
    "seine", "seinem", "seinen", "seiner", "seit", "sich", "sind",
    "soll", "sondern", "ueber", "unser", "unsere", "unserem", "unseren",
    "unserer", "unter", "viel", "viele", "vielen", "vielleicht", "voll",
    "waehrend", "wann", "warum", "weil", "welch", "welche", "welchem",
    "welchen", "welcher", "wenn", "werde", "werden", "wessen", "wird",
    "wohl", "wurde", "wurden", "zwischen",
})

# Maximale Anzahl neuer Inhaltswörter, die der Rewrite einführen darf
_MAX_NEW_CONTENT_WORDS = 4

_REWRITE_PROMPT = """\
/no_think
Du bist ein Query-Rewriter. Deine EINZIGE Aufgabe: Loese Pronomen und \
Verweise in der aktuellen Frage auf, damit sie eigenstaendig verstaendlich \
ist.

REGELN:
1. Loese NUR Pronomen und Verweise auf. Uebernimm KEINE Themen, \
Fachbegriffe oder Einschraenkungen aus dem Gespraechsverlauf, die in der \
neuen Frage nicht referenziert werden.
2. Wenn die Frage bereits eigenstaendig verstaendlich ist, gib sie \
UNVERAENDERT zurueck.
3. Behalte Eigennamen und Fachbegriffe aus der Frage EXAKT bei \
(UR10e, OPC UA, CP Factory, Zhili Wang, ...).
4. Fuege NICHTS hinzu, was nicht in der Frage oder im aufgeloesten \
Bezug steht. Kein Anreichern, kein Kontextualisieren.
5. Antworte NUR mit der umformulierten Frage, ohne Erklaerung.

Gespraechsverlauf:
{history}

Aktuelle Frage: {query}

Umformulierte Frage:"""


@dataclass
class RewriteResult:
    """Ergebnis der Query-Umschreibung."""

    original: str
    rewritten: str
    was_rewritten: bool


class QueryRewriter:
    """LLM-basierter Query-Rewriter fuer Konversationskontext.

    Zweistufiger Bypass:
    - Kein History (erster Turn) → immer Bypass.
    - Mit History → Rewrite wenn Pronomen- ODER Ellipse-Signale.
    - Im Zweifel: lieber rewriten (Call billig, Retrieval-Miss teuer).

    Args:
        settings: Optionale Settings-Instanz.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = get_llm_client(settings=self._settings)
        self._model = self._client.model

    async def rewrite(
        self,
        query: str,
        history: list[dict[str, str]],
    ) -> RewriteResult:
        """Schreibt eine Follow-up-Frage als eigenstaendige Suchanfrage um.

        Args:
            query: Die aktuelle Benutzeranfrage.
            history: Bisherige Conversation-Turns (role/content dicts).

        Returns:
            RewriteResult mit original, rewritten, was_rewritten.
        """
        if not _needs_rewrite(query, history):
            return RewriteResult(
                original=query, rewritten=query, was_rewritten=False,
            )

        try:
            rewritten = await self._call_llm(query, history)
            rewritten = self._validate(rewritten, query)
        except Exception as exc:
            logger.warning("query_rewrite_failed", error=str(exc))
            return RewriteResult(
                original=query, rewritten=query, was_rewritten=False,
            )

        was_rewritten = rewritten != query
        if was_rewritten:
            logger.info(
                "query_rewritten",
                original=query[:80],
                rewritten=rewritten[:80],
            )
        return RewriteResult(
            original=query, rewritten=rewritten, was_rewritten=was_rewritten,
        )

    async def _call_llm(
        self, query: str, history: list[dict[str, str]],
    ) -> str:
        """LLM-Aufruf zur Query-Umschreibung."""
        history_text = _format_history(history[-6:])
        prompt = _REWRITE_PROMPT.format(history=history_text, query=query)

        response = await asyncio.to_thread(
            self._client.chat,
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            think=False,
            options={"temperature": 0.0, "num_predict": 150},
        )
        content: str = response["message"]["content"].strip()
        return _strip_think_tags(content)

    def _validate(self, rewritten: str, original: str) -> str:
        """Validiert das Rewrite-Ergebnis. Faellt auf Original zurueck.

        Guards:
        1. Leer → Original.
        2. Laenge > 2x Original (bzw. 500 abs.) → Original.
        3. Mehr als _MAX_NEW_CONTENT_WORDS neue Inhaltswoerter → Original.
        4. Eigennamen aus Original fehlen im Rewrite → Original.
        """
        if not rewritten:
            logger.warning("query_rewrite_empty")
            return original

        # Längen-Guard (2x statt 3x)
        max_len = max(len(original) * _MAX_LENGTH_FACTOR, _MAX_ABSOLUTE_LEN)
        if len(rewritten) > max_len:
            logger.warning("query_rewrite_too_long", length=len(rewritten))
            return original

        # Content-Guard: neue Inhaltswörter zählen
        orig_words = _extract_content_words(original)
        rewrite_words = _extract_content_words(rewritten)
        new_words = rewrite_words - orig_words
        if len(new_words) > _MAX_NEW_CONTENT_WORDS:
            logger.warning(
                "query_rewrite_rejected",
                reason="too_many_new_words",
                new_words=sorted(new_words)[:8],
                count=len(new_words),
            )
            return original

        # Eigennamen-Guard: Grossgeschriebene Wörter aus Original müssen erhalten bleiben
        orig_names = _extract_proper_names(original)
        if orig_names:
            rewrite_lower = rewritten.lower()
            missing = [n for n in orig_names if n.lower() not in rewrite_lower]
            if missing:
                logger.warning(
                    "query_rewrite_rejected",
                    reason="names_missing",
                    missing=missing,
                )
                return original

        return rewritten


def _needs_rewrite(query: str, history: list[dict[str, str]]) -> bool:
    """Zweistufige Bypass-Entscheidung.

    - Kein History → immer False (nichts aufzuloesen).
    - Mit History → True wenn Pronomen/Ellipse-Signal oder kurze Frage.
    """
    if not history:
        return False

    # Pronomen-Signal
    if _PRONOUN_RE.search(query):
        return True

    # Ellipse: Anfang mit und/auch/was ist mit/...
    if _ELLIPSE_START_RE.search(query):
        return True

    # Ellipse: Woerter wie "der zweite", "die andere", "ebenfalls"
    if _ELLIPSE_WORDS_RE.search(query):
        return True

    # Kurze Frage mit History → im Zweifel rewriten
    return len(query.split()) < _SHORT_QUERY_WORDS


def _format_history(turns: list[dict[str, str]]) -> str:
    """Formatiert History-Turns als Text fuer den Prompt."""
    parts: list[str] = []
    for turn in turns:
        role = "Nutzer" if turn["role"] == "user" else "Assistent"
        parts.append(f"{role}: {turn['content'][:200]}")
    return "\n".join(parts)


def _extract_content_words(text: str) -> set[str]:
    """Extrahiert Inhaltswoerter (>=4 Buchstaben, keine Stoppwoerter)."""
    words = set(_CONTENT_WORD_RE.findall(text.lower()))
    return words - _STOP_WORDS


def _extract_proper_names(text: str) -> list[str]:
    """Extrahiert potenzielle Eigennamen (grossgeschriebene Woerter).

    Ignoriert Satzanfaenge (nach Punkt/Fragezeichen/Ausrufezeichen) und
    das allererste Wort im Text.
    """
    # Satzanfänge markieren: Positionen nach Satzzeichen+Leerzeichen
    sentence_start_positions: set[int] = {0}
    for m in re.finditer(r"[.!?]\s+", text):
        sentence_start_positions.add(m.end())

    names: list[str] = []
    for m in re.finditer(r"\b([A-ZÄÖÜ][a-zäöüß]{2,})\b", text):
        if m.start() not in sentence_start_positions:
            names.append(m.group(1))
    return names


from halle_gehirn.llm_utils import strip_think_tags as _strip_think_tags  # noqa: E402
