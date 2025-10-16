# src/sim/run_sim.py
from __future__ import annotations

import sys
import os
import yaml
import asyncio
from pprint import pprint
from typing import Any, Dict, List

# Ensure 'src' is importable when running as a module
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Agents (your current set)
from agents.fund import FundAgent
from agents.retail_agent import RetailAgent
from agents.institutional.ark_agent import ArkAgent

# Environments
from env.market import MarketEnvironment, MarketConfig
from env.realtime_env import RealtimeEnvironment, RealtimeConfig
# add near the top, after imports
import logging, json, hashlib, random

logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("charset_normalizer").setLevel(logging.ERROR)


def _cfg_checksum(cfg: dict) -> str:
    # stable-ish hash for repro
    payload = json.dumps(cfg, sort_keys=True, default=str).encode()
    return hashlib.sha256(payload).hexdigest()[:12]


def build_agents(cfg: Dict[str, Any]) -> List[Any]:
    agents: List[Any] = []
    agent_list = cfg.get("agents", [])  # e.g., ['fund', 'retail', 'ark']

    if "fund" in agent_list:
        agents.append(FundAgent(agent_id="fund-1", span=30, threshold_bps=25, max_qty=120))

    if "retail" in agent_list:
        agents.append(RetailAgent(agent_id="retail-1", lookback=5, trade_qty=2.0, max_qty=40))

    if "ark" in agent_list:
        agents.append(ArkAgent(agent_id="arkk", etf="ARKK", cash=1_000_000.0))

    return agents


def run_backtest(cfg: Dict[str, Any], agents: List[Any]) -> Any:
    # Minimal MarketConfig; extend with start/end/timespan/etc. as your env supports
    mk_conf = MarketConfig(steps=cfg.get("max_ticks", 500))
    env = MarketEnvironment(agents=agents, config=mk_conf)
    return env.run()  # sync


def run_realtime(cfg: Dict[str, Any], agents: List[Any]) -> Any:
    # Map common keys defensively
    symbols = cfg.get("symbols") or ["BTC-USD"]
    providers = cfg.get("providers") or {}

    rt_conf = RealtimeConfig(
        symbols=list(symbols),
        providers=providers,
        max_ticks=cfg.get("max_ticks"),
        timeout_s=cfg.get("timeout_s"),
        heartbeat_s=cfg.get("heartbeat_s", 5.0),
    )
    env = RealtimeEnvironment(agents=agents, config=rt_conf)

    # IMPORTANT: async run
    return asyncio.run(env.run())


def main(config_path: str) -> None:
    with open(config_path, "r", encoding="utf-8") as f:
        cfg: Dict[str, Any] = yaml.safe_load(f) or {}

    mode = (cfg.get("mode") or "backtest").lower()
    agents = build_agents(cfg)
    # inside main(cfg_path: str), right after loading cfg
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    seed = int(cfg.get("seed", 42))
    random.seed(seed); np_seed = seed  # if you use numpy, set where used
    print(f"▶︎ mode={mode}  seed={seed}  cfg_hash={_cfg_checksum(cfg)}")

    if mode in ("live", "realtime"):
        result = run_realtime(cfg, agents)
        print("\n=== Simulation Summary (Realtime) ===")
        pprint(result)
    else:
        result = run_backtest(cfg, agents)
        print("\n=== Simulation Summary (Backtest) ===")
        pprint(result)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        print("Usage: python -m src.sim.run_sim <config.yaml>")
