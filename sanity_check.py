import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, GRU, Attention, Dense
import talib, gym, statsmodels.api as sm, torch
from stable_baselines3 import DQN

print("TF:", tf.__version__)
print("Torch:", torch.__version__)
print("Gym:", gym.__version__)
print("TA-Lib OK:", len(talib.get_functions()))
print("Statsmodels:", sm.__version__)
print("SB3 OK:", DQN is not None)
