"""Collector metrics — Prometheus-ready counters and gauges."""

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CollectorMetrics:
    """Thread-safe in-memory metrics for monitoring and future Prometheus export."""

    import_duration_ms: list[float] = field(default_factory=list)
    import_rows_total: int = 0
    import_failures: int = 0
    validation_failures: int = 0
    repair_attempts: int = 0
    repair_successes: int = 0
    repair_failures: int = 0
    gap_count: int = 0
    provider_latency_ms: dict[str, list[float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record_import(self, *, duration_ms: float, success: bool, rows: int = 0) -> None:
        with self._lock:
            self.import_duration_ms.append(duration_ms)
            if len(self.import_duration_ms) > 1000:
                self.import_duration_ms = self.import_duration_ms[-500:]
            if success:
                self.import_rows_total += rows
            else:
                self.import_failures += 1

    def record_validation_failure(self, count: int = 1) -> None:
        with self._lock:
            self.validation_failures += count

    def record_repair(self, *, success: bool) -> None:
        with self._lock:
            self.repair_attempts += 1
            if success:
                self.repair_successes += 1
            else:
                self.repair_failures += 1

    def record_gaps(self, count: int) -> None:
        with self._lock:
            self.gap_count += count

    def record_provider_latency(self, provider: str, latency_ms: float) -> None:
        with self._lock:
            bucket = self.provider_latency_ms.setdefault(provider, [])
            bucket.append(latency_ms)
            if len(bucket) > 500:
                self.provider_latency_ms[provider] = bucket[-250:]

    @property
    def repair_success_rate(self) -> float:
        with self._lock:
            if self.repair_attempts == 0:
                return 1.0
            return self.repair_successes / self.repair_attempts

    @property
    def avg_import_duration_ms(self) -> float:
        with self._lock:
            if not self.import_duration_ms:
                return 0.0
            return sum(self.import_duration_ms) / len(self.import_duration_ms)

    def export_prometheus(self) -> str:
        """Render metrics in Prometheus text exposition format."""
        lines = [
            "# HELP fxnav_import_rows_total Total rows imported",
            "# TYPE fxnav_import_rows_total counter",
            f"fxnav_import_rows_total {self.import_rows_total}",
            "# HELP fxnav_import_failures_total Import failures",
            "# TYPE fxnav_import_failures_total counter",
            f"fxnav_import_failures_total {self.import_failures}",
            "# HELP fxnav_validation_failures_total Validation failures",
            "# TYPE fxnav_validation_failures_total counter",
            f"fxnav_validation_failures_total {self.validation_failures}",
            "# HELP fxnav_repair_success_rate Repair success rate",
            "# TYPE fxnav_repair_success_rate gauge",
            f"fxnav_repair_success_rate {self.repair_success_rate:.4f}",
            "# HELP fxnav_gap_count_total Gaps detected",
            "# TYPE fxnav_gap_count_total counter",
            f"fxnav_gap_count_total {self.gap_count}",
            "# HELP fxnav_import_duration_ms_avg Average import duration",
            "# TYPE fxnav_import_duration_ms_avg gauge",
            f"fxnav_import_duration_ms_avg {self.avg_import_duration_ms:.2f}",
        ]
        for provider, latencies in self.provider_latency_ms.items():
            avg = sum(latencies) / len(latencies) if latencies else 0
            lines.append(f'fxnav_provider_latency_ms{{provider="{provider}"}} {avg:.2f}')
        return "\n".join(lines) + "\n"

    def snapshot(self) -> dict[str, Any]:
        return {
            "import_rows_total": self.import_rows_total,
            "import_failures": self.import_failures,
            "import_duration_ms_avg": round(self.avg_import_duration_ms, 2),
            "validation_failures": self.validation_failures,
            "repair_attempts": self.repair_attempts,
            "repair_success_rate": round(self.repair_success_rate, 4),
            "gap_count": self.gap_count,
            "provider_latency_ms": {
                p: round(sum(v) / len(v), 2) if v else 0
                for p, v in self.provider_latency_ms.items()
            },
            "exported_at": time.time(),
        }


_metrics: CollectorMetrics | None = None


def get_collector_metrics() -> CollectorMetrics:
    global _metrics
    if _metrics is None:
        _metrics = CollectorMetrics()
    return _metrics

def reset_collector_metrics() -> None:
    global _metrics
    _metrics = None
