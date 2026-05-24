"""Data processing: normalize, detect waste/anomalies, estimate savings, report."""

from src.processor.anomaly_detector import AnomalyDetector
from src.processor.normalizer import DataNormalizer, ProcessorError, RawDataLoader
from src.processor.report_generator import ReportGenerator
from src.processor.run import run_processing
from src.processor.savings_estimator import SavingsEstimator
from src.processor.waste_detector import WasteDetector

__all__ = [
    "AnomalyDetector",
    "DataNormalizer",
    "ProcessorError",
    "RawDataLoader",
    "ReportGenerator",
    "SavingsEstimator",
    "WasteDetector",
    "run_processing",
]
