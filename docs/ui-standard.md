# UI standard

The dashboard is built as an operations console, not a SaaS template. This page
records who it is for, the density that follows, and what CI holds it to.

## Operator

A sUAS mission planner or safety officer preflighting one mission on a 14-inch
1080p laptop in a field vehicle or ops trailer, reading about 25 computed
figures and a sealed assessment, deciding go or no-go and signing within two
minutes.

**Tier 2 (analyst).** Dark theme by default, 13px base text, 28px rows and
controls, 11px uppercase section labels, 20px the largest size anywhere. The
same statement heads `frontend/src/app/page.tsx`.

## Layout

A fixed 100vh shell with no page scroll at 1280px and wider: a 36px top bar
(product, UTC clock), the mission form on the left, the assessment workspace in
the middle, and the review-and-acknowledge inspector on the right. Panels scroll
inside themselves and are separated by 1px lines, not gaps or shadows. Figures
are dense tables (label, value, unit, basis), numbers right-aligned in tabular
numerals, IDs and hashes in the mono face.

## Tokens

`frontend/src/styles/tokens.css` holds every color, size, space and duration;
it is the only file allowed a literal color. `frontend/tailwind.config.ts`
replaces (does not extend) Tailwind's theme with those tokens, so the default
palette, radii above 4px, static shadows and text above 20px do not exist as
utilities. Fonts are the system stack plus any locally installed face; nothing
is fetched from a CDN.

Color carries meaning only: one accent for interaction; `ok`, `caution`,
`critical` and `stale` for status, always shown with text as well, as a 2-4px
left border or a 14% tint, never as a large solid fill. Green is an operational
GO and nothing else.

## Gate

`npm run lint:ui` (`frontend/src/lib/ui-scan.test.ts`) runs in the `frontend`
CI job as "UI standard scan". It fails on any gradient, backdrop blur, radius
above 4px, static shadow, indigo or purple accent, text above 20px, bounce or
pulse animation, Tailwind palette color, arbitrary pixel value, literal color
outside `tokens.css`, emoji, or `@ts-ignore`/`eslint-disable`/`any` under
`frontend/src`. Each rule is proven on a probe before the tree is scanned.

## Visual check

Every UI change is rendered and screenshot at 1920x1080, 1366x768 and
2560x1440 in its empty, loading, error and result states, critiqued and fixed
for two or three rounds before review. This is a local step, not a CI job.
