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

### Schnelltest

`docker compose up --build`, http://localhost:8080 öffnen, unter „Beispiel“ `3-sphere` wählen
und „3D-Vorschau“ klicken. Im 3D-Tab lassen sich Maschen anklicken (springt zur Stelle in
der Anleitung), Reihen ausblenden und die Garnfarben ändern.

## Notation

Eine Zeile je Runde/Reihe, Beispiele im Dialekt `de` (en-US/en-UK analog, siehe
`data/dialects/`):

```
Rd. 1: 6 fM in MR (6)          Label: Rd./Runde/R/Reihe, auch „R1:“ und „1. Rd:“
Rd. 2: 6x zun (12)             Wiederholung vorne …
Rd. 3: (1 fM, zun) x6 (18)     … oder hinten, (n) am Ende ist die Kontrollzahl
Rd. 4: 2 fM in jede M (36)     n Maschen in jede Masche, „fM rundum“
Rd. 5-8: 36 fM (36)            Bereich
Rd. 9 (nur hMg): 36 fM (36)    nur hinteres/vorderes Maschenglied
R 1: 16 Lm, wenden             Reihen mit Wendeluftmaschen
Füllen                         Hinweise werden übernommen, Freitext wird gemeldet
```

„R“ ist mehrdeutig (Runde oder Reihe): Beginnt das Stück im Magic Ring, gilt es als Runde.

### Farbwechsel

```
Farben: A = creme, B = rot, C = #2b2b2b     optional; Farbnamen siehe data/colors.toml
Rd. 1: 6 fM in MR (6)                       Start in der ersten Farbe (ohne Palette: A)
Rd. 2 (B): 6x zun (12)                      Farbe im Rundenkopf
Rd. 3: 3 fM, FbW C, 3 fM, FbW A, 6 fM (12)  Wechsel mitten in der Runde
FbW B                                       eigene Zeile: gilt ab der nächsten Runde
```

Varianten: `FbW X`, `Farbwechsel zu/auf X`, `mit Farbe X`, `in Farbe X`; englisch
`change to X`, `with color X`, Codes wie `MC`/`CC1`. Codes sind Großbuchstaben, Farbnamen
(`rot`, `blue`) und `#rrggbb` gehen direkt. Farben ohne Festlegung bekommen eine Ersatzfarbe
und sind im Viewer frei wählbar; das ändert nur die Darstellung, nicht die Simulation.

## Bekannte Grenzen (M1)

- Höchstens 5 000 Maschen pro Vorschau (≈ 7 ms pro Masche), sonst `E_TOO_LARGE`.
- Garn durchdringt sich bei Zu-/Abnahmen noch stellenweise (Kriterium A5, siehe Protokoll).
- Ein Teil pro Anleitung; kein Tapestry/Intarsien, keine Prosa-Farbwechsel
  („am Ende der Runde auf creme wechseln“).
- Der Fortschritt (`/previews/{id}/events`, SSE) meldet die Stufen validate, shape, yarn und export;
  die Formrelaxation selbst meldet keine Zwischenstände.

## Kommandozeile

```sh
uv run stitchcraft validate tests/reference/3-sphere/pattern.txt
uv run stitchcraft preview  tests/reference/3-sphere/pattern.txt --out /tmp/kugel
uv run stitchcraft gate     # misst A1–A9 und schreibt docs/evaluation/m1.md
uv run stitchcraft gate --milestone m5   # Stäbchen-Gate (Stück 6 u. a.), docs/evaluation/m5.md
```

## MCP-Server

`services/mcp` stellt den Kern als MCP-Server bereit. Tools: `validate_pattern` (Dialekt, Diagnosen
mit Zeile/Spalte und Meldung in `ui_locale` de|en, Soll/Ist je Reihe, geschätzte Häkelzeit
`time_estimate` nach `data/timing.toml`), `parse_pattern` (IR als JSON),
`render_preview` (GLB als Resource `stitchcraft://previews/{key}/model.glb`, Statistik und, wenn der
Snapshot-Dienst läuft, ein PNG; sonst nur mit Hinweis) und `list_stitches`. Vorschauen liegen im selben
Cache wie bei der API. Einbinden in Claude Code, Snapshot-Profil, Beispielsession: [`docs/mcp.md`](docs/mcp.md).

```sh
uv run stitchcraft-mcp stdio                    # stdio
uv run stitchcraft-mcp http --port 8765         # Streamable HTTP: http://localhost:8765/mcp
docker compose up -d                            # mcp auf :8765 (Dienst `mcp`)
docker compose run --rm -i mcp stdio            # stdio im Container (das Argument ist nötig)
docker compose --profile snapshot up -d         # zusätzlich der PNG-Renderer (Playwright, nur intern)
```

## Tests

```sh
uv run pytest                     # Kern + API + MCP (A3–A5, A7–A9 automatisiert)
uv run pytest -m reference        # A1/A2 gegen Fotos (übersprungen ohne Fotos), M5-Kriterien für Stück 6
cd web && pnpm test && pnpm typecheck && pnpm e2e
cd services/snapshot && npm ci && npm test    # Renderer; echter Chromium-Lauf: SNAPSHOT_REAL=1 SNAPSHOT_KEY=<id> STITCHCRAFT_WEB_URL=…
```

`?fps` an der UI-URL blendet einen FPS-Zähler ein (A9, Viewer ≥ 30 FPS). Gemessen wird A9 in
`web/e2e/fps.e2e.ts` (≈ 5 000 Maschen, Totale und Nahaufnahme); nur auf macOS mit Hardware-GPU (Metal),
sonst übersprungen.

## Aufbau

```
packages/core/   stitchcraft_core: notation → ir → expand → graph → validate → sim → yarn → export
services/api/    FastAPI (validate, parse, previews mit Datei-Cache)
services/mcp/    MCP-Server (FastMCP/MCPServer; stdio + Streamable HTTP)
services/snapshot/  Playwright-Renderer: PNG aus der Viewer-Seite (`/?snapshot=<key>`), Compose-Profil `snapshot`
web/             React + react-three-fiber Viewer
data/            Dialekt-Vokabular, Maschenbibliothek, Garnvorlagen, Häkelzeiten (versioniert)
tests/reference/ Referenzstücke für die Gates M1 und M5 (Fotos/Masken ergänzen, siehe README dort)
```

Commits enthalten keine Co-Autor-Trailer (pre-commit-Hook `no-coauthor-trailer`).
