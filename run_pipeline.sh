#!/usr/bin/env bash
set -euo pipefail

echo "Running collector..."
python -m src.collector.run

echo "Running processor..."
python -m src.processor.run

echo "Building FAISS index (optional)..."
python -m src.ai.run --build-index --skip-ai || true
