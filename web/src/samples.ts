// Reference pieces of the M1 gate (tests/reference/*/pattern.txt), all in the German dialect.
const files = import.meta.glob("../../tests/reference/*/pattern.txt", { query: "?raw", import: "default", eager: true });

export const samples: { id: string; text: string }[] = Object.entries(files)
  .map(([path, text]) => ({ id: path.split("/").at(-2) ?? path, text: text as string }))
  .sort((a, b) => a.id.localeCompare(b.id));
