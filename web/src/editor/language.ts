import { HighlightStyle, StreamLanguage, syntaxHighlighting } from "@codemirror/language";
import { tags } from "@lezer/highlight";
import type { RowCount } from "../api";

/** One vocabulary entry of a dialect, as served by GET /api/v1/vocabulary. */
export interface Word { word: string; category: string; canonical: string }
export interface Token { from: number; to: number; text: string; type: string }

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const GLUED = new Set(["label", "stitch"]); // a digit may touch these ("R1", "sc2tog")
const NUMBER = /[x×]?\d+(?:-\d+)?(?:tog)?[x×]?(?![\p{L}\p{N}_])/iuy;
const COUNT = /\(\d+\)\s*\.?\s*$/y;

export const normalise = (w: string) => w.replace(/\s+/g, "").toLocaleLowerCase();

/** Same boundaries as the parser's word_regex: longest word first, case-insensitive. */
function wordPattern(words: Word[]): RegExp | null {
  const sorted = [...words].sort((a, b) => b.word.length - a.word.length);
  const parts = sorted.map(({ word, category }) => {
    let p = word.split(/\s+/).map(escape).join("\\s*");
    if (/^[\p{L}\p{N}]/u.test(word)) p = "(?<![\\p{L}\\p{N}_])" + p;
    if (/[\p{L}\p{N}]$/u.test(word)) p += GLUED.has(category) ? "(?![\\p{L}_])" : "(?![\\p{L}\\p{N}_])";
    return p;
  });
  return parts.length ? new RegExp(parts.join("|"), "iuy") : null;
}

const cache = new WeakMap<Word[], { rx: RegExp | null; lookup: Map<string, Word> }>();
function compiled(words: Word[]) {
  let c = cache.get(words);
  if (!c) {
    c = { rx: wordPattern(words), lookup: new Map(words.map((w) => [normalise(w.word), w])) };
    cache.set(words, c);
  }
  return c;
}

function numberMayStart(line: string, pos: number, prev: Token | undefined): boolean {
  if (prev && prev.to === pos && GLUED.has(prev.type)) return true;
  return !/[\p{L}\p{N}_]/u.test(line[pos - 1] ?? "");
}

export function scanLine(line: string, words: Word[]): Token[] {
  const { rx, lookup } = compiled(words);
  const out: Token[] = [];
  let pos = 0;
  while (pos < line.length) {
    const at = (re: RegExp) => ((re.lastIndex = pos), re.exec(line));
    let m: RegExpExecArray | null;
    let type: string | undefined;
    if ((m = at(COUNT))) type = "count";
    else if (rx && (m = at(rx))) type = lookup.get(normalise(m[0]))?.category ?? "word";
    else if (numberMayStart(line, pos, out.at(-1)) && (m = at(NUMBER))) type = "number";
    if (m && type) {
      const text = type === "count" ? m[0].trim().replace(/\.$/, "") : m[0];
      out.push({ from: pos, to: pos + text.length, text, type });
      pos += m[0].length;
    } else pos += 1;
  }
  return out;
}

/** The vocabulary word under ``pos`` (an offset into ``text``), for hover help. */
export function wordAt(text: string, pos: number, words: Word[]): Word | null {
  const start = text.lastIndexOf("\n", pos - 1) + 1;
  const end = text.indexOf("\n", pos);
  const line = text.slice(start, end < 0 ? undefined : end);
  const tok = scanLine(line, words).find((t) => t.from <= pos - start && pos - start < t.to);
  if (!tok || tok.type === "number" || tok.type === "count") return null;
  return compiled(words).lookup.get(normalise(tok.text)) ?? null;
}

export interface CountMarker { label: string; bad: boolean }

/** Gutter text per source line: the stitch count of the row(s) written on it. */
export function countMarkers(rows: (RowCount & { line?: number | null })[]): Map<number, CountMarker> {
  const out = new Map<number, CountMarker>();
  for (const r of rows) {
    if (!r.line) continue;
    const bad = r.expected !== null && r.expected !== r.actual;
    const label = bad ? `${r.actual}≠${r.expected}` : String(r.actual);
    const prev = out.get(r.line);
    out.set(r.line, { label: prev?.bad && !bad ? prev.label : label, bad: bad || !!prev?.bad });
  }
  return out;
}

const STYLE: Record<string, string> = {
  label: "heading",
  stitch: "keyword",
  macro: "atom",
  loop: "typeName",
  ring: "typeName",
  each: "typeName",
  same: "typeName",
  skip: "typeName",
  together: "typeName",
  stitch_word: "typeName",
  turn: "operator",
  color_change: "meta",
  palette: "meta",
  glossary: "meta",
  ignored: "comment",
  number: "number",
  count: "string",
};

/** Highlighting for the pattern notation of one dialect's vocabulary. */
export function patternLanguage(words: Word[]) {
  let lastLine = "";
  let lastTokens: Token[] = [];
  return StreamLanguage.define<null>({
    startState: () => null,
    token(stream) {
      if (stream.string !== lastLine) {
        lastLine = stream.string;
        lastTokens = scanLine(lastLine, words);
      }
      const tok = lastTokens.find((t) => t.to > stream.pos);
      if (!tok) {
        stream.skipToEnd();
        return null;
      }
      if (tok.from > stream.pos) {
        stream.pos = tok.from;
        return null;
      }
      stream.pos = tok.to;
      return STYLE[tok.type] ?? null;
    },
  });
}

export const patternHighlight = syntaxHighlighting(
  HighlightStyle.define([
    { tag: tags.heading, color: "var(--hl-label)", fontWeight: "600" },
    { tag: tags.keyword, color: "var(--hl-stitch)" },
    { tag: tags.atom, color: "var(--hl-macro)" },
    { tag: tags.typeName, color: "var(--hl-modifier)" },
    { tag: tags.operator, color: "var(--hl-modifier)", fontStyle: "italic" },
    { tag: tags.meta, color: "var(--hl-meta)" },
    { tag: tags.comment, color: "var(--muted)", fontStyle: "italic" },
    { tag: tags.number, color: "var(--hl-number)" },
    { tag: tags.string, color: "var(--muted)" },
  ]),
);
