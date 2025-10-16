import numpy as np
import pandas as pd
from ta import momentum, trend, volatility

x = pd.Series(np.linspace(100, 110, 50))
print("RSI ok:", not momentum.RSIIndicator(x, window=14).rsi().dropna().empty)

m = trend.MACD(x)
print("MACD ok:", m.macd().notna().any())

b = volatility.BollingerBands(x, window=20, window_dev=2)
print("BB ok:", b.bollinger_hband().notna().any())
