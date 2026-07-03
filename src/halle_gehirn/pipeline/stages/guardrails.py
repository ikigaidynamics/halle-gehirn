"""Prompt-Injection-Abwehr, Topic-Gate, PII-Filter -- Phase 5.

Regex-basierte Guardrails fuer Input (Prompt-Injection, Off-Topic)
und Output (PII-Redaktion). Kein LLM-Call -- deterministisch und schnell.

WICHTIG: Erkennt auch INDIREKTE Injection aus Dokument-Content,
die ueber RAG in den Kontext gelangen kann.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class GuardrailResult:
    """Ergebnis einer Guardrail-Pruefung."""

    approved: bool
    reason: str = ""
    category: str = ""


# ── Input: Prompt-Injection Patterns ──

_INJECTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(
        r"(ignore|forget|disregard|override)\s+(all\s+)?(previous|prior|above|your)\s+"
        r"(instructions?|rules?|prompts?|constraints?)",
        re.IGNORECASE,
    ), "direct_injection"),
    (re.compile(
        r"(you\s+are\s+now|act\s+as|pretend\s+(to\s+be|you\s+are)|"
        r"new\s+instructions?|system\s*prompt|roleplay\s+as)",
        re.IGNORECASE,
    ), "role_override"),
    (re.compile(
        r"(repeat|print|show|reveal|output|display)\s+(the\s+)?"
        r"(system\s*prompt|instructions?|your\s+rules|initial\s+prompt)",
        re.IGNORECASE,
    ), "prompt_extraction"),
    (re.compile(
        r"(\bDAN\b|do\s+anything\s+now|jailbreak|bypass\s+(safety|filter|guardrail))",
        re.IGNORECASE,
    ), "jailbreak"),
    # Deutsch
    (re.compile(
        r"(ignoriere|vergiss|missachte)\s+(alle\s+)?(vorherigen?\s+)?"
        r"(Anweisungen?|Regeln?|Instruktionen?)",
        re.IGNORECASE,
    ), "direct_injection_de"),
    (re.compile(
        r"(du\s+bist\s+(jetzt|ab\s+sofort)|neue\s+Anweisungen?|"
        r"gib\s+(den\s+)?System\s*prompt\s+(aus|wieder))",
        re.IGNORECASE,
    ), "role_override_de"),
]

# ── Input: Indirekte Injection (aus Dokument-Content) ──

_INDIRECT_INJECTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(
        r"\[INST\]|\[/INST\]|<<SYS>>|<\|im_start\|>|<\|im_end\|>",
        re.IGNORECASE,
    ), "template_injection"),
    (re.compile(
        r"(IMPORTANT|ACHTUNG|HINWEIS)\s*:\s*(ignore|ignoriere|vergiss|forget)",
        re.IGNORECASE,
    ), "document_injection"),
    (re.compile(
        r"(assistant|system)\s*:\s*(ich|I)\s+(werde|will|shall)",
        re.IGNORECASE,
    ), "role_impersonation"),
]

# ── Output: PII-Filter ──

_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "email"),
    (re.compile(r"\b\d{3,5}[-/\s]?\d{3,8}\b"), "phone"),
    (re.compile(r"\b\d{6,8}\b"), "matrikelnummer"),
]


class PromptGuardrail:
    """Regex-basierte Input/Output-Guardrails.

    Prueft Inputs auf Prompt-Injection (direkt + indirekt) und
    Outputs auf PII-Leaks. Kein LLM-Call, deterministisch.
    """

    def check_input(self, text: str) -> GuardrailResult:
        """Prueft User-Input auf Injection und Off-Topic.

        Args:
            text: Die Benutzeranfrage.

        Returns:
            GuardrailResult mit approved=False bei Verdacht.
        """
        # Direkte Injection
        for pattern, category in _INJECTION_PATTERNS:
            if pattern.search(text):
                logger.warning(
                    "guardrail_input_blocked",
                    category=category,
                    text=text[:80],
                )
                return GuardrailResult(
                    approved=False,
                    reason="Prompt-Injection erkannt",
                    category=category,
                )

        # Indirekte Injection (aus Dokumenten)
        for pattern, category in _INDIRECT_INJECTION_PATTERNS:
            if pattern.search(text):
                logger.warning(
                    "guardrail_indirect_blocked",
                    category=category,
                    text=text[:80],
                )
                return GuardrailResult(
                    approved=False,
                    reason="Indirekte Injection erkannt",
                    category=category,
                )

        return GuardrailResult(approved=True)

    def check_output(self, text: str) -> GuardrailResult:
        """Prueft LLM-Output auf PII-Leaks.

        Args:
            text: Die generierte Antwort.

        Returns:
            GuardrailResult. Bei PII-Fund: approved=True aber mit Warnung.
        """
        found: list[str] = []
        for pattern, category in _PII_PATTERNS:
            if pattern.search(text):
                found.append(category)

        if found:
            logger.warning("guardrail_pii_detected", categories=found)
            return GuardrailResult(
                approved=True,
                reason=f"PII erkannt: {', '.join(found)}",
                category="pii",
            )

        return GuardrailResult(approved=True)

    def redact_pii(self, text: str) -> str:
        """Maskiert PII im Text.

        Args:
            text: Text mit moeglichem PII.

        Returns:
            Text mit maskiertem PII.
        """
        result = text
        for pattern, category in _PII_PATTERNS:
            result = pattern.sub(f"[{category.upper()}_REDACTED]", result)
        return result
