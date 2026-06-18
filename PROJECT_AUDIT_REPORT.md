# Project End-to-End Verification Report

Audit date: 2026-06-11  
Repository state: `main`, with a pre-existing staged change in `src/ai/advisor.py`

## Executive Verdict

The project is not production-ready. Azure authentication, Cost Management,
Resource Graph, and Advisor API calls work directly. The dashboard image also
serves successfully when built and run under a unique Docker tag.

The complete live pipeline does not produce a truthful cost dashboard:

- Live run collected 38 Cost Management rows.
- Resource Graph returned 3 inventory resources.
- Processing normalized 0 resources and reported total cost `$0.00`.
- Waste and savings were both `$0.00`.
- Two cost anomalies were detected from the raw cost series.
- Azure OpenAI could not run because the configured endpoint hostname does not
  resolve in DNS.
- Docker Compose starts the pipeline entrypoint as the dashboard because both
  services use the same image tag.

Status meanings:

- **LIVE**: verified against Azure on 2026-06-11.
- **MOCK**: loaded from `tests/mock_data`.
- **CACHED**: read from persisted local artifacts.
- **SYNTHETIC**: locally derived, estimated, or inserted rather than returned by Azure.
- **BROKEN/PARTIAL**: code exists, but the verified flow is incomplete or fails.

## Component Matrix

