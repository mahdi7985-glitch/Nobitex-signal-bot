def get_current_price(self, symbol: str) -> Optional[float]:
    """
    دریافت قیمت لحظه‌ای از نوبیتکس
    """
    market_key = self._get_nobitex_symbol(symbol)

    if not market_key:
        logger.warning(f"⚠️ No market mapping for {symbol}")
        return None

    try:
        self._rate_limit('stats')

        url = f"{self.base_url_stats}/market/stats"

        params = {
            'srcCurrency': symbol.upper(),
            'dstCurrency': 'USDT'
        }

        logger.debug(f"Fetching price for {symbol}")

        response = self.session.get(
            url,
            params=params,
            timeout=Config.REQUEST_TIMEOUT
        )

        if response.status_code != 200:
            logger.error(
                f"❌ HTTP Error {response.status_code} for {symbol}: "
                f"{response.text}"
            )
            return None

        data = response.json()

        if data.get('status') != 'ok':
            logger.error(f"❌ API Error for {symbol}: {data}")
            return None

        stats = data.get('stats', {})

        # ابتدا دقیقاً با mapping جستجو می‌کنیم
        ticker = stats.get(market_key)

        # اگر پیدا نشد، جستجوی بدون حساسیت به حروف
        if not ticker:
            target_key = market_key.upper()

            for key, value in stats.items():
                if key.upper() == target_key:
                    ticker = value
                    break

        if not ticker:
            logger.warning(
                f"⚠️ No ticker found for {symbol}. "
                f"Expected: {market_key}, "
                f"Available: {list(stats.keys())}"
            )
            return None

        price = ticker.get('latest')

        if price is None:
            logger.warning(
                f"⚠️ No latest price for {symbol}. "
                f"Ticker: {ticker}"
            )
            return None

        return float(price)

    except requests.exceptions.Timeout:
        logger.error(f"❌ Timeout getting price for {symbol}")
        return None

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Request error getting price for {symbol}: {e}")
        return None

    except (ValueError, TypeError) as e:
        logger.error(
            f"❌ Invalid price for {symbol}: {price if 'price' in locals() else None} "
            f"({e})"
        )
        return None

    except Exception as e:
        logger.error(f"❌ Unexpected error getting price for {symbol}: {e}")
        return None
