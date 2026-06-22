"""End-to-end data pipeline: collect → process → index → recommend."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.ai.advisor import FinOpsAdvisor
from src.collector.run import run_all
from src.config import get_settings
from src.processor.anomaly_detector import AnomalyDetector
from src.processor.report_generator import ReportGenerator
from src.processor.run import run_processing
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run_pipeline(skip_ai: bool = False) -> dict:
    settings = get_settings()
    settings.ensure_data_dirs()

    logger.info("Step 1/4: Running all collectors")
    run_all(export_csv=True, continue_on_error=False)

    logger.info("Step 2/4: Processing raw data")
    _, proc_report = run_processing()

    summary = ReportGenerator(settings).load_latest_summary()
    waste_payload = json.loads(
        (settings.processed_path / "waste_findings_latest.json").read_text(encoding="utf-8")
    )
    anomaly_payload = AnomalyDetector(settings).load_latest()

    recommendations = None
    if not skip_ai:
        logger.info("Step 3/4: Building FAISS index and generating AI recommendations")
        advisor = FinOpsAdvisor(settings)
        try:
            advisor.build_index(rebuild=True)
        except Exception as exc:
            logger.warning("FAISS index build skipped: %s", exc)
        recommendations = advisor.generate_recommendations()
    else:
        logger.info("Step 3/4: Skipped (skip_ai=True)")

    logger.info("Step 4/4: Pipeline complete")
    return {
        "summary": summary,
        "waste_count": proc_report.waste_count,
        "anomaly_count": proc_report.anomaly_count,
        "total_estimated_savings": proc_report.total_estimated_savings,
        "recommendations_source": (
            recommendations.get("source") if recommendations else "skipped"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="FinsOpsIQ pipeline")
    parser.add_argument(
        "--skip-ai",
        action="store_true",
        help="Skip Azure OpenAI recommendations and FAISS indexing",
    )
    args = parser.parse_args()
    result = run_pipeline(skip_ai=args.skip_ai)
    logger.info("Pipeline complete: %s", result)


if __name__ == "__main__":
    main()
