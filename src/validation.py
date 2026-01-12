"""
Data validation utilities to prevent inflated or invalid values in the application.
"""
import numpy as np
import pandas as pd
from typing import Optional, Union, Tuple, Dict, Any
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Reasonable bounds for financial data
FINANCIAL_BOUNDS = {
    'price': (0.01, 1_000_000),  # Min and max price per share
    'volume': (0, 10_000_000_000),  # Min and max volume
    'pct_change': (-100, 100),  # Percentage change bounds (-100% to +100%)
    'rsi': (0, 100),  # RSI bounds (0-100)
    'iv': (0, 500),  # Implied volatility bounds (0-500%)
    'quantity': (0, 10_000_000),  # Reasonable position size limit
}

def validate_financial_value(
    value: Union[float, int, str, None], 
    value_type: str,
    symbol: str = 'unknown',
    date: Optional[Union[str, datetime]] = None
) -> Optional[float]:
    """
    Validate a financial value against expected bounds.
    
    Args:
        value: The value to validate
        value_type: Type of financial value (e.g., 'price', 'volume', 'pct_change')
        symbol: Symbol/identifier for logging
        date: Optional date for logging
        
    Returns:
        Validated value or None if invalid
    """
    if value is None or pd.isna(value):
        return None
        
    try:
        # Convert to float, handling string representations
        value_float = float(value) if not isinstance(value, (int, float)) else value
        
        # Get bounds for this value type
        bounds = FINANCIAL_BOUNDS.get(value_type, (None, None))
        min_val, max_val = bounds
        
        # Check bounds
        if min_val is not None and value_float < min_val:
            logger.warning(
                f"Value {value_float} for {value_type} is below minimum {min_val}. "
                f"Symbol: {symbol}, Date: {date}"
            )
            return None
            
        if max_val is not None and value_float > max_val:
            logger.warning(
                f"Value {value_float} for {value_type} exceeds maximum {max_val}. "
                f"Symbol: {symbol}, Date: {date}"
            )
            return None
            
        return value_float
        
    except (ValueError, TypeError) as e:
        logger.error(f"Error validating {value_type} value {value}: {e}")
        return None

def detect_outliers(
    series: pd.Series, 
    z_threshold: float = 3.0,
    iqr_factor: float = 1.5
) -> pd.Series:
    """
    Detect outliers in a pandas Series using Z-score and IQR methods.
    
    Args:
        series: Input data series
        z_threshold: Z-score threshold for outlier detection
        iqr_factor: IQR multiplier for outlier detection
        
    Returns:
        Boolean mask where True indicates an outlier
    """
    if series.empty or len(series) < 2:
        return pd.Series(False, index=series.index)
    
    # Z-score method
    z_scores = (series - series.mean()) / series.std()
    z_outliers = abs(z_scores) > z_threshold
    
    # IQR method (more robust for non-normal distributions)
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    lower_bound = q1 - (iqr * iqr_factor)
    upper_bound = q3 + (iqr * iqr_factor)
    iqr_outliers = (series < lower_bound) | (series > upper_bound)
    
    # Consider a point an outlier if either method flags it
    return z_outliers | iqr_outliers

