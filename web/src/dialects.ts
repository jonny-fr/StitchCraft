/** Pattern dialects the parser knows; `auto` lets the server detect one. */
export const DIALECTS = [
  { id: "auto", label: "auto" },
  { id: "de", label: "Deutsch" },
  { id: "en-US", label: "English (US)" },
  { id: "en-UK", label: "English (UK)" },
];

export const DIALECT_IDS = DIALECTS.map((d) => d.id);

export const dialectLabel = (id: string) => DIALECTS.find((d) => d.id === id)?.label ?? id;
