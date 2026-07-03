"""Schnelltest: Beweist dass think=True jetzt Think-Bloecke erzeugt
und _filter_think_stream sie korrekt filtert."""
from __future__ import annotations

import asyncio
import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]


async def main() -> None:
    import ollama
    from halle_gehirn.config import get_settings

    settings = get_settings()
    client = ollama.Client(host=settings.ollama_url)
    model = settings.llm_model

    print(f"Ollama: {settings.ollama_url}, Modell: {model}")
    print(f"num_predict: {settings.gen_num_predict}")
    print()

    # 1. Raw-Call MIT think=True — beweist dass Think-Block kommt
    print("=== 1. Raw-Call mit think=True ===")
    t0 = time.time()
    resp = client.chat(
        model=model,
        messages=[{"role": "user", "content": "Was ist 2+2? Antworte kurz."}],
        think=True,
        options={"num_predict": 256, "temperature": 0.0},
    )
    t1 = time.time()
    content = resp["message"]["content"]
    has_think = "<think>" in content
    print(f"<think>-Block vorhanden: {has_think}")
    if has_think:
        think_end = content.find("</think>")
        think_part = content[content.find("<think>")+7:think_end]
        after = content[think_end+8:].strip()
        print(f"Think-Inhalt: '{think_part[:200].strip()}'")
        print(f"Sichtbare Antwort: '{after}'")
    else:
        print(f"Antwort: '{content[:200]}'")
    print(f"Dauer: {t1-t0:.1f}s")

    # 2. Streaming mit _filter_think_stream — beweist Filterung
    print("\n=== 2. Streaming mit _filter_think_stream ===")
    from halle_gehirn.generator.ollama_client import _filter_think_stream

    queue: asyncio.Queue[str | BaseException | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _stream() -> None:
        try:
            for chunk in client.chat(
                model=model,
                messages=[
                    {"role": "user",
                     "content": "Erklaere in 2 Saetzen was Python ist."},
                ],
                stream=True,
                think=True,
                options={"num_predict": 512, "temperature": 0.0},
            ):
                token = chunk.get("message", {}).get("content", "")
                if token:
                    loop.call_soon_threadsafe(queue.put_nowait, token)
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    t0 = time.time()
    loop.run_in_executor(None, _stream)

    visible_tokens: list[str] = []
    think_leaked = False
    async for token in _filter_think_stream(queue):
        visible_tokens.append(token)
        if "<think>" in token or "</think>" in token:
            think_leaked = True

    t1 = time.time()
    visible_text = "".join(visible_tokens)
    print(f"Sichtbare Tokens: {len(visible_tokens)}")
    print(f"<think>-Leak: {'JA - FEHLER!' if think_leaked else 'NEIN (korrekt)'}")
    print(f"Sichtbare Antwort: '{visible_text[:300]}'")
    print(f"Antwort leer: {not visible_text.strip()}")
    print(f"Dauer: {t1-t0:.1f}s")

    # Zusammenfassung
    print("\n=== ERGEBNIS ===")
    if has_think and not think_leaked and visible_text.strip():
        print("[PASS] think=True erzeugt Think-Bloecke")
        print("[PASS] _filter_think_stream filtert sie korrekt")
        print("[PASS] Sichtbare Antwort ist nicht leer")
    else:
        if not has_think:
            print("[FAIL] think=True erzeugt KEINEN Think-Block")
        if think_leaked:
            print("[FAIL] Think-Inhalt im sichtbaren Output!")
        if not visible_text.strip():
            print("[FAIL] Sichtbare Antwort ist leer!")


if __name__ == "__main__":
    asyncio.run(main())
