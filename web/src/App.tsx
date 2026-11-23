import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { PatternEditor, type EditorHandle } from "./editor/PatternEditor";
import type { Word } from "./editor/language";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { ApiError, fetchVocabulary, paramsValid, requestPreview, validate, type Diagnostic, type PaletteColor, type Params, type PreviewResult, type Progress, type Validation } from "./api";
import { ParamsPanel } from "./params/ParamsPanel";
import { parseStitchFile, serializeStitchFile, stitchFileName } from "./stitchFile";
import { samples } from "./samples";
import { KEYS, loadColors, loadDialect, loadParams, loadString, save } from "./storage";
import { Viewer, type View, type ViewerHandle } from "./viewer/Viewer";

const DIALECTS = [
  { id: "auto", label: "auto" },
  { id: "de", label: "Deutsch" },
  { id: "en-US", label: "English (US)" },
  { id: "en-UK", label: "English (UK)" },
];

const NARROW = "(max-width: 768px)";

function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(() => window.matchMedia(NARROW).matches);
  useEffect(() => {
    const mq = window.matchMedia(NARROW);
    const on = () => setNarrow(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return narrow;
}

export default function App() {
  const { t, i18n } = useTranslation();
  const [text, setText] = useState(() => loadString(KEYS.text, samples.find((s) => s.id === "3-sphere")?.text ?? ""));
  const [dialect, setDialect] = useState(() => loadDialect());
  const [params, setParams] = useState<Params>(loadParams);
  // colours picked in the viewer, keyed by code and the colour the pattern gave it
  const [colorPicks, setColorPicks] = useState<Record<string, string>>(loadColors);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [result, setResult] = useState<PreviewResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [maxRow, setMaxRow] = useState(1e9);
  const [view, setView] = useState<View>("iso");
  const [overlay, setOverlay] = useState<string | null>(null);
  const [overlayOpacity, setOverlayOpacity] = useState(0.5);
  const [silhouette, setSilhouette] = useState(false);
  const narrow = useNarrow();
  const [tab, setTab] = useState<"editor" | "viewer">("editor");
  const editor = useRef<EditorHandle>(null);
  const [vocab, setVocab] = useState<Record<string, Word[]>>({});
  const viewer = useRef<ViewerHandle>(null);
  const showFps = new URLSearchParams(location.search).has("fps");

  useEffect(() => save(KEYS.text, text), [text]);
  useEffect(() => save(KEYS.dialect, dialect), [dialect]);
  useEffect(() => save(KEYS.params, params), [params]);
  useEffect(() => save(KEYS.colors, colorPicks), [colorPicks]);
  useEffect(() => () => void (overlay && URL.revokeObjectURL(overlay)), [overlay]);

  // live lint, debounced
  useEffect(() => {
    const ctrl = new AbortController();
    const id = setTimeout(() => {
      validate(text, dialect, ctrl.signal).then(setValidation).catch(() => undefined);
    }, 250);
    return () => (clearTimeout(id), ctrl.abort());
  }, [text, dialect]);

  // vocabulary for highlighting and hover: the chosen dialect, or the detected one
  const wordsDialect = dialect === "auto" ? (validation?.dialect ?? "de") : dialect;
  useEffect(() => {
    if (vocab[wordsDialect]) return;
    fetchVocabulary(wordsDialect).then((w) => setVocab((v) => ({ ...v, [wordsDialect]: w }))).catch(() => undefined);
  }, [wordsDialect, vocab]);
  const words = useMemo(() => vocab[wordsDialect] ?? [], [vocab, wordsDialect]);
  const describe = (w: Word) => t(`terms.${w.canonical}`, { defaultValue: t(`categories.${w.category}`, { defaultValue: w.canonical }) });
  const ambiguous = validation?.diagnostics.find((d) => d.code === "W_AMBIGUOUS_DIALECT");

  const message = (d: Diagnostic) => t(`diagnostics.${d.code}`, { ...d.params, line: d.span?.line });
  const runPreview = useCallback(async () => {
    setBusy(true);
    setError(null);
    setProgress(null);
    try {
      const r = await requestPreview(text, dialect, params, setProgress);
      setResult(r);
      setSelected(null);
      setMaxRow(Math.max(...r.shape.rows.map((row) => row.number)));
      setTab("viewer");
    } catch (e) {
      const diags = e instanceof ApiError ? e.diagnostics : [];
      setError(diags.length ? diags.map(message).join(" ") : (e as Error).message);
    } finally {
      setBusy(false);
      setProgress(null);
    }
  }, [text, dialect, params, t]);

  const stitchById = useMemo(() => new Map(result?.shape.stitches.map((s) => [s.id, s]) ?? []), [result]);
  const rowOf = useMemo(() => new Map(result?.shape.stitches.map((s) => [s.id, s.row]) ?? []), [result]);
  const palette = result?.shape.palette ?? [];
  const pickKey = (c: PaletteColor) => `${c.ref}:${c.hex}`;
  // the first colour the pattern leaves open takes the yarn colour from the parameters
  const hexOf = useCallback(
    (c: PaletteColor) => colorPicks[pickKey(c)] ?? (!c.defined && c.ref === palette[0]?.ref ? params.color : c.hex),
    [colorPicks, palette, params.color],
  );
  const colorOf = useMemo(() => {
    const hex = new Map(result?.shape.palette.map((c) => [c.ref, hexOf(c)]) ?? []);
    return new Map(result?.shape.stitches.map((s) => [s.id, hex.get(s.color) ?? "#ffffff"]) ?? []);
  }, [result, hexOf]);
  const rowNumbers = result?.shape.rows.map((r) => r.number) ?? [];
  const rounds = (result?.shape.rows[0]?.kind ?? "round") === "round";

  // 3D -> editor: select the stitch's token
  const selectStitch = (id: number) => {
    setSelected(id);
    const span = stitchById.get(id)?.span;
    if (span) editor.current?.select(span.start, span.end);
  };
  // editor -> 3D: highlight the first stitch made by the token under the caret
  const onCaret = (pos: number) => {
    const hit = result?.shape.stitches.find((s) => s.span && s.span.start <= pos && pos <= s.span.end);
    if (hit) setSelected(hit.id);
  };

  const exportFile = () => {
    const blob = new Blob([serializeStitchFile({ text, dialect, params, colors: colorPicks })], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = stitchFileName(text);
    a.click();
    URL.revokeObjectURL(url);
  };
  const importFile = async (file: File) => {
    const parsed = parseStitchFile(await file.text());
    if (!parsed.ok) return setImportError(t(`app.importError.${parsed.error}`));
    setImportError(null);
    setText(parsed.file.text);
    setDialect(parsed.file.dialect);
    setParams(parsed.file.params);
    setColorPicks(parsed.file.colors);
  };

  const paramsOk = paramsValid(params);
  const sel = selected !== null ? stitchById.get(selected) : undefined;
  const stats = result?.shape.stats;

  const editorPane = (
    <section className="editor">
      <div className="row">
        <label>
          {t("app.dialect")}{" "}
          <select value={dialect} onChange={(e) => setDialect(e.target.value)}>
            {DIALECTS.map((d) => <option key={d.id} value={d.id}>{d.id === "auto" ? t("app.autoDialect", { dialect: validation?.dialect ?? "–" }) : d.label}</option>)}
          </select>
        </label>
        <label>
          {t("app.sample")}{" "}
          <select value="" onChange={(e) => { const s = samples.find((x) => x.id === e.target.value); if (s) (setText(s.text), setDialect("de")); }}>
            <option value="">–</option>
            {samples.map((s) => <option key={s.id} value={s.id}>{s.id}</option>)}
          </select>
        </label>
        <button onClick={exportFile}>{t("app.exportFile")}</button>
        <label className="button">
          {t("app.importFile")}
          <input type="file" accept=".json,application/json" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) void importFile(f); e.target.value = ""; }} />
        </label>
      </div>
      {importError && <p className="error">{importError}</p>}
      {ambiguous && (
        <div className="row ambiguous">
          {t("app.pickDialect")}
          {(ambiguous.params.candidates as string[]).map((c) => (
            <button key={c} onClick={() => setDialect(c)}>{DIALECTS.find((d) => d.id === c)?.label ?? c}</button>
          ))}
        </div>
      )}
      <PatternEditor
        ref={editor}
        label={t("app.pattern")}
        value={text}
        onChange={setText}
        words={words}
        diagnostics={validation?.diagnostics ?? []}
        rows={validation?.rows ?? []}
        message={message}
        describe={describe}
        onCaret={onCaret}
      />
      <button className="primary" disabled={busy || !paramsOk} onClick={runPreview}>{busy ? t("app.computing") : t("app.preview")}</button>
      {busy && progress && (
        <label className="progress">
          {t(`app.stage.${progress.stage}`, { defaultValue: progress.stage })}
          <progress max={1} value={progress.fraction} />
        </label>
      )}
      {!paramsOk && <p className="error">{t("app.invalidParams")}</p>}
      {error && <p className="error">{t("app.error", { message: error })}</p>}

      <ul className="diagnostics">
        {validation && validation.diagnostics.length === 0 && <li className="ok">{t("app.noDiagnostics")}</li>}
        {validation?.diagnostics.map((d, i) => (
          <li key={i} className={d.severity}>
            <button
              className="link"
              onClick={() => d.span && editor.current?.select(d.span.start, d.span.end)}
            >
              {message(d)}
            </button>
          </li>
        ))}
      </ul>

      <details>
        <summary>{t("app.rowCounts")}</summary>
        <table className="counts">
          <tbody>
            {validation?.rows.map((r) => (
              <tr key={r.number} className={r.expected !== null && r.expected !== r.actual ? "bad" : ""}>
                <td>{t("app.row", { number: r.number })}</td>
                <td>{r.actual}</td>
                <td>{r.expected ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>

      <ParamsPanel params={params} onChange={setParams} />
    </section>
  );
  const viewerPane = (
    <section className="viewer">
      <div className="stage">
        {result ? (
          <Viewer
            ref={viewer}
            yarn={result.yarn}
            rowOf={rowOf}
            maxRow={maxRow}
            colorOf={colorOf}
            selected={selected}
            onSelect={selectStitch}
            silhouette={silhouette}
            view={view}
            rounds={rounds}
            material={params.material}
            showFps={showFps}
          />
        ) : (
          <div className="placeholder">{t("app.preview")} →</div>
        )}
        {overlay && <img className="overlay" src={overlay} style={{ opacity: overlayOpacity }} alt="" />}
      </div>
      {result && (
        <div className="controls">
          {stats && (
            <p className="stats">
              {t("app.stats", {
                stitches: stats.stitches,
                size: stats.size_cm.join(" × "),
                yarn: stats.yarn_length_m,
                ms: Math.round(Object.values(stats.timings).reduce((a, b) => a + b, 0)),
              })}
            </p>
          )}
          {sel && <p>{t("app.selected", { id: sel.id, type: sel.type, row: sel.row, color: sel.color })}</p>}
          <div className="row palette">
            {t("app.colors")}:
            {palette.map((c) => (
              <label key={c.ref} title={c.defined ? undefined : t("app.colorFallback")}>
                {c.ref}{" "}
                <input type="color" value={hexOf(c)} onChange={(e) => setColorPicks((p) => ({ ...p, [pickKey(c)]: e.target.value }))} />
              </label>
            ))}
          </div>
          <label>
            {t("app.showUpToRow", { row: Math.min(maxRow, rowNumbers.at(-1) ?? 0) })}
            <input
              type="range"
              min={rowNumbers[0] ?? 1}
              max={rowNumbers.at(-1) ?? 1}
              value={Math.min(maxRow, rowNumbers.at(-1) ?? 1)}
              onChange={(e) => setMaxRow(Number(e.target.value))}
            />
          </label>
          <div className="row">
            {t("app.views")}:
            {(["front", "side", "top", "iso"] as View[]).map((v) => (
              <button key={v} aria-pressed={view === v} onClick={() => setView(v)}>{t(`app.${v}`)}</button>
            ))}
          </div>
          <div className="row">
            <label>
              {t("app.overlay")}{" "}
              <input type="file" accept="image/*" onChange={(e) => { const f = e.target.files?.[0]; setOverlay(f ? URL.createObjectURL(f) : null); }} />
            </label>
            {overlay && (
              <label>{t("app.overlayOpacity")}<input type="range" min="0" max="1" step="0.05" value={overlayOpacity} onChange={(e) => setOverlayOpacity(Number(e.target.value))} /></label>
            )}
            <label><input type="checkbox" checked={silhouette} onChange={(e) => setSilhouette(e.target.checked)} /> {t("app.silhouette")}</label>
          </div>
          <div className="row">
            <button onClick={() => { const a = document.createElement("a"); a.href = viewer.current?.snapshot() ?? ""; a.download = `stitchcraft-${view}.png`; a.click(); }}>{t("app.snapshot")}</button>
            <a className="button" href={`/api/v1/previews/${result.id}/model.glb`} download="stitchcraft.glb">{t("app.exportGlb")}</a>
          </div>
        </div>
      )}
    </section>
  );

  return (
    <div className="app" data-tab={tab}>
      <header>
        <h1>{t("app.title")}</h1>
        <nav className="tabs">
          <button aria-pressed={tab === "editor"} onClick={() => setTab("editor")}>{t("app.editorTab")}</button>
          <button aria-pressed={tab === "viewer"} onClick={() => setTab("viewer")}>{t("app.viewerTab")}</button>
        </nav>
        <label>
          {t("app.uiLanguage")}{" "}
          <select
            value={i18n.language.slice(0, 2)}
            onChange={(e) => (void i18n.changeLanguage(e.target.value), save(KEYS.lang, e.target.value))}
          >
            <option value="de">Deutsch</option>
            <option value="en">English</option>
          </select>
        </label>
      </header>

      {narrow ? (
        <main className="stack">
          {editorPane}
          {viewerPane}
        </main>
      ) : (
        <PanelGroup direction="horizontal" autoSaveId="stitchcraft.split" className="split">
          <Panel defaultSize={35} minSize={20}>{editorPane}</Panel>
          <PanelResizeHandle className="handle" />
          <Panel defaultSize={65} minSize={30}>{viewerPane}</Panel>
        </PanelGroup>
      )}
    </div>
  );
}
