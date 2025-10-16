from __future__ import annotations
import math

def square_root_impact(q_usd: float, adv_usd: float, sigma: float, zeta: float = 0.8) -> float:
    """
    Fractional price impact (e.g., 0.001 = +10 bps) via square-root law.
    q_usd: trade notional
    adv_usd: average daily dollar volume
    sigma: daily vol (stdev of returns, in fraction, e.g. 0.02 = 2%)
    zeta: impact coefficient
    """
    if q_usd <= 0 or adv_usd <= 0 or sigma <= 0 or zeta <= 0:
        return 0.0
    return float(zeta * sigma * math.sqrt(q_usd / adv_usd))
