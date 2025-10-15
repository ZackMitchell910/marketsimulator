# Market Twin — Entity Simulation MVP

A minimal, **beginner-friendly** starter you can run locally. It simulates a few market entities (fund + retail) trading a synthetic price series, and exposes a small API.

## 0) Prereqs
- Python 3.11+ recommended
- macOS/Linux/WSL or Windows

## 1) Setup (one time)
```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows (PowerShell)
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

## 2) Run a quick simulation (prints summary)
```bash
python -m market_twin.sim.run_sim
```

## 3) Start the API (optional)
```bash
uvicorn market_twin.api.main:app --reload
```
Then open http://127.0.0.1:8000/docs to run `/simulate`.

## 4) Project layout
```
market-twin-mvp/
  ├─ requirements.txt
  ├─ README.md
  └─ src/
     └─ market_twin/
        ├─ __init__.py
        ├─ core/
        │  ├─ types.py
        │  ├─ events.py
        │  └─ utils.py
        ├─ agents/
        │  ├─ base.py
        │  ├─ fund.py
        │  └─ retail.py
        ├─ env/
        │  └─ market.py
        ├─ sim/
        │  └─ run_sim.py
        └─ api/
           └─ main.py
```

## 5) What this does
- Generates a **synthetic price** stream
- Two agents:
  - **FundAgent**: mean-reversion (buys when price < moving average, sells when >)
  - **RetailAgent**: momentum-chasing
- **MarketEnvironment** aggregates orders, updates price by **order imbalance**
- Records simple PnL + trade counts

## 6) Next steps
- Add more agents (whale, market-maker), plug real data, swap rules for RL/transformers.
- Persist runs to a DB, put a dashboard on top.
