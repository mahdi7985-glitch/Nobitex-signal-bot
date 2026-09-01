"""
Trade Logger Module
ذخیره کامل اطلاعات هر معامله در فایل CSV
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Union

logger = logging.getLogger(__name__)

# ================================================
# تنظیمات
# ================================================
CSV_FILE = Path("logs") / "trades_log.csv"
CSV_HEADERS = [
    "trade_id",
    "symbol",
    "side",
    "entry_price",
    "exit_price",
    "stop_loss",
    "take_profit",
    "entry_time",
    "exit_time",
    "exit_reason",
    "quantity",
    "risk_amount",
    "gross_pnl",
    "fees",
    "net_pnl",
    "rr_planned",
    "rr_actual",
    "duration_minutes",
    "signal_score",
    "rsi",
    "macd_line",
    "macd_signal",
    "adx",
    "strategy_version",
    "notes"
]


def _get_trade_id() -> int:
    """ایجاد ID ترتیبی برای معاملات"""
    if not CSV_FILE.exists():
        return 1
    
    try:
        import pandas as pd
        df = pd.read_csv(CSV_FILE)
        if len(df) > 0:
            return int(df['trade_id'].max()) + 1
    except:
        pass
    
    # روش جایگزین: شمارش خطوط
    try:
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            return len(lines)  # اولین خط هدر هست
    except:
        return 1


def _format_time(time_val: Union[str, datetime, None]) -> str:
    """یکدست‌سازی فرمت زمان"""
    if time_val is None:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if isinstance(time_val, datetime):
        return time_val.strftime("%Y-%m-%d %H:%M:%S")
    
    return str(time_val)


def init_csv():
    """ایجاد فایل CSV با هدر (اگه وجود نداشته باشه)"""
    try:
        CSV_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        if not CSV_FILE.exists():
            with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(CSV_HEADERS)
            logger.info(f"✅ فایل CSV ایجاد شد: {CSV_FILE}")
    except Exception as e:
        logger.error(f"❌ خطا در ایجاد فایل CSV: {e}")


def log_trade(
    symbol: str,
    side: str,
    entry_price: float,
    exit_price: float,
    stop_loss: float,
    take_profit: float,
    entry_time: Union[str, datetime, None] = None,
    exit_time: Union[str, datetime, None] = None,
    exit_reason: str = "MANUAL",
    quantity: float = 0.0,
    risk_amount: float = 0.0,
    gross_pnl: float = 0.0,
    fees: float = 0.0,
    net_pnl: float = 0.0,
    rr_planned: float = 0.0,
    rr_actual: float = 0.0,
    duration_minutes: float = 0.0,
    signal_score: Optional[float] = None,
    rsi: Optional[float] = None,
    macd_line: Optional[float] = None,
    macd_signal: Optional[float] = None,
    adx: Optional[float] = None,
    strategy_version: str = "v1.0",
    notes: str = ""
) -> bool:
    """
    ثبت یک معامله کامل در فایل CSV
    
    Returns:
        True در صورت موفقیت، False در صورت خطا
    """
    try:
        # اطمینان از وجود فایل
        init_csv()
        
        # یکدست‌سازی زمان‌ها
        entry_time_str = _format_time(entry_time)
        exit_time_str = _format_time(exit_time)
        
        # تولید ID خودکار
        trade_id = _get_trade_id()
        
        # رند کردن اعداد
        def r(v, d=8):
            return round(v, d) if v is not None else ""
        
        # آماده‌سازی ردیف
        row = [
            trade_id,
            symbol.upper(),
            side.upper(),
            r(entry_price, 8),
            r(exit_price, 8),
            r(stop_loss, 8),
            r(take_profit, 8),
            entry_time_str,
            exit_time_str,
            exit_reason.upper(),
            r(quantity, 4),
            r(risk_amount, 2),
            r(gross_pnl, 2),
            r(fees, 2),
            r(net_pnl, 2),
            r(rr_planned, 2),
            r(rr_actual, 2),
            r(duration_minutes, 1),
            r(signal_score, 1) if signal_score is not None else "",
            r(rsi, 1) if rsi is not None else "",
            r(macd_line, 6) if macd_line is not None else "",
            r(macd_signal, 6) if macd_signal is not None else "",
            r(adx, 1) if adx is not None else "",
            strategy_version,
            notes
        ]
        
        # نوشتن در فایل
        with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(row)
        
        logger.info(f"✅ معامله {symbol} با ID {trade_id} در CSV ثبت شد")
        return True
        
    except Exception as e:
        logger.error(f"❌ خطا در ثبت CSV: {e}")
        return False


def get_trades_dataframe():
    """
    دریافت داده‌های CSV به صورت DataFrame (برای تحلیل)
    نیاز به pandas داره
    """
    try:
        import pandas as pd
        if CSV_FILE.exists():
            return pd.read_csv(CSV_FILE)
        return pd.DataFrame(columns=CSV_HEADERS)
    except ImportError:
        logger.warning("⚠️ pandas نصب نیست")
        return None


def get_summary_stats() -> Dict[str, Any]:
    """
    دریافت آمار خلاصه از معاملات
    """
    try:
        import pandas as pd
        if not CSV_FILE.exists():
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0,
                "total_pnl": 0,
                "avg_pnl": 0,
                "best_trade": 0,
                "worst_trade": 0,
                "avg_rr_actual": 0,
                "total_fees": 0,
                "total_gross_pnl": 0
            }
        
        df = pd.read_csv(CSV_FILE)
        
        if len(df) == 0:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0,
                "total_pnl": 0,
                "avg_pnl": 0,
                "best_trade": 0,
                "worst_trade": 0,
                "avg_rr_actual": 0,
                "total_fees": 0,
                "total_gross_pnl": 0
            }
        
        winning = df[df['net_pnl'] > 0]
        losing = df[df['net_pnl'] < 0]
        
        return {
            "total_trades": len(df),
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "win_rate": len(winning) / len(df) if len(df) > 0 else 0,
            "total_pnl": df['net_pnl'].sum(),
            "avg_pnl": df['net_pnl'].mean(),
            "best_trade": df['net_pnl'].max(),
            "worst_trade": df['net_pnl'].min(),
            "avg_rr_actual": df['rr_actual'].mean() if 'rr_actual' in df.columns else 0,
            "total_fees": df['fees'].sum() if 'fees' in df.columns else 0,
            "total_gross_pnl": df['gross_pnl'].sum() if 'gross_pnl' in df.columns else 0
        }
    except Exception as e:
        logger.error(f"❌ خطا در دریافت آمار: {e}")
        return {"total_trades": 0}


def print_summary():
    """چاپ خلاصه آمار به صورت خوانا"""
    stats = get_summary_stats()
    
    if stats.get("total_trades", 0) == 0:
        print("\n📊 هیچ معامله‌ای ثبت نشده است.")
        return
    
    print("\n" + "="*50)
    print("📊 خلاصه عملکرد معاملات")
    print("="*50)
    print(f"📊 تعداد کل معاملات: {stats['total_trades']}")
    print(f"✅ معاملات برنده: {stats['winning_trades']}")
    print(f"❌ معاملات بازنده: {stats['losing_trades']}")
    print(f"🎯 نرخ برد: {stats['win_rate']*100:.1f}%")
    print(f"💰 سود ناخالص کل: {stats['total_gross_pnl']:.2f} USDT")
    print(f"💰 کارمزد کل: {stats['total_fees']:.2f} USDT")
    print(f"💰 سود خالص کل: {stats['total_pnl']:.2f} USDT")
    print(f"📈 میانگین سود: {stats['avg_pnl']:.2f} USDT")
    print(f"🏆 بهترین معامله: {stats['best_trade']:.2f} USDT")
    print(f"💔 بدترین معامله: {stats['worst_trade']:.2f} USDT")
    print(f"⚖️ میانگین RR واقعی: {stats['avg_rr_actual']:.2f}")
    print("="*50)
