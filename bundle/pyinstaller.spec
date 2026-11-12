# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Spec fuer das Halle-Gehirn Standalone-Bundle (onedir).

Build:  pyinstaller bundle/pyinstaller.spec
Entry:  src/halle_gehirn/bundle/entrypoint.py (Launcher: CWD + Caches + uvicorn)

Das Bundle enthaelt bewusst NICHT: docling, pymupdf4llm, ragas, datasets,
streamlit, playwright. Extraktion laeuft im Bundle-Betrieb ausschliesslich
ueber externes Docling Serve (DOCLING_SERVE_URL).
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []

# tiktoken findet Encodings (cl100k_base) nur ueber das Namespace-Paket
# tiktoken_ext + pkgutil.iter_modules -- im Gefrierbetrieb unzuverlaessig.
# Das Plugin-Modul wird explizit eingebunden; der Entry Point fuellt die
# Registry daraus direkt (kein pkgutil-Scan noetig).
hiddenimports += ["tiktoken_ext.openai_public"]

# Pakete mit Datendateien/Compiled-Extensionen vollstaendig sammeln.
# deps=False: sonst zieht collect_all die komplette METADATA-Abhaengigkeits-
# closure (pyarrow, scipy, pandas, babel, ...) mit ein.
for _pkg in (
    "fastembed",       # bringt onnxruntime-DLLs + Modell-Registry mit
    "trafilatura",     # mitgelieferte Settings/YAML-Dateien
    "tiktoken",        # vorkompilierte Ext + Regex-Dateien
    "qdrant_client",
    "pydantic",
    "pydantic_settings",
    "structlog",
    "opentelemetry.sdk",
    "opentelemetry.instrumentation.fastapi",
):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h

# uvicorn ladet Loops/Protocols/Workers dynamisch per Name.
hiddenimports += collect_submodules("uvicorn")
# FastAPI lazy-Importe (Formulares, Standards).
hiddenimports += collect_submodules("fastapi")

a = Analysis(
    ["../src/halle_gehirn/bundle/entrypoint.py"],
    pathex=["../src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Schwere, im Bundle-Betrieb ungenutzte Pakete hart ausschliessen.
        "docling",
        "docling_core",
        "docling_ibm_models",
        "pymupdf",
        "fitz",
        "pymupdf4llm",
        "ragas",
        "datasets",
        "streamlit",
        "playwright",
        "torch",
        "transformers",
        "matplotlib",
        "pytest",
        # Ballast aus Hook-Abhaengigkeits-Closures (kein eigener Import):
        "pyarrow",
        "pandas",
        "scipy",
        "babel",
        "sqlalchemy",
        "aiohttp",
        "trio",
        "IPython",
        "numexpr",
        "setuptools",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="halle-gehirn",
    debug=False,
    strip=False,
    upx=False,
    console=True,  # Konsolenfenster zeigt structlog-Output (Betrieb/Fehlersuche)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="halle-gehirn",
)
