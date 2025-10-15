# Market Simulator

MarketSimulator is a multi-agent market laboratory for prototyping backtests, stress scenarios, and real-time trading ideas. It ships with rule-based agents, a configurable matching engine, and a FastAPI service that can feed dashboards and downstream analytics.

## Features
- **Config-driven simulations** that toggle between backtest and realtime modes by swapping YAML files.
- **Agent library** covering retail momentum, mean-reversion funds, and institutional strategies (ARK-inspired, dealer, etc.).
- **Realtime I/O** pipeline that can ingest live ticks, push events into `runs/`, and expose the latest metrics over HTTP.
- **Extensible FastAPI service** with static dashboard mounting, recent-event buffers, and simple health endpoints.

## Quick Start
1. Install Python 3.11 or newer.
2. (Recommended) Create a virtual environment:
   ```bash
   python -m venv .venv
   # macOS / Linux
   source .venv/bin/activate
   # Windows (PowerShell)
   .venv\Scripts\Activate.ps1
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Run a Simulation
The simulation runner expects a YAML config describing the mode, agents, and data sources.

```bash
python -m src.sim.run_sim configs/daily_backtest_spy_nvda.yaml
```

For the realtime demo (e.g., crypto quotes):
```bash
python -m src.sim.run_sim configs/realtime_crypto.yaml
```

The engine prints a summary once the run completes. Outputs (fills, metrics, logs) land under `runs/`.

## Start the API
Launch the FastAPI app (with hot reload) from the repository root:
```bash
uvicorn api.main:app --reload --app-dir src
```

Endpoints of note:
- `GET /health` – basic readiness check.
- `POST /ingest` – push snapshots/events from realtime agents.
- `GET /recent?n=50` – ring buffer of the latest events.
- `GET /metrics` – returns the newest `metrics.json` under `runs/`.
- `GET /dashboard` – serves static assets from `src/dashboard` if present.

## Configuration Guide
Each YAML file under `configs/` maps directly onto the simulation builder. Common keys:

| Key            | Purpose                                                    |
| -------------- | ----------------------------------------------------------- |
| `mode`         | `"backtest"`, `"live"`, or `"realtime"` toggles engine type |
| `symbols`      | Universe (list of tickers)                                  |
| `agents`       | Enables specific agent classes (e.g., `fund`, `retail`, `ark`) |
| `providers`    | Data sources for realtime runs (e.g., `yfinance`, `polygon`) |
| `max_ticks`    | Safety stop for realtime loops                              |
| `account` / `dealer` / `strategy` | Agent-specific knobs per sample config   |

Use `configs/daily_backtest_spy_nvda.yaml` as a baseline for historical runs, and `configs/intraday_spy_nvda.yaml` for live-ish intraday experiments.

## Project Layout
```
MarketSimulator/
  configs/            Example YAML scenarios for backtests and realtime modes
  data_cache/         Local cache for fetched data (ignored by git)
  infra/              Deployment helpers and scripts
  models/             Saved ML models and checkpoints
  runs/               Simulation artifacts (logs, metrics, fills)
  src/
    agents/           Agent implementations (fund, retail, institutional, RL)
    api/              FastAPI application surface
    core/, env/, sim/ Matching engine, environments, and run loop
    dashboard/        Optional static dashboard assets served by the API
    telemetry/        Telemetry primitives and sinks
  tools/              Utility scripts and notebooks
  requirements.txt    Base Python dependencies
```

## Development Notes
- Set `PYTHONPATH=src` (or rely on `--app-dir src`) when running ad-hoc modules.
- `python sanity_check.py` will import heavy dependencies (TensorFlow, Torch, TA-Lib, Stable Baselines) to make sure your environment is ready.
- `forecast.json`, `data_cache/`, and other large artifacts are meant to stay local; they will be ignored by git once you add the provided `.gitignore`.

## Next Steps
- Wire in real market data providers and expand the `providers` map.
- Add unit tests (consider `pytest`) for agents, event handling, and the matching engine.
- Drop a built dashboard bundle under `src/dashboard/` or connect the API to your visualization stack.
