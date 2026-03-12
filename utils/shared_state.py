"""
Shared State Singleton - Module-level cache for DataFrames between agents
Trạng thái chia sẻ - Cache cấp module cho DataFrames giữa các agent

Since all CrewAI agents run in the same Python process, we use a singleton
to share DataFrames in memory (avoids repeated serialization/deserialization).
Vì tất cả agent CrewAI chạy trong cùng một tiến trình Python, chúng ta dùng
singleton để chia sẻ DataFrames trong bộ nhớ.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import pandas as pd


class SharedState:
    """
    Thread-safe singleton for sharing state between agents.
    Singleton an toàn luồng để chia sẻ trạng thái giữa các agent.
    """

    _instance: Optional["SharedState"] = None

    def __new__(cls) -> "SharedState":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        # OHLCV DataFrames keyed by "SYMBOL_TIMEFRAME"
        # DataFrames OHLCV được đánh key theo "SYMBOL_TIMEFRAME"
        self.data: Dict[str, pd.DataFrame] = {}

        # Timestamp of last update per key
        # Thời gian cập nhật cuối cùng theo key
        self.last_update: Dict[str, str] = {}

        # Latest pattern analysis results per key
        # Kết quả phân tích mẫu giá mới nhất theo key
        self.latest_patterns: Dict[str, List[Dict]] = {}

        # Latest trade decisions per key
        # Quyết định giao dịch mới nhất theo key
        self.latest_decisions: Dict[str, Dict] = {}

        # Latest indicator values per key
        # Giá trị chỉ báo mới nhất theo key
        self.latest_indicators: Dict[str, Dict] = {}

        # Open trade tickets to track
        # Vé giao dịch đang mở để theo dõi
        self.open_tickets: List[int] = []

        # Daily P/L tracker
        # Theo dõi lãi/lỗ trong ngày
        self.daily_pnl: float = 0.0
        self.daily_trades: int = 0

        # Current cycle number
        # Số chu kỳ hiện tại
        self.cycle: int = 0

        # Account balance cache
        # Cache số dư tài khoản
        self.account_balance: float = 10000.0
        self.account_equity: float = 10000.0

        self._initialized = True

    def get_df(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Retrieve DataFrame for a symbol/timeframe pair."""
        return self.data.get(f"{symbol}_{timeframe}")

    def set_df(self, symbol: str, timeframe: str, df: pd.DataFrame) -> None:
        """Store DataFrame and record update timestamp."""
        key = f"{symbol}_{timeframe}"
        self.data[key] = df.copy()
        self.last_update[key] = datetime.now().isoformat()

    def reset_daily(self) -> None:
        """Reset daily counters at midnight / Reset bộ đếm hàng ngày vào nửa đêm."""
        self.daily_pnl = 0.0
        self.daily_trades = 0


# Module-level singleton instance
# Thực thể singleton cấp module
shared_state = SharedState()
