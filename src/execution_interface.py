"""
Execution Interface Module
Abstract base class for Paper and Live trading
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class ExecutionInterface(ABC):
    """رابط یکسان برای Paper و Live Trading"""
    
    @abstractmethod
    def execute_buy(self, symbol: str, price: float, stop_loss: float, take_profit: float, size: float) -> bool:
        """اجرای سفارش خرید"""
        pass
    
    @abstractmethod
    def execute_sell(self, symbol: str, price: float, stop_loss: float, take_profit: float, size: float) -> bool:
        """اجرای سفارش فروش"""
        pass
    
    @abstractmethod
    def get_balance(self) -> float:
        """دریافت موجودی"""
        pass
    
    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """دریافت وضعیت یک موقعیت"""
        pass
    
    @abstractmethod
    def get_all_positions(self) -> Dict[str, Dict[str, Any]]:
        """دریافت همه موقعیت‌ها"""
        pass
    
    @abstractmethod
    def close_position(self, symbol: str) -> bool:
        """بستن یک موقعیت"""
        pass