| Component | Purpose and files | Data source and code path | Status | Latest actual output | Independent verification |
|---|---|---|---|---|---|
| Azure Authentication | Create a singleton `DefaultAzureCredential`. `src/collector/auth.py`, `src/config.py` | `.env` -> `load_dotenv()` -> `DefaultAzureCredential` -> Azure token | **LIVE** | Management token acquired; Resource Manager listed 2 resource groups | `PYTHONUTF8=1 python verify_azure_auth.py`; expected token and Resource Manager success. Note: its Cost query uses unsupported `TheLastMonth` and the script still exits 0 after failure. |
| Resource Graph | Query disks, public IPs, and inventory. `src/collector/resource_graph_collector.py` | Azure Resource Graph, three KQL queries -> merged envelope -> `resource_graph_latest.json` | **LIVE + SYNTHETIC estimates** | 0 unattached disks, 0 public IPs, 3 inventory resources | `python diagnose_live_fetch.py`; expected `metadata.source=live`. Disk `daysUnattached=30`, disk price `size*0.15`, and public IP price `$3.65` are hard-coded estimates. |
| Cost Management | Collect daily cost and usage grouped by RG/service/location. `src/collector/cost_collector.py` | Cost Management `query.usage()` -> validated records -> JSON/CSV | **LIVE** | 38 rows in the isolated live run | `python diagnose_live_fetch.py`; expected `records count > 0`. Direct collector succeeded. |
| Azure Advisor | Collect Cost recommendations. `src/collector/advisor_collector.py` | Advisor API -> filter category `Cost` -> normalized recommendations | **LIVE + SYNTHETIC placeholder** | API call succeeded; output contains one locally inserted "No recommendations" row | `python diagnose_live_fetch.py`; independently inspect `metadata.source` and recommendation ID. Empty Azure results are converted to a fake record rather than an empty list. |
| Data Collectors | Run Cost, VM metrics, Resource Graph, Advisor, and AKS sequentially. `src/collector/run.py`, `src/collector/base.py` | Live call when four credential strings exist; any exception silently falls back to fixtures | **PARTIAL / MIXED** | Isolated live run reported 5 succeeded, 0 failed: counts `38, 0, 3, 1, 0` | `python -m src.collector.run --fail-fast`. Verify each output's `metadata.source`, `ingestion.simulatedApi`, and `mockSource`; success count alone is not provenance. |
| VM Metrics Collector | Intended to collect Monitor CPU/memory/network metrics. `src/collector/metrics_collector.py` | Lists VMs, but loop body is `pass`; `MonitorManagementClient` is never queried | **PARTIAL LIVE inventory, no metrics** | 0 VMs and 0 metric rows in the current subscription | `python -c "from src.collector.metrics_collector import MetricsCollector; print(MetricsCollector()._fetch_live_data())"`; with VMs present, current code would still emit no resources. |
| AKS Collector | Intended to collect cluster/node utilization. `src/collector/aks_collector.py` | Lists clusters, but loop body is `pass`; Monitor is never queried | **PARTIAL LIVE inventory, no metrics** | 0 clusters | Run `_fetch_live_data()` directly. With clusters present, current code would still emit no cluster records. |
| Processing / Normalization | Convert raw envelopes into canonical resource rows. `src/processor/normalizer.py`, `src/processor/run.py` | VM metrics + allocated VM costs; orphan disks/IPs; AKS metrics; aggregate costs explicitly discarded | **BROKEN for cost-only subscriptions** | 38 live cost rows became 0 canonical resources and total cost `$0.00` | Run isolated `python -m src.pipeline --skip-ai`; expected total should reconcile to raw Cost Management totals. Actual summary was zero. |
| Waste Detection | Flag low-CPU VMs, unattached disks, idle IPs, and low-utilization AKS. `src/processor/waste_detector.py` | Canonical DataFrame -> fixed local thresholds | **SYNTHETIC heuristic** | 0 findings on the latest live run because normalization produced 0 rows | `python -m src.processor.run`; inspect `waste_findings_latest.json`. Rules are not Azure Advisor results and have no observation-duration enforcement. |
| Savings Estimation | Apply fixed savings percentages by waste rule. `src/processor/savings_estimator.py` | Waste rows -> rates: VM 55%, disk/IP 100%, AKS 35%, fallback 25% | **SYNTHETIC estimate** | `$0.00` on latest live run | Inspect `SAVINGS_RATES`; recompute `monthly_cost * rate`. No Azure Retail Prices, reservations, licensing, region, or SKU pricing is queried. |
| Anomaly Detection | Detect daily spend above 1.5 times prior seven-day average. `src/processor/anomaly_detector.py` | Raw Cost Management records -> local rolling average | **LIVE-derived, SYNTHETIC rule** | 2 anomalies in isolated live run | `python -m src.processor.run`; inspect `anomalies_latest.json`. Configured `ANOMALY_ZSCORE_THRESHOLD` is unused; implementation is not a z-score. |
| FAISS Index | Persist embedded processed/resource/advisor/knowledge chunks. `src/ai/vector_store.py`, `src/ai/embeddings.py` | Processed CSV/JSON + raw Advisor + six hard-coded FinOps documents -> Azure embeddings -> FAISS | **CACHED** | Existing index loads: 11 vectors / 11 docstore entries; manifest built 2026-06-09 | `python -c "...FAISS.load_local(...); print(store.index.ntotal)"`. Manifest path records `/app/...`, showing it was built in a container. Querying requires the unavailable embedding endpoint. |
| Azure OpenAI | Supply embeddings and chat completion. `src/ai/embeddings.py`, `src/ai/rag.py` | Configured Azure OpenAI endpoint and deployments | **BROKEN now** | Host `cost-advisor-open-ai.openai.azure.com` returned DNS `NXDOMAIN`; embedding and chat calls raised `APIConnectionError` | `Resolve-DnsName cost-advisor-open-ai.openai.azure.com`; expected an A/CNAME record, actual DNS name does not exist. |
| RAG Pipeline | Retrieve FAISS chunks and generate answers/recommendations. `src/ai/rag.py`, `src/ai/vector_store.py` | Query embedding -> FAISS similarity -> LangChain retrieval chain -> Azure chat model | **BROKEN now / historically cached** | Persisted recommendation says `azure_openai_rag`, but current retrieval and generation both fail before returning output | `python -m src.ai.run --ask "What are my biggest savings opportunities?"`; expected answer, actual unhandled `openai.APIConnectionError`. |
| FinOps Chat | Streamlit chat over `FinOpsAdvisor.ask()`. `src/dashboard/chat.py`, `src/ai/advisor.py` | Inventory keyword path -> RAG when OpenAI strings exist -> rule-based fallback otherwise | **PARTIAL** | Offline rule-based answer works. Configured mode fails on OpenAI connection. Current staged code calls missing `_handle_live_inventory()` before falling through. | Clear OpenAI env vars and run `python -m src.ai.run --ask ...` for rule-based mode. In configured mode, verify the command exits successfully; it currently does not. |
| AI Recommendations | Generate or display prioritized recommendation text/cards. `src/ai/advisor.py`, `src/dashboard/components/recommendation_cards.py` | Cached `recommendations_latest.json`; cards primarily rebuilt from canonical resource rows | **CACHED / PARTIAL** | Dashboard cache reports source `azure_openai_rag`; regeneration currently fails. Cards can still display deterministic waste rows without AI. | Delete/relocate cached recommendation in an isolated data directory, regenerate, and require `source=azure_openai_rag` plus successful API response. |
| Dashboard Pages | Executive Summary, Waste, Cost Trends, Recommendations, Anomalies, Chat. `src/dashboard/app.py`, `src/dashboard/data_loader.py`, `src/dashboard/components/*`, `src/dashboard/charts.py` | Reads latest local raw/processed files and FAISS manifest; no page queries Azure directly | **CACHED** | Current cache: 1 resource, `$3.65` cost/savings, 0 anomalies, 6 daily rows, FAISS ready. It is older than the 2026-06-11 live audit run. | `streamlit run src/dashboard/app.py`; verify each tab. `DashboardDataLoader().load()` reports the values above. Sidebar status only checks whether credential strings exist, not API health/provenance. |
| Docker Setup | Build dashboard and optional pipeline services. `docker-compose.yml`, `Dockerfile*`, `run_pipeline.sh` | Two images from separate Dockerfiles, shared bind-mounted data | **BROKEN in Compose; dashboard Dockerfile works alone** | Compose built, but both services used `azure-cost-advisor:local`; dashboard started `./run_pipeline.sh`. Four collectors then failed from missing SDK packages and missing fixtures. Unique dashboard image returned health `ok`. | `docker compose config --quiet`; `docker compose build`; inspect `docker image inspect azure-cost-advisor:local`; `docker compose up -d cost-advisor`; expected Streamlit, actual pipeline entrypoint. Control: unique dashboard tag served `/_stcore/health -> ok`. |

