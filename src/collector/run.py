"""Orchestrate all Azure data collectors."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.collector.advisor_collector import AdvisorCollector
from src.collector.aks_collector import AksCollector
from src.collector.base import CollectorError, IngestionResult
from src.collector.cost_collector import CostCollector
from src.collector.metrics_collector import MetricsCollector
from src.collector.resource_graph_collector import ResourceGraphCollector
from src.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class OrchestrationReport:
    started_at: str
    completed_at: str = ""
    results: list[IngestionResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    export_csv: bool = True

    @property
    def success_count(self) -> int:
        return len(self.results)

    @property
    def failure_count(self) -> int:
        return len(self.errors)


def run_all(export_csv: bool = True, continue_on_error: bool = True) -> OrchestrationReport:
    """Run every collector in sequence and optionally export pipeline CSVs."""
    from datetime import datetime, timezone

    settings = get_settings()
    settings.ensure_data_dirs()

    report = OrchestrationReport(
        started_at=datetime.now(timezone.utc).isoformat(),
        export_csv=export_csv,
    )

    collectors = [
        CostCollector(settings),
        MetricsCollector(settings),
        ResourceGraphCollector(settings),
        AdvisorCollector(settings),
        AksCollector(settings),
    ]

    cost_collector: CostCollector | None = None
    metrics_collector: MetricsCollector | None = None

    for collector in collectors:
        try:
            result = collector.collect()
            report.results.append(result)

            if isinstance(collector, CostCollector):
                cost_collector = collector
            elif isinstance(collector, MetricsCollector):
                metrics_collector = collector

        except CollectorError as exc:
            msg = f"{collector.collector_name}: {exc}"
            logger.error(msg)
            report.errors.append(msg)
            if not continue_on_error:
                break
        except Exception as exc:
            msg = f"{collector.collector_name}: unexpected error — {exc}"
            logger.exception(msg)
            report.errors.append(msg)
            if not continue_on_error:
                break

    if export_csv:
        try:
            if cost_collector:
                cost_collector.export_csv()
            if metrics_collector:
                metrics_collector.export_usage_csv()
        except Exception as exc:
            err = f"csv_export: {exc}"
            logger.error(err)
            report.errors.append(err)

    report.completed_at = datetime.now(timezone.utc).isoformat()
    logger.info(
        "Orchestration finished — %d succeeded, %d failed",
        report.success_count,
        report.failure_count,
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run all Azure Cost Advisor data collectors"
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="Skip CSV export for downstream pandas pipeline",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first collector failure",
    )
    args = parser.parse_args()

    report = run_all(
        export_csv=not args.no_csv,
        continue_on_error=not args.fail_fast,
    )

    print(f"Collectors succeeded: {report.success_count}")
    for result in report.results:
        print(f"  - {result.collector}: {result.record_count} records -> {result.output_path}")

    if report.errors:
        print(f"Collectors failed: {report.failure_count}")
        for err in report.errors:
            print(f"  - {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
