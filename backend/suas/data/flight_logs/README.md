# Flight-log evidence for bundled hover power

These CSVs are redacted conversions of public PX4 Flight Review ULogs,
produced by `backend/scripts/ulog_to_csv.py`. The converter sums every
battery pack, prefers `vehicle_local_position` (and falls back to barometric
altitude plus EKF velocity), holds the land-detector flag so ground samples
are dropped, and never copies pack serials or vehicle identifiers.

They are the evidence behind `Freefly_Astro_Max.hover_power_w` in
`aircraft.json`. The seed is updated by
`backend/scripts/apply_flight_log_to_seed.py`, which uses the same hover
estimator as `POST /api/logs?apply=true`. That ingest path writes the runtime
database only; it does not write this seed, by design.

Timestamps are boot-relative microseconds rendered as UTC datetimes starting
at `1970-01-01`. They preserve the original intervals so climb rate stays
valid; they are not a claim about the wall-clock flight time. Payload is
unstated in every public log, so every `payload_id` cell is empty.

All three source logs are licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
(“CC-BY PX4” in the PX4 documentation). The excerpts are provided under the
same license, with attribution below.

The applied figure is the 992.07 W median from `054112f4`, the only screened
log labeled Astro Max, and the conservative (highest) of the three usable
hover medians. The other two logs are supporting evidence and were not
written into the seed: their descriptions do not say Astro Max.

Cruise power in the seed is left at the previous datasheet-derived value.
The Astro Max log has a cruise window, but it was flown at a median 4.5 m/s,
not the 14 m/s catalog cruise, so that power is not evidence for
`cruise_power_w`.

## `054112f4` — applied (Astro Max)

| Field | Value |
| --- | --- |
| Flight Review | https://review.px4.io/plot_app?log=054112f4-683e-49c2-8777-097f5fe35df2 |
| Source ULog | https://cdn.logs.px4.io/054112f4-683e-49c2-8777-097f5fe35df2.ulg |
| Uploader description | Astro Max flight |
| License | CC BY 4.0 (CC-BY PX4) |
| Retrieved | 2026-11-14 14:53:58 EST (America/New_York) |
| Source SHA-256 | `5bcef1faf0bcd0a72e5ac38a4b36150951635f80edd5d888c4ae942f50b50618` |
| Source size | 21,731,794 bytes |
| Excerpt SHA-256 | `2d09ebe8e06d36d16b1fe52344ebb3462d17c96113dc085fb4a5f6f7745986e8` |
| Hover estimate | 179 samples, median 992.07 W, IQR 92.83 W, high confidence |
| Cruise window | 192 samples, median 1047.32 W, median speed 4.5 m/s (not applied) |

## `8f757ee6` — supporting, not applied

| Field | Value |
| --- | --- |
| Flight Review | https://review.px4.io/plot_app?log=8f757ee6-8978-4c7c-badc-0544b3a83906 |
| Source ULog | https://cdn.logs.px4.io/8f757ee6-8978-4c7c-badc-0544b3a83906.ulg |
| Uploader description | Penelope test flight March 25 2025 |
| License | CC BY 4.0 (CC-BY PX4) |
| Retrieved | 2026-11-14 14:55:55 EST (America/New_York) |
| Source SHA-256 | `9a9f0216f9a5bddf737821485a890f89674dc0c079f9941a08d8be84d5c5f40f` |
| Source size | 38,962,010 bytes |
| Excerpt SHA-256 | `64313dcedcd8e536cdc2b41631d76f2898eab243ebe851e31d41799d50960ca1` |
| Hover estimate | 152 samples, median 685.15 W, IQR 20.21 W, high confidence |
| Cruise window | none |
| Why not applied | Description does not say Astro Max. Official `FREEFLY_ASTRO_FMU_V5X` hardware. |

## `6ca79cb1` — supporting, not applied

| Field | Value |
| --- | --- |
| Flight Review | https://review.px4.io/plot_app?log=6ca79cb1-017c-457d-b1c5-f4f401d87eb0 |
| Source ULog | https://cdn.logs.px4.io/6ca79cb1-017c-457d-b1c5-f4f401d87eb0.ulg |
| Uploader description | Astro Flight1 |
| License | CC BY 4.0 (CC-BY PX4) |
| Retrieved | 2026-11-14 15:39:24 EST (America/New_York) |
| Source SHA-256 | `604332e81de90b829f850bc32ef2112666c099d36419054767fc9bbaafff4954` |
| Source size | 69,468,160 bytes |
| Excerpt SHA-256 | `aebe18f0a6a3d31e0011ae98d0b567b59abd016d788f087743bbb2c09f8a0ffe` |
| Hover estimate | 3536 samples, median 561.66 W, IQR 18.32 W, high confidence |
| Cruise window | 4838 samples, median 509.8 W, median speed 9.35 m/s (not applied) |
| Why not applied | Description does not say Astro Max. Official `FREEFLY_ASTRO_FMU_V5X` hardware. Cruise speed is still not the 14 m/s catalog cruise. |
