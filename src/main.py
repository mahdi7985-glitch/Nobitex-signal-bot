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
from src.paper_trader import PaperTrader  # <-- اصلاح شده

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
        # راه‌اندازی Paper Trader (اضافه شده)
        # =========================
        self.paper_trader = PaperTrader(config)
        logger.info("✅ Paper Trader initialized with 530 USDT")
        
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
            # به‌روزرسانی قیمت‌ها در Paper Trader (اضافه شده)
            # ================================================
            current_prices = {}
            for symbol, data in market_data.items():
                if data and data.get('price'):
                    current_prices[symbol] = data['price']
            
            if current_prices:
                self.paper_trader.update_prices(current_prices)
            
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
                        # استخراج indicator_scores
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
            # پردازش سیگنال‌ها توسط Paper Trader (اضافه شده)
            # ================================================
            for signal in top_signals:
                if signal.get('signal') in ['BUY', 'SELL']:
                    self.paper_trader.process_signal(signal)
            
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
                # اطمینان از وجود indicator_scores در همه سیگنال‌ها
                for result in all_results:
                    if 'indicator_scores' not in result:
                        result['indicator_scores'] = self._extract_indicator_scores(result)
                
                self.performance_tracker.save_signals(all_results)
                logger.info(f"💾 Saved {len(all_results)} signals to performance tracker")
            
            # ================================================
            # نمایش خلاصه عملکرد اندیکاتورها
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
            # گزارش وضعیت Paper Trader (اضافه شده)
            # ================================================
            if signals_to_send:
                status = self.paper_trader.get_status()
                logger.info(
                    f"💰 Paper Balance: {status['balance']:.2f} USDT "
                    f"| Open: {status['open_positions_count']} "
                    f"| P/L: {status['balance'] - 530:.2f} USDT"
                )
            
            self.last_run_time = datetime.now()
            return True
            
        except Exception as e:
            logger.error(f"❌ Critical error in run_once: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _fetch_market_data(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        دریافت داده بازار برای همه ارزها
        
        با دریافت OHLCV و سپس قیمت به صورت تکی (به جای Batch)
        """
        market_data = {}
        
        # =========================
        # مرحله 1: دریافت OHLCV
        # =========================
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
        
        # =========================
        # مرحله 2: دریافت قیمت‌ها (تکی)
        # =========================
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
                # گزارش نهایی Paper Trader (اضافه شده)
                # ================================================
                status = self.paper_trader.get_status()
                logger.info("=" * 50)
                logger.info("📊 FINAL PAPER TRADING REPORT")
                logger.info(f"   Initial Balance: 530.00 USDT")
                logger.info(f"   Final Balance:   {status['balance']:.2f} USDT")
                logger.info(f"   Total P/L:       {status['balance'] - 530:.2f} USDT")
                logger.info(f"   P/L Percent:     {((status['balance'] / 530) - 1) * 100:.2f}%")
                logger.info(f"   Open Positions:  {status['open_positions_count']}")
                logger.info("=" * 50)
                break
            except Exception as e:
                logger.error(f"❌ Critical error: {e}")
                time.sleep(60)
    
    def stop(self):
        """متوقف کردن ربات"""
        self.running = False
        logger.info("🛑 Bot stopped")


def main():
    """نقطه ورود اصلی"""
    try:
        Config.validate()
        bot = CryptoSignalBot()
        
        if len(sys.argv) > 1 and sys.argv[1] == '--once':
            bot.run_once()
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
