"""Orchestrate the full processing pipeline."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd

from src.config import get_settings
from src.processor.anomaly_detector import AnomalyDetector
from src.processor.normalizer import DataNormalizer, ProcessorError
from src.processor.report_generator import ReportGenerator
from src.processor.savings_estimator import SavingsEstimator
from src.processor.waste_detector import WasteDetector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class ProcessingReport:
    started_at: str
    completed_at: str = ""
    resource_count: int = 0
    waste_count: int = 0
    anomaly_count: int = 0
    total_estimated_savings_usd: float = 0.0
    output_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def run_processing() -> tuple[pd.DataFrame, ProcessingReport]:
    """Execute normalize → waste → savings → anomalies → report."""
    settings = get_settings()
    settings.ensure_data_dirs()

    report = ProcessingReport(started_at=datetime.now(timezone.utc).isoformat())

    try:
        logger.info("Step 1/5: Normalizing raw JSON into unified DataFrame")
        df = DataNormalizer(settings).normalize()

        logger.info("Step 2/5: Applying waste detection rules")
        df = WasteDetector(settings).detect(df)

        logger.info("Step 3/5: Estimating savings")
        df = SavingsEstimator(settings).estimate(df)
        savings_summary = SavingsEstimator.summary(df)

        logger.info("Step 4/5: Detecting cost anomalies")
        df, anomalies_payload = AnomalyDetector(settings).detect(df)

        logger.info("Step 5/5: Generating reports")
        outputs = ReportGenerator(settings).generate(df, anomalies_payload, savings_summary)

        report.resource_count = len(df)
        report.waste_count = int((df["waste_level"] != "NONE").sum())
        report.anomaly_count = anomalies_payload.get("anomaly_count", 0)
        report.total_estimated_savings_usd = savings_summary["total_estimated_savings_usd"]
        report.output_files = [str(p) for p in outputs.values()]

    except ProcessorError as exc:
        logger.error("Processing failed: %s", exc)
        report.errors.append(str(exc))
        raise
    except Exception as exc:
        logger.exception("Unexpected processing error")
        report.errors.append(str(exc))
        raise

    report.completed_at = datetime.now(timezone.utc).isoformat()
    logger.info(
        "Processing complete — %d resources, %d waste flags, %d anomalies, $%.2f savings",
        report.resource_count,
        report.waste_count,
        report.anomaly_count,
        report.total_estimated_savings_usd,
    )
    return df, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Azure Cost Advisor processor")
    args = parser.parse_args()
    _, report = run_processing()
    print(f"Resources processed: {report.resource_count}")
    print(f"Waste flagged: {report.waste_count}")
    print(f"Anomalies: {report.anomaly_count}")
    print(f"Est. savings: ${report.total_estimated_savings_usd:,.2f}")
    for path in report.output_files:
        print(f"  -> {path}")


if __name__ == "__main__":
    main()
