# XAUUSD H1 post-2026H1 quarantine

This directory contains immutable, unlabeled candle-acquisition tranches
strictly after the historical 2026H1 benchmark.

Rules:

1. Do not run any swing-engine version on these candles.
2. Do not generate predictions, error analyses, or parameter searches.
3. Do not create labels until the required accrual period and benchmark
   protocol have been frozen.
4. Each tranche becomes immutable when committed.
5. New exports must be stored as new timestamped tranches; existing
   tranches must never be overwritten.
6. These tranches are not a locked benchmark until a future protocol
   explicitly freezes windows, labeling procedures, and evaluation rules.
