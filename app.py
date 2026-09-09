"""
Binance Grid Trading Bot — Web Arayüzlü
=========================================
Testnet üzerinde çalışan basit bir grid trading botu.

Grid mantığı:
- Belirlenen fiyat aralığı (lower..upper) N parçaya bölünür.
- Mevcut fiyatın ALTINDAKİ her seviyeye bir LIMIT BUY emri konur.
- Bir BUY emri dolduğunda, bir üst seviyeye LIMIT SELL emri konur.
- O SELL emri dolduğunda, kâr kayda geçer ve bir alt seviyeye tekrar
  LIMIT BUY emri konur. Böylece bot fiyat aralığında salınırken
  otomatik olarak "düşükten al, yüksekten sat" yapar.

ÖNEMLİ: Bu kod varsayılan olarak Binance TESTNET'e bağlanır
(sahte para). Gerçek hesapla kullanmadan önce README.md'yi okuyun.
"""

import os
import math
import time
import threading
from datetime import datetime

from flask import Flask, jsonify, request, render_template
from dotenv import load_dotenv
from binance.client import Client
from binance.exceptions import BinanceAPIException

load_dotenv()

app = Flask(__name__)

API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_API_SECRET", "")
USE_TESTNET = os.getenv("USE_TESTNET", "true").lower() == "true"

MAX_LOG_LINES = 200


def round_step(value: float, step: float) -> float:
    """Bir değeri Binance'ın istediği step büyüklüğüne yuvarlar (aşağı doğru)."""
    if step == 0:
        return value
    precision = int(round(-math.log10(step))) if step < 1 else 0
    return math.floor(value / step) * step if precision == 0 else round(
        math.floor(value / step) * step, precision
    )


