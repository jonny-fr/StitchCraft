/** WCAG contrast ratio of two opaque colours, given as "#rrggbb" or "rgb(r, g, b)". */
export function contrast(a: string, b: string): number {
  const [la, lb] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (la + 0.05) / (lb + 0.05);
}

function channels(color: string): number[] {
  const hex = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(color);
  if (hex) return hex.slice(1).map((h) => parseInt(h, 16));
  const rgb = /^rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)/.exec(color);
  if (rgb) return rgb.slice(1).map(Number);
  throw new Error(`not a colour: ${color}`);
}

function luminance(color: string): number {
  const [r, g, b] = channels(color).map((c) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
