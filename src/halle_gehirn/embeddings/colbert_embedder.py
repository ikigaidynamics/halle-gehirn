"""Optionaler ColBERT Late-Interaction-Embedder.

Nur aktiv wenn USE_COLBERT=true in der Konfiguration. Wird erst in
spaeterer Phase vollstaendig implementiert — aktuell Fehler bei Aufruf
ohne aktivierte Config.
"""
from __future__ import annotations

from halle_gehirn.config import Settings, get_settings


class ColBERTNotEnabledError(Exception):
    """ColBERT ist nicht aktiviert (USE_COLBERT=false)."""


class ColBERTEmbedder:
    """Optionaler ColBERT-Embedder fuer Late-Interaction-Reranking.

    Wird erst aktiviert wenn USE_COLBERT=true gesetzt ist.
    Vollstaendige Implementierung folgt in spaeterer Phase.

    Args:
        settings: Optionale Settings-Instanz.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        if not self._settings.use_colbert:
            return
        # ColBERT-Modell-Initialisierung (spaetere Phase)

    def embed(self, texts: list[str]) -> list[list[list[float]]]:
        """Erzeugt ColBERT-Multi-Vektoren.

        Args:
            texts: Liste von Texten.

        Returns:
            Liste von Multi-Vektoren (je Text eine Matrix).

        Raises:
            ColBERTNotEnabledError: USE_COLBERT ist false.
        """
        if not self._settings.use_colbert:
            raise ColBERTNotEnabledError(
                "ColBERT ist deaktiviert (USE_COLBERT=false). "
                "Setze USE_COLBERT=true in .env um ColBERT zu aktivieren."
            )
        raise NotImplementedError(
            "ColBERT-Embedding wird in einer spaeteren Phase implementiert."
        )
