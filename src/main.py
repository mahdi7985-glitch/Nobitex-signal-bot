"""
Main Application Module
Orchestrates all components: data fetching, analysis, AI, and messaging
"""

import logging
import time
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional

import pandas as pd  # 🔥 اضافه شد

from config import Config
from src.data_fetcher import NobitexDataFetcher
from src.signal_engine import SignalEngine
from src.news_reader import NewsReader
from src.ai_analyzer import AIAnalyzer
from src.bale_bot import BaleBot
from src.formatter import MessageFormatter
from src.performance_tracker import PerformanceTracker
from src.paper_trader import PaperTrader
from src.data_validator import DataValidator
from src.state_manager import (
    load_state, save_state, open_position,
    close_position, check_all_positions,
    get_total_pnl, get_performance_summary,
    get_position_info, update_unrealized_pnl,
    can_open_new_position, is_symbol_in_positions,
    MAX_POSITIONS
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
        self.data_validator = DataValidator(config)
        self.signal_engine = SignalEngine(config)
        self.news_reader = NewsReader(config)
        self.ai_analyzer = AIAnalyzer(config)
        self.bale_bot = BaleBot(config)
        self.formatter = MessageFormatter(config)
        self.performance_tracker = PerformanceTracker(config)

        # =========================
        # راه‌اندازی Paper Trader
        # =========================
        self.paper_trader = PaperTrader(config)

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
            state = load_state()

            symbols = self.config.get_active_symbols()
            if not symbols:
                logger.error("❌ No active symbols found")
                return False

            logger.info(f"📊 Analyzing {len(symbols)} symbols")

            # ================================================
            # 🔥 دریافت داده با اعتبارسنجی + تایم‌فریم‌های بالاتر
            # ================================================
            market_data = self._fetch_and_validate_market_data(symbols)
            if not market_data:
                logger.error("❌ No valid market data available")
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
            # بررسی پوزیشن‌های باز
            # ================================================
            positions = state.get("positions", [])

            if positions:
                state = update_unrealized_pnl(state, current_prices)
                to_close = check_all_positions(state, current_prices)

                for item in to_close:
                    position = item["position"]
                    position_id = item.get("position_id") or position.get("id")
                    exit_price = item["exit_price"]
                    reason = item["reason"]

                    state = close_position(state, position_id, exit_price, reason)
                    save_state(state)

                    symbol = position["symbol"]
                    self.bale_bot.send_message(
                        f"🔴 پوزیشن بسته شد! ({reason})\n"
                        f"📊 {symbol}\n"
                        f"💰 سود/زیان: {position.get('unrealized_pnl', 0):+.2f} USDT"
                    )
                    logger.info(f"✅ پوزیشن {symbol} بسته شد: {reason}")

                remaining = state.get("positions", [])
                if remaining:
                    logger.info(f"⏳ {len(remaining)} پوزیشن باز:")
                    for pos in remaining:
                        pnl = pos.get("unrealized_pnl", 0)
                        logger.info(f"   📊 {pos['symbol']} @ {pos['entry_price']:.4f} | PnL: {pnl:+.2f} USDT")
            else:
                logger.info("📭 پوزیشنی باز نیست")

            # ================================================
            # تحلیل سیگنال‌ها با تایم‌فریم‌های بالاتر
            # ================================================
            all_results = []
            for symbol, data in market_data.items():
                if data is None:
                    continue

                try:
                    # 🔥 ارسال تایم‌فریم‌های بالاتر به SignalEngine
                    result = self.signal_engine.analyze_symbol(
                        df=data['df'],
                        symbol=symbol,
                        current_price=data['price'],
                        data_quality=(
                            data['data_quality'].to_dict()
                            if data.get('data_quality') is not None
                            else None
                                ),
                        higher_tf=data.get('higher_tf', {})  # 🔥 جدید
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

            top_signals = self.signal_engine.get_top_opportunities(all_results, limit=10)

            # ================================================
            # دریافت تحلیل AI
            # ================================================
            ai_results = {}
            if self.config.ENABLE_AI_ANALYSIS and top_signals:
                for signal in top_signals[:5]:
                    symbol = signal.get('symbol')
                    ohlcv_data = market_data.get(symbol, {}).get('df')
                    current_price = signal.get('price', 0)

                    if ohlcv_data is not None and not ohlcv_data.empty:
                        ohlcv_list = ohlcv_data[['open', 'high', 'low', 'close', 'volume']].to_dict('records')

                        ai_result = self.ai_analyzer.analyze(
                            ohlcv_data=ohlcv_list,
                            symbol=symbol,
                            current_price=current_price,
                            timeframe=self.config.TIMEFRAME
                        )
                    else:
                        logger.warning(f"⚠️ No OHLCV data for {symbol}, skipping AI analysis")
                        ai_result = {
                            'direction': 'INVALID',
                            'confidence': 0,
                            'summary': 'No data for AI analysis'
                        }

                    ai_results[symbol] = ai_result

                    signal['ai_direction'] = ai_result.get('direction', 'NEUTRAL')
                    signal['ai_confidence'] = ai_result.get('confidence', 0)
                    signal['ai_summary'] = ai_result.get('summary', '')
                    signal['ai_trend'] = ai_result.get('trend', 'UNKNOWN')
                    signal['ai_entry_quality'] = ai_result.get('entry_quality', 'POOR')

                    time.sleep(0.3)

            # ================================================
            # باز کردن پوزیشن‌های جدید
            # ================================================
            opened_count = 0
            for signal in top_signals:
                if signal.get('signal') == 'BUY':
                    symbol = signal.get('symbol')

                    if is_symbol_in_positions(state, symbol):
                        logger.info(f"⏭️ {symbol} در حال حاضر در پوزیشن باز است، رد شد")
                        continue

                    price = signal.get('price')
                    stop_loss = signal.get('stop_loss_raw')
                    take_profit = signal.get('tp1_raw')

                    if not stop_loss or not take_profit or stop_loss >= take_profit:
                        logger.warning(f"⚠️ حد سود/ضرر نامعتبر برای {symbol}")
                        continue

                    rr = signal.get('risk_reward', 0)
                    if rr < self.config.MIN_ACCEPTABLE_RR:
                        logger.info(f"⏭️ {symbol}: RR={rr:.2f} < {self.config.MIN_ACCEPTABLE_RR}")
                        continue

                    if not can_open_new_position(state):
                        logger.info(f"⏸️ ظرفیت پوزیشن‌ها پر شده ({MAX_POSITIONS})، توقف")
                        break

                    state = open_position(
                        state,
                        symbol=symbol,
                        price=price,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        signal_data=signal
                    )

                    if state.get("positions") and len(state["positions"]) > opened_count:
                        opened_count += 1
                        save_state(state)

                        ai_info = ""
                        if signal.get('ai_direction'):
                            ai_info = f"\n🤖 AI: {signal.get('ai_direction')} (اطمینان: {signal.get('ai_confidence')}/10)"

                        self.bale_bot.send_message(
                            f"🟢 پوزیشن جدید باز شد! ({opened_count}/{MAX_POSITIONS})\n"
                            f"📊 {symbol}\n"
                            f"💰 قیمت ورود: {price:.4f}\n"
                            f"🛑 حد ضرر: {stop_loss:.4f}\n"
                            f"🎯 حد سود: {take_profit:.4f}\n"
                            f"💰 موجودی: {state['balance']:.2f} USDT"
                            f"{ai_info}"
                        )
                        logger.info(f"✅ پوزیشن جدید باز شد: {symbol} @ {price:.4f}")

            if opened_count == 0 and len(state.get("positions", [])) < MAX_POSITIONS:
                logger.info("📭 هیچ سیگنال مناسبی برای باز کردن پوزیشن جدید یافت نشد")
            elif opened_count > 0:
                logger.info(f"✅ {opened_count} پوزیشن جدید باز شد")

            # ================================================
            # ارسال سیگنال‌ها
            # ================================================
            signals_to_send = []
            for signal in top_signals[:5]:
                if self._should_send_signal(signal):
                    signals_to_send.append(signal)

            logger.info(f"📤 {len(signals_to_send)} signals to send out of {len(top_signals)} top signals")
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
            # گزارش وضعیت نهایی
            # ================================================
            summary = get_performance_summary(state)
            positions = state.get("positions", [])

            logger.info(
                f"💰 Balance: {summary.get('balance', 530.0):.2f} USDT "
                f"| P/L: {summary.get('total_pnl', 0):+.2f} USDT "
                f"| Win Rate: {summary.get('win_rate', 0)*100:.1f}% "
                f"| Trades: {summary.get('total_trades', 0)} "
                f"| Open Positions: {len(positions)}/{MAX_POSITIONS}"
            )

            if positions:
                for pos in positions:
                    pnl = pos.get("unrealized_pnl", 0)
                    logger.info(
                        f"   📊 {pos['symbol']} @ {pos['entry_price']:.4f} "
                        f"| PnL: {pnl:+.2f} USDT "
                        f"| SL: {pos.get('stop_loss', 0):.4f} "
                        f"| TP: {pos.get('take_profit', 0):.4f}"
                    )

            save_state(state)

            self.last_run_time = datetime.now()
            return True

        except Exception as e:
            logger.error(f"❌ Critical error in run_once: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _fetch_and_validate_market_data(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        دریافت و اعتبارسنجی داده بازار برای همه ارزها
        🔥 شامل تایم‌فریم‌های بالاتر
        """
        market_data = {}

        for symbol in symbols:
            try:
                # ================================================
                # STEP 1: دریافت داده اصلی (15m)
                # ================================================
                df = self.data_fetcher.get_ohlcv(
                    symbol,
                    timeframe=self.config.TIMEFRAME,
                    limit=self.config.CANDLES_LIMIT
                )

                if df is None or len(df) < self.config.MIN_CANDLES_REQUIRED:
                    logger.warning(f"⚠️ Insufficient data for {symbol}: {len(df) if df is not None else 0} candles")
                    continue

                # ================================================
                # STEP 2: 🔥 دریافت تایم‌فریم‌های بالاتر
                # ================================================
                higher_tf_data = {}
                for tf in self.config.HIGHER_TIMEFRAMES:
                    try:
                        df_higher = self.data_fetcher.get_ohlcv(
                            symbol,
                            timeframe=tf,
                            limit=self.config.CANDLES_LIMIT
                        )
                        if df_higher is not None and len(df_higher) > 50:
                            higher_tf_data[tf] = df_higher
                            logger.debug(f"✅ {symbol}: Fetched {tf} with {len(df_higher)} candles")
                    except Exception as e:
                        logger.warning(f"⚠️ Could not fetch {tf} for {symbol}: {e}")

                if higher_tf_data:
                    logger.info(f"📊 {symbol}: Fetched higher TFs: {list(higher_tf_data.keys())}")

                # ================================================
                # STEP 3: اعتبارسنجی داده اصلی
                # ================================================
                validation_result = self.data_validator.validate(df, symbol, self.config.TIMEFRAME)

                if not validation_result.get('valid', False):
                    logger.warning(
                        f"🚫 {symbol}: Data validation failed - {validation_result.get('reason', 'Unknown')}"
                    )
                    continue
                # ================================================
                # STEP 4: دریافت قیمت
                # ================================================
                price = self.data_fetcher.get_current_price(symbol)
                if not price:
                    logger.warning(f"⚠️ No price for {symbol}")
                    continue

                # ================================================
                # STEP 5: ذخیره داده
                # ================================================
                market_data[symbol] = {
                    'df': df,
                    'price': price,
                    'data_quality': validation_result,
                    'higher_tf': higher_tf_data,  # 🔥 تایم‌فریم‌های بالاتر
                    'validation_passed': True
                }

                if validation_result.get('issues'):
                    logger.info(f"📊 {symbol}: Data quality={validation_result.get('quality_score', 0):.1f}% "
                               f"({len(validation_result.get('issues', []))} issues)")

            except Exception as e:
                logger.error(f"❌ Error fetching/validating {symbol}: {e}")
                continue

        logger.info(f"✅ Validated data for {len(market_data)} symbols")
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

        state = load_state()
        summary = get_performance_summary(state)
        positions = state.get("positions", [])

        logger.info(f"💰 سرمایه اولیه: {summary.get('initial_balance', 530.0):.2f} USDT")
        logger.info(f"💰 سرمایه فعلی: {summary.get('balance', 530.0):.2f} USDT")
        logger.info(f"📈 سود/زیان کل: {summary.get('total_pnl', 0):+.2f} USDT")
        logger.info(f"📊 بازده کل: {summary.get('total_return', 0):+.2f}%")
        logger.info(f"📊 تعداد معاملات: {summary.get('total_trades', 0)}")
        logger.info(f"✅ معاملات برنده: {summary.get('winning_trades', 0)}")
        logger.info(f"❌ معاملات بازنده: {summary.get('losing_trades', 0)}")
        logger.info(f"🎯 نرخ برد: {summary.get('win_rate', 0)*100:.1f}%")
        logger.info(f"📭 پوزیشن‌های باز: {len(positions)}/{MAX_POSITIONS}")

        if positions:
            logger.info("   📊 پوزیشن‌های باز:")
            for pos in positions:
                pnl = pos.get("unrealized_pnl", 0)
                logger.info(f"      {pos['symbol']} @ {pos['entry_price']:.4f} | PnL: {pnl:+.2f} USDT")
                logger.info(f"      🛑 SL: {pos.get('stop_loss', 0):.4f} | 🎯 TP: {pos.get('take_profit', 0):.4f}")

        logger.info("=" * 60)

    def stop(self):
        """متوقف کردن ربات"""
        self.running = False
        logger.info("🛑 Bot stopped")
        self._show_final_report()


def main():
    """نقطه ورود اصلی"""
    try:
        Config.validate()
        bot = CryptoSignalBot()

        if len(sys.argv) > 1 and sys.argv[1] == '--once':
            bot.run_once()
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
