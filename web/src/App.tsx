import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { ApiError, fetchVocabulary, paramsValid, requestPreview, validate, type Diagnostic, type Params, type PreviewResult, type Progress, type Timing, type Validation } from "./api";
import { paletteColors, type ColorPicks, type ColorState } from "./colors";
import { dialectLabel } from "./dialects";
import { PatternEditor, type EditorHandle } from "./editor/PatternEditor";
import type { Word } from "./editor/language";
import { samples } from "./samples";
import { parseStitchFile, serializeStitchFile, stitchFileName } from "./stitchFile";
import { KEYS, loadColorSettings, loadDialect, loadPace, loadString, loadTheme, save } from "./storage";
import { applyTheme, useDarkScheme, type Theme } from "./theme";
import { formatDuration, secondsUpTo, type PaceSetting } from "./time";
import { ContextPill } from "./ui/ContextPill";
import { Header } from "./ui/Header";
import { Menu } from "./ui/Menu";
import { StatusBar } from "./ui/StatusBar";
import { TimeChip } from "./ui/TimeChip";
import { ViewerOverlay } from "./ui/ViewerOverlay";
import { Viewer, type View, type ViewerHandle } from "./viewer/Viewer";

function download(href: string, name: string) {
  const a = document.createElement("a");
  a.href = href;
  a.download = name;
  a.click();
}

