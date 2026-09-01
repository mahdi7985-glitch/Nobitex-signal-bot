"""
Main Application Module
Orchestrates all components: data fetching, analysis, AI, and messaging
"""

import logging
import time
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional

from config import Config
from src.data_fetcher import NobitexDataFetcher
from src.signal_engine import SignalEngine
from src.news_reader import NewsReader
from src.ai_analyzer import AIAnalyzer
from src.bale_bot import BaleBot
from src.formatter import MessageFormatter
from src.performance_tracker import PerformanceTracker
from src.paper_trader import PaperTrader
from src.state_manager import (
    load_state, save_state, open_position,
    close_position, check_exit_conditions,
    get_total_pnl, get_performance_summary,
    get_position_info, update_unrealized_pnl
)

logger = logging.getLogger(__name__)


class CryptoSignalBot:
    """
    ربات اصلی سیگنال‌دهی رمزارز
    """
    
    def __init__(self, config=Config):
        self.config = config
        
        # =========================
        # راه‌اندازی ماژول‌ها
        # =========================
        self.data_fetcher = NobitexDataFetcher()
        self.signal_engine = SignalEngine(config)
        self.news_reader = NewsReader(config)
        self.ai_analyzer = AIAnalyzer(config)
        self.bale_bot = BaleBot(config)
        self.formatter = MessageFormatter(config)
        self.performance_tracker = PerformanceTracker(config)
        
        # =========================
        # راه‌اندازی Paper Trader (با پشتیبانی از ذخیره‌سازی)
        # =========================
        self.paper_trader = PaperTrader(config)
        
        # گرفتن موجودی اولیه از BalanceManager
        initial_balance = self.paper_trader.get_balance()
        logger.info(f"✅ Paper Trader initialized with {initial_balance:.2f} USDT")
        
        # =========================
        # وضعیت ربات
        # =========================
        self.last_run_time = None
        self.last_signals = {}
        self.last_sent_signals = {}
        self.last_sent_times = {}
        self.running = False
        
        self._setup_logging()
    
    def _setup_logging(self):
        """تنظیم لاگ‌گیری"""
        log_level = getattr(logging, self.config.LOG_LEVEL.upper(), logging.INFO)
        
        logging.basicConfig(
            level=log_level,
            format=self.config.LOG_FORMAT,
            handlers=[
                logging.FileHandler(self.config.LOG_FILE),
                logging.StreamHandler()
            ]
        )
        
        logger.info("🚀 Crypto Signal Bot initialized")
        logger.info(self.config.get_config_summary())
    
    def _extract_indicator_scores(self, result: Dict[str, Any]) -> Dict[str, float]:
        """استخراج امتیاز اندیکاتورها از score_breakdown"""
        score_breakdown = result.get('score_breakdown', {})
        return {
            'trend': score_breakdown.get('trend', 0),
            'momentum': score_breakdown.get('momentum', 0),
            'volume': score_breakdown.get('volume', 0),
            'volatility': score_breakdown.get('volatility', 0),
            'breakout': score_breakdown.get('breakout', 0),
            'support_resistance': score_breakdown.get('support_resistance', 0),
            'adx': score_breakdown.get('adx', 0)
        }
    
    def run_once(self) -> bool:
        """یک بار اجرای کامل ربات"""
        logger.info("=" * 50)
        logger.info(f"🔄 Starting scan at {datetime.now()}")
        
        try:
            # ================================================
            # 🔥 بارگذاری وضعیت قبلی
            # ================================================
            state = load_state()
            
            symbols = self.config.get_active_symbols()
            if not symbols:
                logger.error("❌ No active symbols found")
                return False
            
            logger.info(f"📊 Analyzing {len(symbols)} symbols")
            
            market_data = self._fetch_market_data(symbols)
            if not market_data:
                logger.error("❌ No market data available")
                return False
            
            # ================================================
            # به‌روزرسانی قیمت‌ها
            # ================================================
            current_prices = {}
            for symbol, data in market_data.items():
                if data and data.get('price'):
                    current_prices[symbol] = data['price']
            
            if current_prices:
                self.paper_trader.update_prices(current_prices)
            
            # ================================================
            # 🔥 بررسی وضعیت پوزیشن باز
            # ================================================
            if state.get("in_position", False):
                symbol = state.get("symbol")
                entry_price = state.get("entry_price")
                
                if symbol and symbol in current_prices:
                    current_price = current_prices[symbol]
                    
                    # به‌روزرسانی سود/زیان تحقق‌نیافته
                    state = update_unrealized_pnl(state, current_price)
                    
                    # بررسی شرایط خروج (حد سود/ضرر)
                    should_close, reason = check_exit_conditions(state, current_price)
                    
                    if should_close:
                        # بستن پوزیشن
                        state = close_position(state, current_price, reason)
                        save_state(state)
                        
                        # ارسال پیام بسته شدن
                        pnl = get_total_pnl(state)
                        self.bale_bot.send_message(
                            f"🔴 پوزیشن بسته شد! ({reason})\n"
                            f"📊 {symbol}\n"
                            f"💰 سود/زیان: {pnl:+.2f} USDT"
                        )
                        logger.info(f"✅ پوزیشن {symbol} بسته شد: {reason}")
                    else:
                        # پوزیشن همچنان باز است
                        unrealized_pnl = state.get("unrealized_pnl", 0)
                        logger.info(f"⏳ پوزیشن باز است: {symbol} @ {entry_price:.4f}")
                        logger.info(f"   📊 قیمت فعلی: {current_price:.4f}")
                        logger.info(f"   💰 سود/زیان تحقق‌نیافته: {unrealized_pnl:+.2f} USDT")
                        
                        # ارسال پیام وضعیت (هر چند اجرا یکبار)
                        self.bale_bot.send_message(
                            f"⏳ پوزیشن باز است\n"
                            f"📊 {symbol}\n"
                            f"💰 قیمت ورود: {entry_price:.4f}\n"
                            f"📊 قیمت فعلی: {current_price:.4f}\n"
                            f"💸 سود/زیان: {unrealized_pnl:+.2f} USDT"
                        )
                else:
                    logger.warning(f"⚠️ قیمت {symbol} در دسترس نیست")
            else:
                logger.info("📭 پوزیشنی باز نیست")
            
            # ================================================
            # دریافت اخبار
            # ================================================
            news_data = None
            news_summary = None
            news_sentiment = None
            
            if self.config.ENABLE_NEWS_ANALYSIS:
                news_data = self.news_reader.fetch_news()
                if news_data:
                    news_summary = self.news_reader.get_news_summary()
                    news_sentiment = self.news_reader.get_market_sentiment(news_data)
                    logger.info(f"✅ News fetched: {news_sentiment.get('sentiment', 'neutral')}")
                else:
                    logger.warning("⚠️ News not available")
            
            # ================================================
            # تحلیل سیگنال‌ها
            # ================================================
            all_results = []
            for symbol, data in market_data.items():
                if data is None:
                    continue
                    
                try:
                    result = self.signal_engine.analyze_symbol(
                        df=data['df'],
                        symbol=symbol,
                        current_price=data['price'],
                        data_quality=data.get('data_quality')
                    )
                    
                    if result:
                        result['indicator_scores'] = self._extract_indicator_scores(result)
                        result['data_quality'] = data.get('data_quality')
                        all_results.append(result)
                        
                        self.last_signals[symbol] = {
                            'signal': result.get('signal'),
                            'score': result.get('score'),
                            'confidence': result.get('confidence'),
                            'timestamp': datetime.now()
                        }
                        
                except Exception as e:
                    logger.error(f"❌ Error analyzing {symbol}: {e}")
                    continue
            
            if not all_results:
                logger.warning("⚠️ No analysis results")
                return False
            
            market_regime = self._detect_market_regime(all_results)
            logger.info(f"📈 Market regime: {market_regime}")
            
            top_signals = self.signal_engine.get_top_opportunities(all_results, limit=5)
            
            # ================================================
            # 🔥 باز کردن پوزیشن جدید (فقط اگر پوزیشنی باز نیست)
            # ================================================
            if not state.get("in_position", False):
                for signal in top_signals:
                    if signal.get('signal') == 'BUY':
                        symbol = signal.get('symbol')
                        price = signal.get('price')
                        stop_loss = signal.get('stop_loss_raw')
                        take_profit = signal.get('tp1_raw')
                        
                        # بررسی معتبر بودن حد سود/ضرر
                        if not stop_loss or not take_profit or stop_loss >= take_profit:
                            logger.warning(f"⚠️ حد سود/ضرر نامعتبر برای {symbol}")
                            continue
                        
                        # بررسی RR
                        rr = signal.get('risk_reward', 0)
                        if rr < self.config.MIN_ACCEPTABLE_RR:
                            logger.info(f"⏭️ {symbol}: RR={rr:.2f} < {self.config.MIN_ACCEPTABLE_RR}")
                            continue
                        
                        # محاسبه حجم معامله (۲۰٪ از موجودی)
                        balance = state.get("balance", 530.0)
                        position_size = min(balance * 0.2, 106.0)  # حداکثر ۱۰۶ USDT
                        
                        # باز کردن پوزیشن
                        state = open_position(
                            state,
                            symbol=symbol,
                            price=price,
                            amount=position_size,
                            stop_loss=stop_loss,
                            take_profit=take_profit
                        )
                        
                        if state.get("in_position", False):
                            save_state(state)
                            
                            # ارسال پیام باز شدن
                            self.bale_bot.send_message(
                                f"🟢 پوزیشن باز شد!\n"
                                f"📊 {symbol}\n"
                                f"💰 قیمت ورود: {price:.4f}\n"
                                f"🛑 حد ضرر: {stop_loss:.4f}\n"
                                f"🎯 حد سود: {take_profit:.4f}\n"
                                f"💵 حجم: {position_size:.2f} USDT\n"
                                f"💰 موجودی: {state['balance']:.2f} USDT"
                            )
                            logger.info(f"✅ پوزیشن جدید باز شد: {symbol} @ {price:.4f}")
                            break
            else:
                logger.info("⏸️ پوزیشن باز است، منتظر بسته شدن برای سیگنال جدید...")
            
            # ================================================
            # ارسال سیگنال‌ها (بدون اجرای معامله)
            # ================================================
            signals_to_send = []
            for signal in top_signals:
                if self._should_send_signal(signal):
                    signals_to_send.append(signal)
            
            logger.info(f"📤 {len(signals_to_send)} signals to send out of {len(top_signals)} top signals")
            
            ai_results = {}
            if self.config.ENABLE_AI_ANALYSIS and signals_to_send:
                for signal in signals_to_send:
                    ai_result = self.ai_analyzer.analyze(
                        signal_data=signal,
                        news_summary=news_summary,
                        news_sentiment=news_sentiment,
                        market_regime=market_regime
                    )
                    ai_results[signal.get('symbol')] = ai_result
                    time.sleep(0.3)
            
            self._send_messages(all_results, signals_to_send, ai_results)
            
            # ================================================
            # ذخیره سیگنال‌ها در Performance Tracker
            # ================================================
            if all_results:
                for result in all_results:
                    if 'indicator_scores' not in result:
                        result['indicator_scores'] = self._extract_indicator_scores(result)
                
                self.performance_tracker.save_signals(all_results)
                logger.info(f"💾 Saved {len(all_results)} signals to performance tracker")
            
            # ================================================
            # نمایش خلاصه عملکرد
            # ================================================
            if len(self.performance_tracker.closed_signals) >= 10:
                best_indicators = self.performance_tracker.get_best_indicators(3)
                if best_indicators:
                    logger.info("📊 Best indicators:")
                    for item in best_indicators:
                        logger.info(f"  - {item['indicator']}: effectiveness={item['effectiveness']:.3f}, win_rate={item['win_rate']:.1f}%")
            
            logger.info(f"✅ Scan completed. {len(all_results)} signals generated, {len(signals_to_send)} sent.")
            logger.info("=" * 50)
            
            # ================================================
            # 🔥 گزارش وضعیت نهایی
            # ================================================
            summary = get_performance_summary(state)
            position_info = get_position_info(state)
            
            logger.info(
                f"💰 Balance: {summary.get('balance', 530.0):.2f} USDT "
                f"| P/L: {summary.get('total_pnl', 0):+.2f} USDT "
                f"| Win Rate: {summary.get('win_rate', 0)*100:.1f}% "
                f"| Trades: {summary.get('total_trades', 0)} "
                f"| In Position: {summary.get('in_position', False)}"
            )
            
            if position_info:
                logger.info(
                    f"   📊 Position: {position_info['symbol']} @ {position_info['entry_price']:.4f} "
                    f"| PnL: {state.get('unrealized_pnl', 0):+.2f} USDT"
                )
            
            # ================================================
            # 🔥 ذخیره وضعیت نهایی
            # ================================================
            save_state(state)
            
            self.last_run_time = datetime.now()
            return True
            
        except Exception as e:
            logger.error(f"❌ Critical error in run_once: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _fetch_market_data(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """دریافت داده بازار برای همه ارزها"""
        market_data = {}
        
        for symbol in symbols:
            try:
                df = self.data_fetcher.get_ohlcv(
                    symbol,
                    timeframe=self.config.TIMEFRAME,
                    limit=self.config.CANDLES_LIMIT
                )
                
                if df is None or len(df) < self.config.MIN_CANDLES_REQUIRED:
                    logger.warning(f"⚠️ Insufficient data for {symbol}")
                    continue
                
                data_quality = self.data_fetcher.get_data_quality(symbol)
                
                market_data[symbol] = {
                    'df': df,
                    'price': None,
                    'data_quality': data_quality
                }
                
            except Exception as e:
                logger.error(f"❌ Error fetching OHLCV for {symbol}: {e}")
                continue
        
        if not market_data:
            logger.warning("⚠️ No market data available after OHLCV fetch")
            return {}
        
        symbols_with_data = list(market_data.keys())
        for symbol in symbols_with_data:
            try:
                price = self.data_fetcher.get_current_price(symbol)
                if price:
                    market_data[symbol]['price'] = price
                else:
                    logger.warning(f"⚠️ No price for {symbol}, removing from analysis")
                    del market_data[symbol]
            except Exception as e:
                logger.error(f"❌ Error getting price for {symbol}: {e}")
                del market_data[symbol]
        
        logger.info(f"✅ Fetched data for {len(market_data)} symbols")
        return market_data
    
    def _should_send_signal(self, signal: Dict[str, Any]) -> bool:
        """بررسی اینکه آیا سیگنال باید ارسال شود"""
        symbol = signal.get('symbol')
        current_signal = signal.get('signal')
        current_score = signal.get('score', 0)
        
        if current_signal == 'WAIT':
            return False
        
        if symbol not in self.last_sent_signals:
            return True
        
        last_sent = self.last_sent_signals.get(symbol, {})
        if last_sent.get('signal') != current_signal:
            return True
        
        last_score = last_sent.get('score', 0)
        if abs(current_score - last_score) > 10:
            return True
        
        last_time = self.last_sent_times.get(symbol)
        if last_time:
            time_diff = (datetime.now() - last_time).total_seconds()
            if time_diff >= self.config.MIN_SIGNAL_INTERVAL:
                return True
        
        return False
    
    def _send_messages(
        self, 
        all_results: List[Dict[str, Any]],
        signals_to_send: List[Dict[str, Any]],
        ai_results: Dict[str, Dict[str, Any]]
    ) -> None:
        """ارسال پیام‌ها"""
        if self.config.TEST_MODE:
            logger.info("🧪 TEST MODE: Messages not sent")
            return
        
        if not signals_to_send:
            logger.info("📭 No signals to send")
            return
        
        sent_count = 0
        for signal in signals_to_send:
            symbol = signal.get('symbol')
            ai_result = ai_results.get(symbol)
            
            message = self.formatter.format_signal(signal, ai_result)
            success = self.bale_bot.send_message(message)
            
            if success:
                self.last_sent_signals[symbol] = {
                    'signal': signal.get('signal'),
                    'score': signal.get('score'),
                    'confidence': signal.get('confidence')
                }
                self.last_sent_times[symbol] = datetime.now()
                sent_count += 1
                logger.info(f"📤 Sent signal for {symbol}")
            else:
                logger.error(f"❌ Failed to send message for {symbol}")
            
            time.sleep(0.5)
        
        if self.config.SEND_SUMMARY and sent_count > 0:
            ai_summary = None
            if self.config.ENABLE_AI_ANALYSIS:
                for ai_result in ai_results.values():
                    if ai_result.get('summary'):
                        ai_summary = ai_result.get('summary')
                        break
            
            summary = self.formatter.format_summary(
                signals=all_results,
                market_regime=self._detect_market_regime(all_results),
                ai_summary=ai_summary
            )
            self.bale_bot.send_message(summary)
            
        elif sent_count == 0:
            logger.info("📭 No new signals to send")
    
    def _detect_market_regime(self, results: List[Dict[str, Any]]) -> str:
        """تشخیص وضعیت کلی بازار"""
        if not results:
            return 'neutral'
        
        buy_count = sum(1 for r in results if r.get('signal') == 'BUY')
        sell_count = sum(1 for r in results if r.get('signal') == 'SELL')
        total = len(results)
        
        if total == 0:
            return 'neutral'
        
        buy_ratio = buy_count / total
        sell_ratio = sell_count / total
        
        if buy_ratio > 0.6:
            return 'bullish'
        elif sell_ratio > 0.6:
            return 'bearish'
        elif buy_ratio > 0.55 and sell_ratio < 0.3:
            return 'bullish'
        elif sell_ratio > 0.55 and buy_ratio < 0.3:
            return 'bearish'
        else:
            return 'neutral'
    
    def run_forever(self):
        """اجرای مداوم ربات"""
        self.running = True
        logger.info("🔄 Starting continuous mode...")
        
        while self.running:
            try:
                self.run_once()
                logger.info(f"⏳ Waiting {self.config.SCAN_INTERVAL} seconds...")
                time.sleep(self.config.SCAN_INTERVAL)
            except KeyboardInterrupt:
                logger.info("👋 Bot stopped by user")
                self.running = False
                
                # ================================================
                # 🔥 گزارش نهایی
                # ================================================
                self._show_final_report()
                break
            except Exception as e:
                logger.error(f"❌ Critical error: {e}")
                time.sleep(60)
    
    def _show_final_report(self):
        """نمایش گزارش نهایی"""
        logger.info("=" * 60)
        logger.info("📊 FINAL PAPER TRADING REPORT")
        logger.info("=" * 60)
        
        # بارگذاری وضعیت نهایی
        state = load_state()
        summary = get_performance_summary(state)
        position_info = get_position_info(state)
        
        logger.info(f"💰 سرمایه اولیه: {summary.get('initial_balance', 530.0):.2f} USDT")
        logger.info(f"💰 سرمایه فعلی: {summary.get('balance', 530.0):.2f} USDT")
        logger.info(f"📈 سود/زیان کل: {summary.get('total_pnl', 0):+.2f} USDT")
        logger.info(f"📊 بازده کل: {summary.get('total_return', 0):+.2f}%")
        logger.info(f"📊 تعداد معاملات: {summary.get('total_trades', 0)}")
        logger.info(f"✅ معاملات برنده: {summary.get('winning_trades', 0)}")
        logger.info(f"❌ معاملات بازنده: {summary.get('losing_trades', 0)}")
        logger.info(f"🎯 نرخ برد: {summary.get('win_rate', 0)*100:.1f}%")
        logger.info(f"📭 پوزیشن باز: {summary.get('in_position', False)}")
        
        if position_info:
            logger.info(f"   📊 {position_info['symbol']} @ {position_info['entry_price']:.4f}")
            logger.info(f"   🛑 حد ضرر: {position_info['stop_loss']:.4f}")
            logger.info(f"   🎯 حد سود: {position_info['take_profit']:.4f}")
        
        logger.info("=" * 60)
    
    def stop(self):
        """متوقف کردن ربات"""
        self.running = False
        logger.info("🛑 Bot stopped")
        
        # نمایش گزارش نهایی
        self._show_final_report()


def main():
    """نقطه ورود اصلی"""
    try:
        Config.validate()
        bot = CryptoSignalBot()
        
        if len(sys.argv) > 1 and sys.argv[1] == '--once':
            bot.run_once()
            # نمایش گزارش بعد از یک بار اجرا
            bot._show_final_report()
        else:
            bot.run_forever()
            
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
