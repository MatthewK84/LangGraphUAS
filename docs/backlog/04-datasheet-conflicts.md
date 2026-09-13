---
title: "data: resolve documented datasheet conflicts (ANAFI / IF1200A / Alta X / Astro pack)"
labels: [phase-1, data]
blocked_by: [3]
---
## Goal
The README already documents places where stored constants disagree with published figures. Resolve each against the current datasheet, cite it, record the delta in `CITATIONS.md`.

## The list
- [ ] **Parrot ANAFI USA** `max_temp_c` — stored 43 vs published 49. Verify the current datasheet, pick one, cite it.
- [ ] **Inspired Flight IF1200A** `max_temp_c` — 50 vs 45.
- [ ] **Inspired Flight IF1200A** `battery_wh` and the 12S assumption — confirm or mark `estimate`.
- [ ] **Freefly Alta X** power figures — soft. Mark `estimate` with a reason if no datasheet number exists.
- [ ] **Freefly Astro** takeoff pack minimum 10 °C vs airframe −20 °C.

## The Astro entry is not a conflict
It is two different limits:
```
battery.pack_min_takeoff_c   # procedure limit, 10 C
limits.min_temp_c            # airframe limit, -20 C
```
Do not collapse the procedure limit into `min_temp_c`. This pair becomes a retrieval eval class (#50) and a model trap (#45).

## Acceptance
- [ ] A unit test per patched constant
- [ ] Each row in `CITATIONS.md` with before, after, and a retrieval date
- [ ] Anything unresolved is `source=estimate`, not a confident wrong number
