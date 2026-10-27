// WCAG 2.x contrast between token colors, so the NO-GO treatment's legibility
// is a test result rather than an eyeball judgement.

type Rgb = readonly [number, number, number];

function channels(hex: string): Rgb {
  const value = Number.parseInt(hex.slice(1), 16);
  return [(value >> 16) & 0xff, (value >> 8) & 0xff, value & 0xff];
}

function linear(channel: number): number {
  const c = channel / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const [r, g, b] = channels(hex).map(linear) as unknown as Rgb;
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG contrast ratio of two `#rrggbb` colors, from 1 to 21. */
export function contrastRatio(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return ((light ?? 0) + 0.05) / ((dark ?? 0) + 0.05);
}

/** `color` at `alpha` over an opaque `backdrop`, as `color-mix` paints it. */
export function over(color: string, backdrop: string, alpha: number): string {
  const top = channels(color);
  const base = channels(backdrop);
  return `#${top
    .map((channel, i) =>
      Math.round(channel * alpha + (base[i] ?? 0) * (1 - alpha))
        .toString(16)
        .padStart(2, "0"),
    )
    .join("")}`;
}
