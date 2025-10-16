# Digital Market Twin Gap Analysis & Roadmap

This document maps the remaining work required for the Market Simulator to behave like a high-fidelity digital twin of live market structure. Each capability area captures the current baseline, the gaps we need to close, and the tactical tasks that convert the gaps into milestones.

## Summary
- **North Star**: End-to-end replay and forward simulation that replicates exchange-grade microstructure, supports real-time ingestion, and produces explainable agent behavior.
- **Theme Buckets**: Data ingestion, microstructure fidelity, agent calibration, risk management, observability, and deployment readiness.
- **Execution Lens**: Each section includes quick wins (days), foundational builds (weeks), and differentiators (months) to help sequence backlog items.

## Data Ingestion & Quality
- **Current**: CSV/YAML-driven configs, ad hoc fetchers for historical bars, light caching in `data_cache/`.
- **Target**: Multi-venue streaming ingestion (equities, options, futures, FX, crypto) with depth-of-book snapshots, fundamentals, alternative data, and documented lineage.
- **Gaps**
  - No unified data model that normalizes equities, crypto, and synthetic feeds.
  - Missing tick-level ingestion, corporate actions replay, and data quality guards (outlier detection, gap fills).
  - Manual dependency on local files; no data lineage or cataloging.
- **Tasks**
  - Build a `src/data/registry.py` module that declares canonical schemas (bars, quotes, order book snapshots, news).
  - Implement adapters for Polygon, AlphaVantage, and CME (REST + WebSocket) with retry/backoff and unit tests.
  - Add data validation stage: schema checks, missing value handling, and anomaly scoring.
  - Introduce ingest-to-cache jobs with metadata stored in `runs/manifest.json`.
  - Optional: integrate a lightweight metadata store (DuckDB or SQLite) for tracking provenance.

## Market Microstructure Fidelity
- **Current**: Event loop captures simple LOB updates and fills, but lacks depth and auction mechanics.
- **Target**: Venue-aware order books with queue priority, auction phases, latency modeling, fee/rebate schedules, and stress mechanics that mirror live venues.
- **Gaps**
  - No support for multi-level books, iceberg/hidden liquidity, or auction open/close sequences.
  - Latency, queue position effects, and fee schedules are approximated or ignored.
  - No stress or circuit breaker scenarios.
- **Tasks**
  - Extend matching engine to maintain top-of-book plus N levels with queue prioritization.
  - Model exchange session states (pre-open, halt, closing auction) and enforce order validity rules per state.
  - Parameterize venue fees, rebates, and latency; expose them as config knobs.
  - Add scenario templates for halts, volatility pauses, and liquidity droughts.
  - Validate microstructure behavior with replay tests against known exchange logs.

## Agent Calibration & Behavior
- **Current**: Rule-based personas for retail, funds, and ARK-inspired agent; limited calibration tooling.
- **Target**: Adaptive agents calibrated to historical flows with support for reinforcement and imitation learning, stochastic behavior, and explainable metrics.
- **Gaps**
  - Agents lack real market parameter fitting; behavior is deterministic and static.
  - No reinforcement learning loop tied to live data or cross-asset interactions.
  - Strategy evaluation lacks PnL attribution and sensitivity analysis.
- **Tasks**
  - Build calibration pipelines that ingest historical trades/balances to fit agent parameters.
  - Introduce stochastic decision hooks (noise, optional ML policy) to mimic real variability.
  - Add RL training interface that hooks into `runs/` artifacts and saves policies under `models/`.
  - Create cross-agent coordination scenarios (inventory risk sharing, pair trades).
  - Report agent diagnostics (hit rate, slippage, inventory trajectories) per simulation.

## Risk & Portfolio Controls
- **Current**: Basic stop logic per agent; global limits handled via config.
- **Target**: Full-stack risk engine covering VaR/CVaR, liquidity, margin, compliance hooks, and automated escalation workflows.
- **Gaps**
  - Missing VAR/CVAR computation, margin evaluation, and kill-switch playbooks.
  - No stress matrix or scenario-based risk overlay.
  - Lacks portfolio optimization integration for hedging suggestions.
- **Tasks**
  - Implement a `src/risk/engine.py` that computes per-agent and global exposure metrics each tick.
  - Add scenario stress harness that replays adverse price paths and records drawdowns.
  - Surface real-time risk dashboards (position limits, margin headroom) via the API.
  - Hook risk outputs into agent decision loops for dynamic throttling or liquidation.
  - Optional: integrate open-source optimization (cvxpy) for automated hedge recommendations.

## Observability & Telemetry
- **Current**: Basic logging to `runs/` with static metrics and manual inspection.
- **Target**: Structured telemetry with metrics, logs, traces, dashboards, and automated anomaly detection across ingestion, engine, and agents.
- **Gaps**
  - No structured events, traces, or real-time dashboards.
  - Lacks anomaly detection, alerting, and experiment tracking.
  - API returns aggregate metrics but without context or drill-down.
- **Tasks**
  - Standardize structured logs (JSON) for orders, fills, risk events, and scenario triggers.
  - Instrument OpenTelemetry spans across ingestion, engine, and agents; export to configurable sinks.
  - Build a metrics registry (`src/telemetry/metrics.py`) with gauge/counter abstractions.
  - Integrate with Grafana/Prometheus stack or a lightweight FastAPI WebSocket dashboard.
  - Layer experiment tracking (e.g., MLflow) for agent training runs.

## Deployment & Operations
- **Current**: FastAPI app runs locally; infra scripts exist but are not production ready.
- **Target**: Cloud-ready deployment with containerization, managed data pipelines, CI/CD, secrets management, and SLO-backed operations.
- **Gaps**
  - No containerization story across simulation, API, and data workers.
  - Missing CI/CD, environment promotion, and secrets management.
  - Limited documentation for scaling horizontally or handling failover.
- **Tasks**
  - Package services with Docker Compose; define separate services for API, simulation workers, and background ingest.
  - Set up CI pipelines (GitHub Actions) for tests, linting, and container build.
  - Define staging vs production configs and deployment playbooks (Kubernetes or ECS).
  - Document secrets management (Vault, AWS Parameter Store) and rotation process.
  - Add operational runbooks covering monitoring, incident response, and rollback procedures.

## Milestone Cadence
- **Phase 1 (Weeks 1-4)**: Harden data ingestion, basic microstructure upgrades, telemetry foundation.
- **Phase 2 (Weeks 5-10)**: Agent calibration pipelines, risk engine, structured observability.
- **Phase 3 (Weeks 11+)**: Deployment hardening, RL agent incubation, advanced stress and hedging capabilities.

Revisit progress quarterly and validate simulated outputs against real market statistics, compliance expectations, and operational readiness metrics to confirm the twin remains trustworthy.

## Contribution Guidelines
1. Reference this roadmap when opening issues or PRs; tag the relevant capability area.
2. Provide test coverage or replay scripts demonstrating the new behavior.
3. Update `README.md` and sample configs when you add or change capabilities.
4. Keep large artifact downloads optional (guarded behind flags or documented prerequisites).
