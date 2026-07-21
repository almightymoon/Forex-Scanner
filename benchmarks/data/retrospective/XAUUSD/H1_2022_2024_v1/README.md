# XAUUSD H1 2022–2024 Retrospective Holdout Source

**Classification:** `RETROSPECTIVE_HOLDOUT`

**Package status:** `RETROSPECTIVE_HOLDOUT_SOURCE_FROZEN_NOT_LABELED`

## What this is

A contamination-aware retrospective holdout built from the chronological
prefix of the full MT5 `FXNavigators_XAUUSD_H1.csv` history ending strictly
before the already-exposed canonical 2024-07-15 boundary, plus a
48-bar embargo.

## What this is not

- Not a prospective forward test.
- Not a replacement for the frozen post-2026H1 final certification.
- Not eligible for tuning.
- Not eligible for evaluation until human-adjudicated labels are frozen.

## Coverage

- Retrospective rows: `15368`
- First UTC: `2022-01-02T22:00:00Z`
- Last UTC: `2024-07-11T04:00:00Z`
- Timezone schedule: `EET_EEST_EQUIVALENT_OFFSET_SCHEDULE`
- Exact IANA zone identified: `False`
- Conversion reference (implementation only): `Europe/Athens`
- Equivalent exact-match zones: `Europe/Athens, Europe/Helsinki, Europe/Bucharest`
- Exposed boundary raw index: `15416`
- Embargo bars: `48`

## Timezone attribution honesty

- The exact broker IANA timezone cannot be uniquely attributed.
- The data follows an EET/EEST-compatible UTC+2 winter / UTC+3 summer schedule.
- `Europe/Athens` is used only as a deterministic
  conversion reference (`DETERMINISTIC_IMPLEMENTATION_REFERENCE_ONLY`).
- Helsinki and Bucharest produce identical conversions for the validated
  period.
- This is not evidence that the broker server is physically or
  administratively located in Athens.

## Eligibility flags

- `eligible_for_tuning`: false
- `eligible_for_labeling`: true
- `eligible_for_evaluation`: false
- `prospective_test`: false

## Contamination honesty

The source existed before this package was constructed. Passing a later
retrospective evaluation may support an interim engineering decision only.
Final production certification still requires the prospective post-2026H1
benchmark.
