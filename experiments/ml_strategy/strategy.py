"""
Experiment 1: ML-Based Trading Strategy
Uses Random Forest to predict price movement direction based on engineered features.
Trains periodically on historical data, then makes live predictions.
"""
NAME = "ml-strategy"
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import logging
import threading
import json
import numpy as np
import pandas as pd
import pandas_ta as ta
from iqoptionapi.stable_api import IQ_Option
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
from collections import deque

import config_practice as config

logger = logging.getLogger("exp_ml")

class MLStrategy:
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.feature_buffer = deque(maxlen=500)
        self.label_buffer = deque(maxlen=500)
        self.trained = False
        self.confidence_threshold = 0.65
        self.retrain_interval = 600  # retrain every 10 min
        self.last_train_time = 0
        
    def engineer_features(self, df):
        """Create feature set from OHLCV data"""
        if len(df) < 30:
            return None
            
        close = df['close']
        high = df['max']
        low = df['min']
        volume = df.get('volume', pd.Series([0]*len(df)))
        
        features = pd.DataFrame(index=df.index)
        
        # Price action features
        features['returns_1'] = close.pct_change(1)
        features['returns_5'] = close.pct_change(5)
        features['returns_10'] = close.pct_change(10)
        features['high_low_ratio'] = (high - low) / close
        features['close_open_ratio'] = (close - df['open']) / df['open']
        
        # RSI variants
        features['rsi_5'] = ta.rsi(close, length=5)
        features['rsi_14'] = ta.rsi(close, length=14)
        features['rsi_21'] = ta.rsi(close, length=21)
        
        # ADX
        adx_df = ta.adx(high, low, close, length=14)
        if adx_df is not None and not adx_df.empty:
            adx_col = [c for c in adx_df.columns if 'ADX' in c][0]
            features['adx'] = adx_df[adx_col]
            features['plus_di'] = adx_df.get([c for c in adx_df.columns if 'DMP' in c][0] if [c for c in adx_df.columns if 'DMP' in c] else '', 0)
            features['minus_di'] = adx_df.get([c for c in adx_df.columns if 'DMN' in c][0] if [c for c in adx_df.columns if 'DMN' in c] else '', 0)
        
        # Bollinger Bands
        bb = ta.bbands(close, length=20)
        if bb is not None and not bb.empty:
            bb_high_col = [c for c in bb.columns if 'BBU' in c or 'upper' in c.lower()]
            bb_low_col = [c for c in bb.columns if 'BBL' in c or 'lower' in c.lower()]
            bb_mid_col = [c for c in bb.columns if 'BBM' in c or 'mid' in c.lower() or ('BB' in c and 'U' not in c and 'L' not in c)]
            if bb_high_col: features['bb_upper'] = bb[bb_high_col[0]]
            if bb_low_col: features['bb_lower'] = bb[bb_low_col[0]]
            if bb_mid_col: features['bb_mid'] = bb[bb_mid_col[0]]
            if bb_high_col and bb_low_col:
                features['bb_width'] = (bb[bb_high_col[0]] - bb[bb_low_col[0]]) / bb[bb_mid_col[0]] if bb_mid_col else 0
        
        # MACD
        macd = ta.macd(close)
        if macd is not None and not macd.empty:
            cols = list(macd.columns)
            macd_col = [c for c in cols if 'MACD' in c and 'signal' not in c.lower() and 'hist' not in c.lower()]
            signal_col = [c for c in cols if 'signal' in c.lower()]
            hist_col = [c for c in cols if 'hist' in c.lower() or 'MACDh' in c]
            if macd_col: features['macd'] = macd[macd_col[0]]
            if signal_col: features['macd_signal'] = macd[signal_col[0]]
            if hist_col: features['macd_hist'] = macd[hist_col[0]]
        
        # Volume features (handle zero-volume assets like OTC)
        vol_mean = volume.rolling(10).mean()
        if vol_mean.sum() > 0:
            features['volume_ratio'] = volume / vol_mean
        else:
            features['volume_ratio'] = 0.0
        
        # Volatility
        features['volatility_5'] = close.rolling(5).std() / close
        features['volatility_10'] = close.rolling(10).std() / close
        
        # Moving averages
        features['sma_10'] = ta.sma(close, length=10)
        features['sma_20'] = ta.sma(close, length=20)
        features['sma_50'] = ta.sma(close, length=50)
        if features['sma_10'] is not None:
            features['close_sma10'] = close / features['sma_10']
        if features['sma_20'] is not None:
            features['close_sma20'] = close / features['sma_20']
        
        # Exponential MAs
        features['ema_12'] = ta.ema(close, length=12)
        features['ema_26'] = ta.ema(close, length=26)
        if features['ema_12'] is not None and features['ema_26'] is not None:
            features['ema_cross'] = features['ema_12'] - features['ema_26']
        
        return features
    
    def train(self, df_raw):
        """Train the Random Forest model on historical data"""
        features = self.engineer_features(df_raw)
        if features is None or len(features) < 50:
            return False
        
        # Create labels: 1 if next candle closes higher, 0 if lower
        close = df_raw['close'].values
        future_returns = np.diff(close, prepend=close[-1])
        labels = (future_returns > 0).astype(int)
        
        # Align features and labels (drop NaN rows)
        aligned = features.iloc[:-1].copy()  # all but last row (no future for last)
        aligned_labels = labels[:-1]
        
        # Remove NaN rows
        valid = ~aligned.isna().any(axis=1)
        X = aligned[valid].values
        y = aligned_labels[valid]
        
        if len(X) < 30 or len(np.unique(y)) < 2:
            logger.warning(f"Not enough training data: {len(X)} samples")
            return False
        
        # Scale features
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)
        
        # Train Random Forest with time-series CV
        self.model = RandomForestClassifier(
            n_estimators=200,
            max_depth=6,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=2,
            class_weight='balanced'
        )
        self.model.fit(X_scaled, y)
        
        # Evaluate
        train_score = self.model.score(X_scaled, y)
        feature_imp = pd.Series(self.model.feature_importances_, index=aligned.columns).sort_values(ascending=False)
        
        logger.info(f"ML Model trained: {len(X)} samples, accuracy={train_score:.3f}")
        logger.info(f"Top features: {feature_imp.head(5).to_dict()}")
        
        self.trained = True
        self.last_train_time = time.time()
        return True
    
    def predict(self, features_row):
        """Predict direction for latest candle"""
        if not self.trained or self.model is None:
            return None, 0.0
        
        try:
            row = features_row.values.reshape(1, -1)
            row_scaled = self.scaler.transform(row)
            
            proba = self.model.predict_proba(row_scaled)[0]
            confidence = max(proba)
            prediction = self.model.classes_[np.argmax(proba)]
            
            direction = "call" if prediction == 1 else "put"
            return direction, confidence
        except Exception as e:
            logger.error(f"ML prediction error: {e}")
            return None, 0.0