## Actual End-to-End Live Run

Command:

```powershell
$env:DATA_RAW_DIR="<isolated raw path>"
$env:DATA_PROCESSED_DIR="<isolated processed path>"
$env:DATA_EMBEDDINGS_DIR="<isolated embeddings path>"
.\.venv\Scripts\python.exe -m src.pipeline --skip-ai
```

Observed on 2026-06-11 at 09:58 UTC:

```text
Collectors: 5 succeeded, 0 failed
Cost: 38 live records
VM metrics: 0 live records
Resource Graph: 3 live inventory records
Advisor: 1 placeholder record
AKS: 0 live records
Processed resources: 0
Waste findings: 0
Anomalies: 2
Total cost: $0.00
Estimated savings: $0.00
Exit code: 0
```

The command completes, but it does not preserve the live Cost Management total
in the processed summary. Therefore it is operationally successful but
functionally incorrect.

## Tests and Build Verification

| Check | Expected | Actual |
|---|---|---|
| `python -m compileall -q src` | No syntax errors | PASS |
| `python -m pip check` | No broken installed dependencies | PASS in the local environment |
| `pytest tests -v --cov=src` | 24 passing tests | 8 passed, 12 failed, 4 errors; reported coverage 49% |
| Isolated test rerun with `DATA_*` overrides | 24 passing tests without Azure calls | 15 passed, 9 failed; suite entered live mode and hit Azure throttling |
| `docker compose config --quiet` | Valid Compose model | PASS |
| `docker compose build cost-advisor pipeline` | Two independently runnable images | Build PASS, but shared tag caused entrypoint collision |
| Unique `Dockerfile.dashboard` image health | HTTP 200 / `ok` | PASS |

Test reliability issues:

- `Settings` does not enable `populate_by_name`, so fixture arguments such as
  `data_raw_dir=tmp_path/...` are ignored. Tests can overwrite real project data.