def validate_ohlcv_data(
    df: pd.DataFrame,
    symbol: str = 'unknown',
    require_all_columns: bool = True
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Validate OHLCV (Open, High, Low, Close, Volume) data.
    
    Args:
        df: DataFrame containing OHLCV data
        symbol: Symbol/identifier for logging
        require_all_columns: If True, raises ValueError if required columns are missing
        
    Returns:
        Tuple of (validated_df, stats) where stats contains validation metrics
    """
    required_columns = ['open', 'high', 'low', 'close', 'volume']
    stats = {
        'total_rows': len(df),
        'invalid_rows': 0,
        'price_errors': 0,
        'volume_errors': 0,
        'outliers_detected': 0,
        'date_range': (None, None)
    }
    
    if df.empty:
        return df, stats
    
    # Make a copy to avoid modifying the original
    df = df.copy()
    
    # Check for required columns
    missing_cols = [col for col in required_columns if col not in df.columns]
    if missing_cols and require_all_columns:
        raise ValueError(f"Missing required columns: {', '.join(missing_cols)}")
    
    # Ensure date index is available
    date_col = None
    date_values = None
    
    # Try to find a date column if index is not datetime
    if not isinstance(df.index, pd.DatetimeIndex):
        date_cols = ['date', 'datetime', 'time', 'timestamp', '交易日期', '日期']
        for dc in date_cols:
            if dc in df.columns:
                date_col = dc
                date_values = pd.to_datetime(df[dc], errors='coerce')
                if not date_values.isna().all():
                    break
                date_col = None
    else:
        date_values = df.index
    
    # Track valid rows
    valid_mask = pd.Series(True, index=df.index)
    
    # Validate price columns
    price_cols = [col for col in ['open', 'high', 'low', 'close'] if col in df.columns]
    if price_cols:
        for col in price_cols:
            # Check for negative prices
            price_mask = df[col] > 0
            stats['price_errors'] += (~price_mask).sum()
            valid_mask &= price_mask
            
            # Check for high-low consistency
            if 'high' in df.columns and 'low' in df.columns:
                hl_mask = df['high'] >= df['low']
                stats['price_errors'] += (~hl_mask).sum()
                valid_mask &= hl_mask
            
            # Check for open/close within high/low
            if 'high' in df.columns and 'open' in df.columns:
                oh_mask = df['high'] >= df['open']
                valid_mask &= oh_mask
                
            if 'high' in df.columns and 'close' in df.columns:
                ch_mask = df['high'] >= df['close']
                valid_mask &= ch_mask
                
            if 'low' in df.columns and 'open' in df.columns:
                ol_mask = df['low'] <= df['open']
                valid_mask &= ol_mask
                
            if 'low' in df.columns and 'close' in df.columns:
                cl_mask = df['low'] <= df['close']
                valid_mask &= cl_mask
    
    # Validate volume
    if 'volume' in df.columns:
        volume_mask = df['volume'] >= 0
        stats['volume_errors'] += (~volume_mask).sum()
        valid_mask &= volume_mask
    
    # Apply validation
    stats['invalid_rows'] = (~valid_mask).sum()
    df_valid = df[valid_mask].copy()
    
    # Detect and log outliers
    if not df_valid.empty and len(df_valid) > 5:  # Need enough points for outlier detection
        for col in price_cols + (['volume'] if 'volume' in df_valid.columns else []):
            outliers = detect_outliers(df_valid[col])
            if outliers.any():
                stats['outliers_detected'] += outliers.sum()
                if date_values is not None:
                    outlier_dates = date_values[valid_mask][outliers].astype(str).tolist()
                    logger.warning(
                        f"Detected {outliers.sum()} outliers in {col} for {symbol}. "
                        f"Dates: {', '.join(outlier_dates[:5])}{'...' if outliers.sum() > 5 else ''}"
                    )
    
    # Update date range in stats
    if date_values is not None and not date_values[valid_mask].empty:
        stats['date_range'] = (
            date_values[valid_mask].min().strftime('%Y-%m-%d'),
            date_values[valid_mask].max().strftime('%Y-%m-%d')
        )
    
    return df_valid, stats

def sanitize_api_response(data: Union[dict, list], max_depth: int = 3) -> Union[dict, list]:
    """
    Recursively sanitize API response data to prevent injection and ensure data types.
    
    Args:
        data: Input data (dict or list)
        max_depth: Maximum recursion depth
        
    Returns:
        Sanitized data
    """
    if max_depth < 0:
        return "[Max depth exceeded]"
    
    if isinstance(data, dict):
        return {
            str(k): sanitize_api_response(v, max_depth - 1) 
            for k, v in data.items()
        }
    elif isinstance(data, list):
        return [sanitize_api_response(item, max_depth - 1) for item in data]
    elif isinstance(data, (int, float)):
        # Handle potential NaN or infinity
        if pd.isna(data) or np.isinf(data):
            return None
        return float(data)
    elif isinstance(data, str):
        # Basic XSS prevention
        return data.replace('<', '&lt;').replace('>', '&gt;')
    elif data is None or isinstance(data, (bool, int, float)):
        return data
    else:
        return str(data)

# Add this to the validation utilities
def validate_percentage(value: Union[float, int, str, None], name: str = 'percentage') -> Optional[float]:
    """
    Validate that a percentage value is within 0-100 range.
    
    Args:
        value: The percentage value to validate
        name: Name of the percentage field for error messages
        
    Returns:
        Validated percentage or None if invalid
    """
    if value is None or pd.isna(value):
        return None
        
    try:
        pct = float(value)
        if not (0 <= pct <= 100):
            logger.warning(f"{name} value {pct} is outside valid range (0-100)")
            return None
        return pct
    except (ValueError, TypeError):
        logger.warning(f"Invalid {name} value: {value}")
        return None

# Add this to the validation utilities
def validate_positive_number(
    value: Union[float, int, str, None], 
    name: str = 'value',
    allow_zero: bool = True
) -> Optional[float]:
    """
    Validate that a number is positive.
    
    Args:
        value: The value to validate
        name: Name of the field for error messages
        allow_zero: Whether zero is considered valid
        
    Returns:
        Validated number or None if invalid
    """
    if value is None or pd.isna(value):
        return None
        
    try:
        num = float(value)
        if num < 0 or (not allow_zero and num == 0):
            logger.warning(f"{name} must be {'positive' if not allow_zero else 'non-negative'}: {value}")
            return None
        return num
    except (ValueError, TypeError):
        logger.warning(f"Invalid {name}: {value}")
        return None
