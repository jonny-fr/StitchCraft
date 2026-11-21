# Stitchcraft

Häkelanleitungen in Kurzschreibweise (de / en-US / en-UK) einlesen, prüfen und als
realistische 3D-Vorschau mit sichtbarem Garnverlauf zeigen.

Stand: **M0 (Fundament) und M1 (3D-Spike)** des Entwicklungsplans. Das Go/No-Go-Protokoll
liegt in [`docs/evaluation/m1.md`](docs/evaluation/m1.md).

## Starten

```sh
docker compose up --build        # UI: http://localhost:8080, API: http://localhost:8000
docker compose -f compose.yaml -f compose.dev.yaml up   # Entwicklung: Vite-HMR auf :5173, API mit --reload
```

Lokal ohne Docker:

```sh
uv sync                                   # Python 3.14, Workspace packages/core + services/api
uv run uvicorn stitchcraft_api.app:app --reload
cd web && pnpm install && pnpm dev        # http://localhost:5173
```

## Kommandozeile

```sh
uv run stitchcraft validate tests/reference/3-sphere/pattern.txt
uv run stitchcraft preview  tests/reference/3-sphere/pattern.txt --out /tmp/kugel
uv run stitchcraft gate     # misst A1–A9 und schreibt docs/evaluation/m1.md
```

## Tests

```sh
uv run pytest                     # Kern + API (A3–A5, A7–A9 automatisiert)
uv run pytest -m reference        # A1/A2 gegen Fotos in tests/reference (übersprungen ohne Fotos)
cd web && pnpm test && pnpm typecheck
```

`?fps` an der UI-URL blendet einen FPS-Zähler ein (A9, Viewer ≥ 30 FPS).

## Aufbau

```
packages/core/   stitchcraft_core: notation → ir → expand → graph → validate → sim → yarn → export
services/api/    FastAPI (validate, parse, previews mit Datei-Cache)
web/             React + react-three-fiber Viewer
data/            Dialekt-Vokabular, Maschenbibliothek, Garnvorlagen (versioniert)
tests/reference/ Referenzstücke für das M1-Gate (Fotos/Masken ergänzen, siehe README dort)
```

Commits enthalten keine Co-Autor-Trailer (pre-commit-Hook `no-coauthor-trailer`).