- Mock tests are not guaranteed to disable `.env` credentials and can call Azure.
- AI tests cover only rule-based mode.
- No dashboard page tests, OpenAI integration tests, Docker runtime tests, or
  cost-reconciliation assertions exist.

## Gap Analysis

### Truly Working

- Client-secret authentication and Azure management token acquisition.
- Direct Cost Management custom query.
- Direct Resource Graph queries.
- Direct Advisor query.
- Local schema validation and JSON/CSV persistence when directories are writable.
- Local anomaly calculation from raw costs.
- Loading the persisted FAISS index.
- Rule-based chat when OpenAI is explicitly disabled.
- Streamlit dashboard process and health endpoint from the dashboard Dockerfile.

### Partially Implemented

- VM and AKS collectors only list resources; they do not collect Monitor metrics.
- Resource Graph uses hard-coded age and price estimates.
- Advisor inserts a synthetic success-looking recommendation when none exist.
- RAG code is structurally present, but current endpoint configuration is invalid.
- Dashboard pages render cached files but do not validate freshness or provenance.
- Full pipeline treats empty/incorrect analytical output as success.

### Mock or Synthetic

- All collectors fall back to `tests/mock_data` after any live exception.
- Waste rules and savings rates are local heuristics.
- Disk age, disk cost, and public IP cost are hard-coded.
- Advisor's "No recommendations" row is synthetic.
- Six generic FinOps documents are always inserted into FAISS.
- Report periods and daily averages are generated locally and can diverge from the
  Cost Management query period.

### Not Real-Time

- Dashboard tabs read persisted files only.
- FAISS and recommendations are cached until manually rebuilt.
- The current dashboard cache predates this audit's live run.
- Chat normally uses cached processed/FAISS context. The staged inventory-routing
  branch is nonfunctional because `_handle_live_inventory` does not exist.

## Production Readiness Checklist

- [ ] Reconcile processed total cost exactly to live Cost Management totals.
- [ ] Preserve aggregate service/RG/location cost rows without presenting them as fake resources.
- [ ] Implement Azure Monitor metric queries for VMs and AKS.
- [ ] Add pagination/continuation handling and explicit retry/backoff for Azure APIs.
- [ ] Replace silent live-to-mock fallback with an explicit mode and surfaced failure/provenance.
- [ ] Add source, collection timestamp, subscription, and freshness to every processed artifact and dashboard page.
- [ ] Return empty Advisor results honestly; do not insert a fake recommendation.
- [ ] Replace hard-coded pricing with documented pricing inputs or Azure pricing data.
- [ ] Validate estimates against SKU, region, term, license, reservations, and savings plans.
- [ ] Fix or remove the missing `_handle_live_inventory` path.
- [ ] Catch OpenAI transport/API exceptions and fall back safely.
- [ ] Correct the Azure OpenAI endpoint/deployments and verify embeddings plus chat live.
- [ ] Rebuild FAISS atomically and bind the manifest to source artifact hashes/timestamps.
- [ ] Avoid `allow_dangerous_deserialization=True` for untrusted index files.
- [ ] Give Compose services distinct image tags.
- [ ] Add missing packages: Resource Graph, Advisor, Compute, Monitor, and Container Service SDKs.
- [ ] Include fixtures only in an explicit demo image/mode; never silently use them in production.
- [ ] Make the pipeline fail when required collectors fail or cost reconciliation fails.
- [ ] Fix `Settings` test construction with `populate_by_name=True` or aliases.
- [ ] Guarantee tests disable `.env` and network access unless marked integration.
- [ ] Add deterministic unit, live integration, dashboard, RAG, and container smoke tests.
- [ ] Make verification scripts return nonzero on failed checks and remove Unicode console assumptions.
- [ ] Pin and test the supported Python version consistently; local audit used Python 3.13 while docs/images specify 3.11.
- [ ] Add secrets management, least-privilege identity, audit logging, observability, retention, and access control.
- [ ] Require all tests, image scans, Terraform validation, and post-deploy health/data checks in CI/CD.

Production-ready status: **NO**.