class GridBot:
    def __init__(self):
        self.client = None
        self.active = False
        self.thread = None
        self.lock = threading.Lock()

        self.symbol = None
        self.levels = []          # fiyat seviyeleri (küçükten büyüğe)
        self.qty_per_grid = 0.0
        self.tick_size = 0.0
        self.step_size = 0.0

        # level_index -> {"orderId": int, "side": "BUY"/"SELL", "price": float}
        self.orders = {}
        self.trades = []          # tamamlanan al-sat çiftleri
        self.logs = []
        self.error = None

    # ---------- yardımcılar ----------

    def log(self, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        with self.lock:
            self.logs.append(f"[{ts}] {message}")
            if len(self.logs) > MAX_LOG_LINES:
                self.logs = self.logs[-MAX_LOG_LINES:]

    def _load_symbol_filters(self):
        info = self.client.get_symbol_info(self.symbol)
        if info is None:
            raise ValueError(f"Sembol bulunamadı: {self.symbol}")
        for f in info["filters"]:
            if f["filterType"] == "PRICE_FILTER":
                self.tick_size = float(f["tickSize"])
            if f["filterType"] == "LOT_SIZE":
                self.step_size = float(f["stepSize"])

    def _round_price(self, price: float) -> float:
        return round_step(price, self.tick_size)

    def _round_qty(self, qty: float) -> float:
        return round_step(qty, self.step_size)

    # ---------- ana akış ----------

    def start(self, symbol, lower, upper, grid_count, investment):
        if self.active:
            raise RuntimeError("Bot zaten çalışıyor. Önce durdurun.")

        self.client = Client(API_KEY, API_SECRET, testnet=USE_TESTNET)
        self.symbol = symbol.upper()
        self.orders = {}
        self.trades = []
        self.logs = []
        self.error = None

        self._load_symbol_filters()

        step = (upper - lower) / grid_count
        self.levels = [round(lower + i * step, 8) for i in range(grid_count + 1)]

        ticker = self.client.get_symbol_ticker(symbol=self.symbol)
        current_price = float(ticker["price"])
        self.log(f"{self.symbol} güncel fiyat: {current_price}")

        # Her grid seviyesi için yatırılacak miktar (adet cinsinden)
        raw_qty = investment / grid_count / current_price
        self.qty_per_grid = self._round_qty(raw_qty)
        if self.qty_per_grid <= 0:
            raise ValueError(
                "Hesaplanan işlem miktarı çok küçük. Yatırım miktarını artırın."
            )

        self.active = True

        placed = 0
        for idx, level_price in enumerate(self.levels):
            if level_price < current_price:
                self._place_order(idx, "BUY")
                placed += 1

        if placed == 0:
            self.log(
                "Uyarı: mevcut fiyat, girilen aralığın altında/dışında kaldığı "
                "için hiç BUY emri açılamadı. Aralığı kontrol edin."
            )

        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        self.log("Grid bot başlatıldı.")

    def _place_order(self, level_idx, side):
        price = self._round_price(self.levels[level_idx])
        qty = self.qty_per_grid
        try:
            order = self.client.create_order(
                symbol=self.symbol,
                side=side,
                type="LIMIT",
                timeInForce="GTC",
                quantity=qty,
                price=str(price),
            )
            self.orders[level_idx] = {
                "orderId": order["orderId"],
                "side": side,
                "price": price,
                "qty": qty,
            }
            self.log(f"{side} emri açıldı: seviye {level_idx} @ {price}")
        except BinanceAPIException as e:
            self.error = str(e)
            self.log(f"HATA ({side} @ {price}): {e.message}")

    def _monitor_loop(self):
        while self.active:
            try:
                for level_idx, info in list(self.orders.items()):
                    order = self.client.get_order(
                        symbol=self.symbol, orderId=info["orderId"]
                    )
                    if order["status"] == "FILLED":
                        self._handle_fill(level_idx, info)
            except BinanceAPIException as e:
                self.error = str(e)
                self.log(f"HATA (izleme): {e.message}")
            except Exception as e:  # ağ hatası vb.
                self.log(f"HATA (izleme): {e}")
            time.sleep(5)

    def _handle_fill(self, level_idx, info):
        del self.orders[level_idx]
        side = info["side"]
        price = info["price"]
        qty = info["qty"]
        self.log(f"{side} emri doldu: seviye {level_idx} @ {price}")

        if side == "BUY" and level_idx + 1 < len(self.levels):
            self._place_order(level_idx + 1, "SELL")
        elif side == "SELL" and level_idx - 1 >= 0:
            profit = (price - self.levels[level_idx - 1]) * qty
            self.trades.append(
                {
                    "buy_price": self.levels[level_idx - 1],
                    "sell_price": price,
                    "qty": qty,
                    "profit": round(profit, 8),
                    "time": datetime.now().strftime("%H:%M:%S"),
                }
            )
            self.log(f"Kâr kaydedildi: {round(profit, 4)}")
            self._place_order(level_idx - 1, "BUY")

    def stop(self):
        if not self.active:
            return
        self.active = False
        for level_idx, info in list(self.orders.items()):
            try:
                self.client.cancel_order(symbol=self.symbol, orderId=info["orderId"])
                self.log(f"Emir iptal edildi: seviye {level_idx}")
            except BinanceAPIException as e:
                self.log(f"HATA (iptal): {e.message}")
        self.orders = {}
        self.log("Grid bot durduruldu.")

    def status(self):
        with self.lock:
            total_profit = round(sum(t["profit"] for t in self.trades), 8)
            return {
                "active": self.active,
                "symbol": self.symbol,
                "levels": self.levels,
                "orders": [
                    {"level": idx, **info} for idx, info in sorted(self.orders.items())
                ],
                "trades": self.trades[-50:],
                "total_profit": total_profit,
                "logs": self.logs[-100:],
                "error": self.error,
            }


bot = GridBot()


@app.route("/")
def index():
    return render_template("index.html", testnet=USE_TESTNET)


@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.get_json(force=True)
    try:
        bot.start(
            symbol=data["symbol"],
            lower=float(data["lower"]),
            upper=float(data["upper"]),
            grid_count=int(data["grid_count"]),
            investment=float(data["investment"]),
        )
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/stop", methods=["POST"])
def api_stop():
    bot.stop()
    return jsonify({"ok": True})


@app.route("/api/status")
def api_status():
    return jsonify(bot.status())


if __name__ == "__main__":
    if not API_KEY or not API_SECRET:
        print(
            "UYARI: BINANCE_API_KEY / BINANCE_API_SECRET tanımlı değil. "
            ".env dosyanızı kontrol edin."
        )
    app.run(debug=True, port=5000)
