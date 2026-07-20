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

import ollama
import structlog

from halle_gehirn.config import Settings, get_settings

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

_MAX_LENGTH_FACTOR = 3
_MAX_ABSOLUTE_LEN = 500
_SHORT_QUERY_WORDS = 6

_REWRITE_PROMPT = """\
/no_think
Du bist ein Query-Rewriter. Formuliere die Nutzerfrage in eine \
eigenstaendige, praezise Suchanfrage um. Loese Pronomen und Verweise \
mithilfe des Gespraechsverlaufs auf. Behalte Fachbegriffe und \
Eigennamen EXAKT bei (UR10e, OPC UA, CP Factory, ...). \
Erfinde nichts dazu. Antworte NUR mit der umformulierten Frage, \
ohne Erklaerung.

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
        self._client = ollama.Client(host=self._settings.ollama_url)
        self._model = self._settings.llm_model

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
        """Validiert das Rewrite-Ergebnis. Faellt auf Original zurueck."""
        if not rewritten:
            logger.warning("query_rewrite_empty")
            return original
        max_len = max(len(original) * _MAX_LENGTH_FACTOR, _MAX_ABSOLUTE_LEN)
        if len(rewritten) > max_len:
            logger.warning("query_rewrite_too_long", length=len(rewritten))
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


def _strip_think_tags(text: str) -> str:
    """Entfernt <think>-Bloecke (qwen3 dritte Verteidigungslinie)."""
    if "<think>" not in text:
        return text.strip()
    match = re.search(r"</think>\s*(.*)", text, flags=re.DOTALL)
    if match and match.group(1).strip():
        return match.group(1).strip()
    return text.strip()
