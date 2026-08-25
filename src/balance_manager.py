"""
Balance Manager Module
Manages persistent balance storage across bot runs
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import Config

logger = logging.getLogger(__name__)


class BalanceManager:
    """
    مدیریت ذخیره و بازیابی موجودی بین سیکل‌ها و معاملات
    """
    
    def __init__(self, config=Config):
        self.config = config
        self.balance_file = config.DATA_DIR / "balance.json"
        self.initial_balance = 530.0
        self._balance = self._load_balance()
    
    def _load_balance(self) -> float:
        """بارگذاری موجودی از فایل"""
        if self.balance_file.exists():
            try:
                with open(self.balance_file, 'r') as f:
                    data = json.load(f)
                    balance = data.get('balance', self.initial_balance)
                    updated_at = data.get('updated_at', 'unknown')
                    logger.info(f"💰 Loaded balance from file: {balance:.2f} USDT (updated: {updated_at})")
                    return balance
            except Exception as e:
                logger.error(f"Error loading balance: {e}")
        
        logger.info(f"💰 Using initial balance: {self.initial_balance:.2f} USDT")
        return self.initial_balance
    
    def save_balance(self, balance: float):
        """ذخیره موجودی در فایل"""
        try:
            self.balance_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.balance_file, 'w') as f:
                json.dump({
                    'balance': balance,
                    'updated_at': datetime.now().isoformat(),
                    'initial_balance': self.initial_balance
                }, f, indent=2)
            self._balance = balance
            logger.info(f"💰 Saved balance: {balance:.2f} USDT")
        except Exception as e:
            logger.error(f"Error saving balance: {e}")
    
    def get_balance(self) -> float:
        """دریافت موجودی فعلی"""
        return self._balance
    
    def update_balance(self, new_balance: float):
        """به‌روزرسانی موجودی و ذخیره در فایل"""
        self._balance = new_balance
        self.save_balance(new_balance)
    
    def reset_balance(self, balance: Optional[float] = None):
        """بازنشانی موجودی به مقدار اولیه یا مقدار مشخص"""
        if balance is None:
            balance = self.initial_balance
        self.update_balance(balance)
        logger.info(f"🔄 Balance reset to: {balance:.2f} USDT")