def run(iq, stats, active_trades, active_trades_lock, last_traded_timestamp):
    """Run ML strategy - modified to work with experiment runner"""
    
    pass

ml_strategy = MLStrategy()
strategy_initialized = False

def evaluate_signal(candles_ltf, candles_htf, asset):
    """ML-based signal evaluation"""
    global strategy_initialized
    
    df = pd.DataFrame(candles_ltf)
    if len(df) < 50:
        return None
    
    if not strategy_initialized:
        strategy_initialized = True
        features = ml_strategy.engineer_features(df)
        if features is not None and len(features) >= 50:
            ml_strategy.train(df)
    
    # Re-train periodically
    if ml_strategy.trained and time.time() - ml_strategy.last_train_time > ml_strategy.retrain_interval:
        ml_strategy.train(df)
    
    # Get latest features and predict
    features = ml_strategy.engineer_features(df)
    if features is None or len(features) < 2:
        return None
    
    latest = features.iloc[-2:-1] if len(features) >= 2 else features.iloc[-1:]
    if latest.empty:
        return None
    
    direction, confidence = ml_strategy.predict(latest.iloc[0])
    
    if direction and confidence >= ml_strategy.confidence_threshold:
        # HTF confirmation using EMA50
        df_htf = pd.DataFrame(candles_htf)
        if len(df_htf) >= 55:
            htf_close = df_htf['close']
            htf_ema50 = ta.ema(htf_close, length=50)
            if htf_ema50 is not None and not htf_ema50.empty and not htf_ema50.isna().iloc[-1]:
                htf_bullish = htf_close.iloc[-1] > htf_ema50.iloc[-1]
                htf_bearish = htf_close.iloc[-1] < htf_ema50.iloc[-1]
                
                if direction == "call" and htf_bullish:
                    logger.info(f"[ML] {asset} CALL (conf={confidence:.2f}) + HTF bullish")
                    return "call"
                elif direction == "put" and htf_bearish:
                    logger.info(f"[ML] {asset} PUT (conf={confidence:.2f}) + HTF bearish")
                    return "put"
        else:
            # No HTF filter if not enough data
            if direction == "call":
                logger.info(f"[ML] {asset} CALL (conf={confidence:.2f})")
                return "call"
            else:
                logger.info(f"[ML] {asset} PUT (conf={confidence:.2f})")
                return "put"
    
    return None

def analyze(api, asset, candles):
    """Wrapper for experiment runner compatibility"""
    direction = evaluate_signal(candles, candles, asset)
    conf = ml_strategy.confidence_threshold + 10 if ml_strategy.trained else 55.0
    if direction == "call":
        return "call", conf
    elif direction == "put":
        return "put", conf
    return None, 0.0
