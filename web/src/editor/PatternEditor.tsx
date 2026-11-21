import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { setDiagnostics, type Diagnostic as CmDiagnostic } from "@codemirror/lint";
import { Compartment, EditorState, RangeSet, StateEffect, StateField } from "@codemirror/state";
import { EditorView, GutterMarker, gutter, hoverTooltip, keymap, lineNumbers } from "@codemirror/view";
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import type { Diagnostic, RowCount } from "../api";
import { countMarkers, patternHighlight, patternLanguage, wordAt, type CountMarker, type Word } from "./language";

export interface EditorHandle {
  select(from: number, to: number): void;
}

interface Props {
  value: string;
  onChange(value: string): void;
  words: Word[];
  diagnostics: Diagnostic[];
  rows: RowCount[];
  message(d: Diagnostic): string;
  describe(w: Word): string;
  onCaret(pos: number): void;
  label: string;
}

const setCounts = StateEffect.define<Map<number, CountMarker>>();
const counts = StateField.define<Map<number, CountMarker>>({
  create: () => new Map(),
  update: (value, tr) => tr.effects.find((e) => e.is(setCounts))?.value ?? value,
});

class CountGutterMarker extends GutterMarker {
  constructor(readonly m: CountMarker) {
    super();
  }
  eq(other: CountGutterMarker) {
    return other.m.label === this.m.label && other.m.bad === this.m.bad;
  }
  toDOM() {
    const el = document.createElement("span");
    el.textContent = this.m.label;
    if (this.m.bad) el.className = "bad";
    return el;
  }
}

const countGutter = gutter({
  class: "cm-counts",
  markers(view) {
    const map = view.state.field(counts);
    const marks = [];
    for (const [line, m] of map) {
      if (line <= view.state.doc.lines) marks.push(new CountGutterMarker(m).range(view.state.doc.line(line).from));
    }
    return RangeSet.of(marks, true);
  },
});

export const PatternEditor = forwardRef<EditorHandle, Props>(function PatternEditor(props, ref) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const latest = useRef(props);
  latest.current = props;
  const language = useRef(new Compartment());

  useImperativeHandle(ref, () => ({
    select(from, to) {
      const v = view.current;
      if (!v) return;
      const len = v.state.doc.length;
      v.dispatch({ selection: { anchor: Math.min(from, len), head: Math.min(to, len) }, scrollIntoView: true });
      v.focus();
    },
  }));

  useEffect(() => {
    const hover = hoverTooltip((v, pos) => {
      const w = wordAt(v.state.doc.toString(), pos, latest.current.words);
      if (!w) return null;
      return {
        pos,
        create() {
          const dom = document.createElement("div");
          dom.className = "cm-word-help";
          const b = document.createElement("b");
          b.textContent = w.word;
          dom.append(b, ` – ${latest.current.describe(w)}`);
          return { dom };
        },
      };
    });
    const v = new EditorView({
      parent: host.current!,
      state: EditorState.create({
        doc: latest.current.value,
        extensions: [
          lineNumbers(),
          counts,
          countGutter,
          history(),
          keymap.of([...defaultKeymap, ...historyKeymap]),
          language.current.of(patternLanguage(latest.current.words)),
          patternHighlight,
          hover,
          EditorView.lineWrapping,
          EditorView.contentAttributes.of({ "aria-label": latest.current.label, spellcheck: "false" }),
          EditorView.updateListener.of((u) => {
            if (u.docChanged) latest.current.onChange(u.state.doc.toString());
            if (u.selectionSet && u.view.hasFocus) latest.current.onCaret(u.state.selection.main.head);
          }),
        ],
      }),
    });
    view.current = v;
    return () => v.destroy();
  }, []);

  // external text changes (sample, import)
  useEffect(() => {
    const v = view.current;
    if (v && v.state.doc.toString() !== props.value) {
      v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: props.value } });
    }
  }, [props.value]);

  useEffect(() => {
    view.current?.dispatch({ effects: language.current.reconfigure(patternLanguage(props.words)) });
  }, [props.words]);

  useEffect(() => {
    const v = view.current;
    if (!v) return;
    const len = v.state.doc.length;
    const diags: CmDiagnostic[] = props.diagnostics
      .filter((d) => d.span)
      .map((d) => ({
        from: Math.min(d.span!.start, len),
        to: Math.min(d.span!.end, len),
        severity: d.severity,
        message: latest.current.message(d),
      }));
    v.dispatch(setDiagnostics(v.state, diags));
    v.dispatch({ effects: setCounts.of(countMarkers(props.rows)) });
  }, [props.diagnostics, props.rows]);

  return <div className="pattern-editor" ref={host} />;
});
