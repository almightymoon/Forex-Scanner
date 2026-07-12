"""Configuration loader — all thresholds from config/swing_detection.yaml."""

from scanner.swing_detection.utils import SwingDetectionConfig, get_swing_detection_config

SwingEngineConfig = SwingDetectionConfig
get_config = get_swing_detection_config

__all__ = ["SwingEngineConfig", "get_config"]