export default function App() {
  const { t, i18n } = useTranslation();
  const [text, setText] = useState(() => loadString(KEYS.text, samples.find((s) => s.id === "3-sphere")?.text ?? ""));
  const [dialect, setDialect] = useState(() => loadDialect());
  const [initial] = useState(loadColorSettings);
  const [params, setParams] = useState<Params>(initial.params);
  // colours picked for palette entries other than the first open one (that one is params.color)
  const [colorPicks, setColorPicks] = useState<ColorPicks>(initial.picks);
  const [theme, setTheme] = useState<Theme>(loadTheme);
  const [pace, setPace] = useState<PaceSetting>(loadPace);
  const dark = useDarkScheme(theme);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [result, setResult] = useState<PreviewResult | null>(null);
  // what the shown preview was computed from (see previewInput)
  const [previewed, setPreviewed] = useState<string | null>(null);
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
  const [tab, setTab] = useState<"editor" | "viewer">("editor");
  const editor = useRef<EditorHandle>(null);
  const [vocab, setVocab] = useState<Record<string, Word[]>>({});
  const viewer = useRef<ViewerHandle>(null);
  const showFps = new URLSearchParams(location.search).has("fps");

  useEffect(() => save(KEYS.text, text), [text]);
  useEffect(() => save(KEYS.dialect, dialect), [dialect]);
  useEffect(() => save(KEYS.params, params), [params]);
  useEffect(() => save(KEYS.colors, colorPicks), [colorPicks]);
  useEffect(() => save(KEYS.pace, pace), [pace]);
  useEffect(() => {
    applyTheme(theme);
    save(KEYS.theme, theme);
  }, [theme]);
  useEffect(() => void (document.documentElement.lang = i18n.language), [i18n.language]);
  useEffect(() => () => void (overlay && URL.revokeObjectURL(overlay)), [overlay]);

  // live lint and time estimate, debounced; invalid params leave the yarn factor at its default
  const paramsOk = paramsValid(params);
  const timing = useMemo<Timing>(
    () => ({ yarn: paramsOk ? { yarn_mm: params.yarn_mm, material: params.material } : null, pace }),
    [paramsOk, params.yarn_mm, params.material, pace],
  );
  useEffect(() => {
    const ctrl = new AbortController();
    const id = setTimeout(() => {
      validate(text, dialect, timing, ctrl.signal).then(setValidation).catch(() => undefined);
    }, 250);
    return () => (clearTimeout(id), ctrl.abort());
  }, [text, dialect, timing]);

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
  // the colour is applied by the viewer, so it does not make a preview stale
  const previewInput = JSON.stringify([text, dialect, { ...params, color: null }]);
  const runPreview = useCallback(async () => {
    setBusy(true);
    setError(null);
    setProgress(null);
    try {
      const r = await requestPreview(text, dialect, params, setProgress);
      setResult(r);
      setPreviewed(previewInput);
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
  }, [text, dialect, params, previewInput, t]);
  // small screens have no preview button: the 3D tab computes the preview when it is missing or stale;
  // while the pattern has errors it only switches, so the last preview stays reachable
  const openViewer = () => {
    if (!busy && paramsOk && validation?.ok !== false && previewed !== previewInput) void runPreview();
    else setTab("viewer");
  };

  const stitchById = useMemo(() => new Map(result?.shape.stitches.map((s) => [s.id, s]) ?? []), [result]);
  const rowOf = useMemo(() => new Map(result?.shape.stitches.map((s) => [s.id, s.row]) ?? []), [result]);
  const palette = result?.shape.palette ?? null;
  // a colour change only recolours the yarn: no new preview, and the cache key has no colour
  const colorOf = useMemo(() => {
    const hex = paletteColors(palette ?? [], params.color, colorPicks);
    return new Map(result?.shape.stitches.map((s) => [s.id, hex.get(s.color) ?? "#ffffff"]) ?? []);
  }, [result, palette, params.color, colorPicks]);
  const colors: ColorState = { color: params.color, picks: colorPicks };
  const setColors = (c: ColorState) => (setParams((p) => ({ ...p, color: c.color })), setColorPicks(c.picks));
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
    const blob = new Blob([serializeStitchFile({ text, dialect, params, colors: colorPicks, pace })], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    download(url, stitchFileName(text));
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
    if (parsed.file.pace) setPace(parsed.file.pace);
  };
  const setOverlayFile = (f: File | null) => setOverlay(f ? URL.createObjectURL(f) : null);

  const stats = result?.shape.stats;
  const estimate = validation?.time_estimate;
  const stage = progress ? t(`app.stage.${progress.stage}`, { defaultValue: progress.stage }) : t("app.computing");
  const timeChip = (className: string) => <TimeChip estimate={estimate} pace={pace} onPace={setPace} className={className} />;

  const editorPane = (
    <section className="editor">
      {importError && <p className="banner error" role="alert">{importError}</p>}
      {ambiguous && (
        <div className="banner warning">
          {t("app.pickDialect")}
          {(ambiguous.params.candidates as string[]).map((c) => (
            <button key={c} onClick={() => setDialect(c)}>{dialectLabel(c)}</button>
          ))}
        </div>
      )}
      <div className="card editor-card">
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
          dark={dark}
        />
      </div>
      <StatusBar validation={validation} message={message} onPick={(d) => d.span && editor.current?.select(d.span.start, d.span.end)} />
      {timeChip("editor-time")}
      <button className="primary" disabled={busy || !paramsOk} onClick={runPreview}>
        {busy ? stage : t("app.preview")}
        {busy && <progress max={1} value={progress?.fraction} aria-label={t("app.computing")} />}
      </button>
      {!paramsOk && <p className="error">{t("app.invalidParams")}</p>}
      {error && <p className="error">{t("app.error", { message: error })}</p>}
    </section>
  );
  const viewerPane = (
    <section className="viewer">
      <div className="viewer-card">
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
            <div className="placeholder">{t("app.noPreview")}</div>
          )}
          {overlay && <img className="overlay" src={overlay} style={{ opacity: overlayOpacity }} alt="" />}
        </div>
        {!result && <div className="viewer-bottom">{timeChip("viewer-time")}</div>}
        {result && stats && (
          <ViewerOverlay
            stats={stats}
            selected={selected !== null ? stitchById.get(selected) : undefined}
            view={view}
            onView={setView}
            rowNumbers={rowNumbers}
            maxRow={maxRow}
            onMaxRow={setMaxRow}
            timeUpTo={estimate ? t("time.upTo", { time: formatDuration(t, secondsUpTo(estimate, maxRow)) }) : null}
            corner={timeChip("viewer-time")}
            overlay={overlay}
            onOverlay={setOverlayFile}
            overlayOpacity={overlayOpacity}
            onOverlayOpacity={setOverlayOpacity}
            silhouette={silhouette}
            onSilhouette={setSilhouette}
            onPng={() => download(viewer.current?.snapshot() ?? "", `stitchcraft-${view}.png`)}
            glbHref={`/api/v1/previews/${result.id}/model.glb`}
          />
        )}
      </div>
    </section>
  );

  return (
    <div className="app" data-tab={tab}>
      <Header
        pill={
          <ContextPill
            dialect={dialect}
            detected={validation?.dialect}
            onDialect={setDialect}
            params={params}
            onParams={setParams}
            palette={palette}
            colors={colors}
            onColors={setColors}
          />
        }
        menu={
          <Menu
            onSample={(s) => (setText(s), setDialect("de"))}
            onImport={(f) => void importFile(f)}
            onExport={exportFile}
            theme={theme}
            onTheme={setTheme}
          />
        }
      />
      <nav className="tabs segmented" aria-label={t("app.tabs")}>
        <button aria-pressed={tab === "editor"} onClick={() => setTab("editor")}>{t("app.editorTab")}</button>
        <button aria-pressed={tab === "viewer"} onClick={openViewer} data-busy={busy || undefined} style={{ "--progress": progress?.fraction ?? 0 } as CSSProperties}>
          {busy ? stage : t("app.viewerTab")}
        </button>
      </nav>
      {/* one tree for every width, so crossing the breakpoint keeps the editor state and the camera */}
      <PanelGroup direction="horizontal" autoSaveId="stitchcraft.split" className="split">
        <Panel id="editor" order={1} defaultSize={35} minSize={20} className="pane-editor">{editorPane}</Panel>
        <PanelResizeHandle className="handle" />
        <Panel id="viewer" order={2} defaultSize={65} minSize={30} className="pane-viewer">{viewerPane}</Panel>
      </PanelGroup>
    </div>
  );
}
