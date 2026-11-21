# Referenzstücke (M1-Gate)

Jedes Unterverzeichnis enthält die Anleitung (`pattern.txt`) und Metadaten (`metadata.toml`).
Für die Abnahme A1/A2 kommen dazu (Foto-Protokoll, Plan §9):

```
<stück>/
  pattern.txt          Anleitung (de)
  metadata.toml        Garn, Nadel, Maschenprobe
  measurements.toml    gemessene Maße in mm (siehe unten)
  photos/front.jpg     neutralgrauer Hintergrund, Maßstabslineal, diffuses Licht
  photos/side.jpg
  photos/top.jpg
  photos/macro.jpg     1:1, ca. 3 × 3 Maschen
  masks/front.png      Silhouette (weiß = Stück), einmalig segmentiert
  masks/side.png
```

`measurements.toml`:

```toml
# Maße des echten Stücks in mm
width = 75.0       # Quadrat/Scheibe/Becher: größte Breite bzw. Durchmesser
height = 78.0      # Quadrat: Höhe; Kugel/Becher: Höhe
mm_per_px = 0.12   # Maßstab der Masken (vom Lineal abgelesen)
```

Fehlen diese Dateien, überspringt `pytest -m reference` die Kriterien A1/A2.
