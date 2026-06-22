"""Manual and scheduled multi-tenant collection entry point."""

from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict

from src.config import get_settings
from src.services.multi_tenant_pipeline import MultiTenantPipelineService

logger = logging.getLogger(__name__)


def run_scheduled(
    service: MultiTenantPipelineService,
    interval_seconds: int,
    *,
    max_cycles: int | None = None,
    sleep=time.sleep,
) -> list:
    summaries = []
    cycle = 0
    while max_cycles is None or cycle < max_cycles:
        summaries.append(service.run_once())
        cycle += 1
        if max_cycles is None or cycle < max_cycles:
            sleep(interval_seconds)
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id")
    parser.add_argument("--subscription-id")
    parser.add_argument("--schedule", action="store_true")
    parser.add_argument("--interval-minutes", type=int)
    parser.add_argument("--fail-fast", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    service = MultiTenantPipelineService(settings)
    if args.schedule:
        interval = (
            args.interval_minutes or settings.collection_interval_minutes
        ) * 60
        run_scheduled(service, interval)
        return

    summary = service.run_once(
        tenant_id=args.tenant_id,
        subscription_id=args.subscription_id,
        continue_on_error=not args.fail_fast,
    )
    print(json.dumps(asdict(summary), indent=2, default=str))


if __name__ == "__main__":
    main()
