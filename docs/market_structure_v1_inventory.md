"""Market Structure Engine v1 — integration inventory (DEVELOPMENT_ONLY).

This document inventories current structure integration points and states
what remains legacy versus what the new v1 core will replace later.
"""

# Inventory

## Real FeatureExtractor

- Implementation: `services/quant_engine/features/extractor.py`
- Package export: `services/quant_engine/features/`
- Compatibility shim: `services/feature_engine/` (re-exports only)

## `analyze_market_structure` callers

- Definition: `services/quant_engine/swing_analysis.py`
- Also called from: `analyze_trend_context` in the same module
- `services/quant_engine/detection/smc.py` (`SMCEngine.detect_all`)
- `services/quant_engine/features/extractor.py` (fallback when context lacks structure)
- Tests under `tests/decision/`

## Zigzag / swing helpers

- `build_zigzag_swings`, `find_swings`, `classify_bos` live in
  `services/quant_engine/swing_analysis.py`
- Callers include SMC detection, `MarketStructureEngine.run` fallbacks, and
  decision/feature tests

## `MarketStructureEngine.run` callers

- Production: `services/quant_engine/decision/engine.py`
- Shim: `services/scanner_service/market_structure_engine.py`
- Tests: `tests/decision/test_v2_engines.py`

## Scanner orchestration order

1. `ScannerPipeline.scan_symbol` → data load
2. Indicators
3. `SMCEngine.detect_all` (legacy structure pass #1 + BOS/CHoCH patterns)
4. MTF / news
5. `DecisionEngine.evaluate` → `FeatureExtractor.extract` (structure pass #2)
6. Engines: Trend → **MarketStructure** → Liquidity → OrderBlock → FVG → …

## SMCPattern BOS / CHoCH

- Created only in `services/quant_engine/detection/smc.py` (`_detect_bos_choch`)
- Model: `shared.types.models.SMCPattern`

## Reusable enums

- `TrendDirection` — `shared.types.models` (BULLISH / BEARISH / RANGING)
- `SwingDirection`, `SwingTier`, `SwingScope` — `swing_engine.models`
- Prefer these over stringly-typed legacy `"internal"` / `"external"` returns

## SwingEngine contract

- `DetectionResult.confirmed_swings` filters `swings` where `confirmed`
- Legacy `build_zigzag_swings` currently consumes `result.swings` (not the
  confirmed contract) — a known defect for v1 integration boundaries

## Live scan path (unified)

1. `DataLoader.load` obtains confirmed swings once (`SCAN_SWING_VERSION=2.0.0`)
2. Runs Market Structure Engine v1 once → `StructureSnapshot`
3. `SMCEngine.detect_all` consumes those swings/snapshot (no legacy
   `analyze_market_structure`)
4. `DecisionEngine.evaluate` receives the same swings/snapshot, extracts
   features without a second SwingEngine call, passes features into
   `TrendEngine.analyze`, and scores structure via
   `run_from_structure_snapshot`

## Swing version decision

Keep **2.0.0** at the scan boundary until an explicit, tested cutover to
2.3.0. Do not silently change `swing_engine.DEFAULT_VERSION`.

## Later (not done here)

- Refactor lookahead-sensitive `score_structure_event` follow-through for live use
- Remove remaining legacy zigzag helpers from non-live paths
- Regime / setup / confluence consumers on `StructureSnapshot`

The v1 detector is **not wired** into FeatureExtractor or the live scanner in
this task. Integration is a separate follow-up after review.
