"""Build FAISS index and run FinOps advisor queries."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.ai.advisor import FinOpsAdvisor
from src.ai.prompts import EXAMPLE_QUESTIONS
from src.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="FinsOpsIQ AI layer")
    parser.add_argument(
        "--build-index",
        action="store_true",
        help="Build or rebuild FAISS index from processed data",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Force rebuild of FAISS index (use with --build-index)",
    )
    parser.add_argument(
        "--recommendations",
        action="store_true",
        help="Generate FinOps recommendations report",
    )
    parser.add_argument(
        "--ask",
        type=str,
        default="",
        help="Ask a single FinOps question",
    )
    parser.add_argument(
        "--examples",
        action="store_true",
        help="Run example FinOps questions",
    )
    args = parser.parse_args()

    settings = get_settings()
    advisor = FinOpsAdvisor(settings)

    if args.build_index:
        count = advisor.build_index(rebuild=args.rebuild)
        print(f"FAISS index built: {count} vectors at {settings.embeddings_path / 'faiss_index'}")

    if args.recommendations:
        result = advisor.generate_recommendations()
        print(f"\n=== Recommendations ({result.get('source')}) ===\n")
        print(result.get("recommendations", ""))

    if args.ask:
        print(f"\nQ: {args.ask}\n")
        print(advisor.ask(args.ask))

    if args.examples:
        for question in EXAMPLE_QUESTIONS:
            print(f"\n{'=' * 60}\nQ: {question}\n")
            print(advisor.ask(question))

    if not any([args.build_index, args.recommendations, args.ask, args.examples]):
        parser.print_help()
        print("\nQuick start:")
        print("  python -m src.ai.run --build-index")
        print('  python -m src.ai.run --ask "Which VM wastes the most money?"')


if __name__ == "__main__":
    main()
