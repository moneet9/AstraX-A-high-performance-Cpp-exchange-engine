"""Small persistent account and mock-order service for the local simulator.

This module deliberately uses only the Python standard library. Prices use the
engine's fixed-point scale (1 displayed unit = 10,000 engine price units).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path

PRICE_SCALE = 10_000


class TradingService:
    def __init__(self, engine, db_path: str | None = None):
        self.engine = engine
        self.db_path = db_path or os.getenv("ASTRAX_DB_PATH", "data/astrax.sqlite3")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.max_position = int(os.getenv("ASTRAX_MAX_POSITION", "1000"))
        self.max_price_deviation_bps = int(os.getenv("ASTRAX_PRICE_BAND_BPS", "2000"))
        self._initialize()
        self.order_users: dict[int, int] = {}

    def _initialize(self):
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('trader','admin')),
          cash INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS tokens(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), symbol TEXT NOT NULL,
          engine_id INTEGER,
          side TEXT NOT NULL, type TEXT NOT NULL, price INTEGER NOT NULL, quantity INTEGER NOT NULL,
          filled INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
          idempotency_key TEXT, UNIQUE(user_id,idempotency_key));
        CREATE TABLE IF NOT EXISTS fills(id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id),
          price INTEGER NOT NULL, quantity INTEGER NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS positions(user_id INTEGER NOT NULL REFERENCES users(id), symbol TEXT NOT NULL,
          quantity INTEGER NOT NULL DEFAULT 0, average_price INTEGER NOT NULL DEFAULT 0,
          realized_pnl INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id,symbol));
        CREATE TABLE IF NOT EXISTS benchmark_runs(id INTEGER PRIMARY KEY, status TEXT NOT NULL, created REAL NOT NULL,
          finished REAL, result_json TEXT, error TEXT);
        CREATE TABLE IF NOT EXISTS benchmark_runs(id INTEGER PRIMARY KEY, status TEXT NOT NULL, created REAL NOT NULL,
          finished REAL, result_json TEXT, error TEXT);
        """)
        columns={row[1] for row in self.db.execute("PRAGMA table_info(orders)")}
        if "engine_id" not in columns: self.db.execute("ALTER TABLE orders ADD COLUMN engine_id INTEGER")
        self.db.commit()
        for username, role, envkey in (("trader1", "trader", "ASTRAX_TRADER1_PASSWORD"),
                                       ("trader2", "trader", "ASTRAX_TRADER2_PASSWORD"),
                                       ("admin", "admin", "ASTRAX_ADMIN_PASSWORD")):
            if not self.db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
                password = os.getenv(envkey) or secrets.token_urlsafe(12)
                salt = secrets.token_bytes(16)
                digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
                self.db.execute("INSERT INTO users(username,password_hash,role,cash) VALUES(?,?,?,?)",
                                (username, f"{salt.hex()}:{digest.hex()}", role,
                                 int(os.getenv("ASTRAX_STARTING_CASH", "1000000"))))
                if not os.getenv(envkey):
                    print(f"AstraX demo password for {username} (save it now): {password}")
        self.db.commit()

    def login(self, username: str, password: str) -> str | None:
        user = self.db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not user:
            return None
        salt_hex, expected = user["password_hash"].split(":", 1)
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1).hex()
        if not hmac.compare_digest(actual, expected):
            return None
        token = secrets.token_urlsafe(32)
        self.db.execute("INSERT INTO tokens VALUES(?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user["id"], time.time()))
        self.db.commit()
        return token

    def user_for_token(self, token: str):
        digest = hashlib.sha256(token.encode()).hexdigest()
        return self.db.execute("SELECT u.id,u.username,u.role,u.cash FROM tokens t JOIN users u ON u.id=t.user_id WHERE t.token_hash=?", (digest,)).fetchone()

    def submit(self, user, payload: dict):
        now = time.time()
        key = payload.get("idempotency_key")
        if key:
            old = self.db.execute("SELECT * FROM orders WHERE user_id=? AND idempotency_key=?", (user["id"], key)).fetchone()
            if old: return dict(old), {"server_receive_to_submit_us": 0, "engine_submit_us": 0, "server_send_time": time.time()}
        symbol = str(payload.get("symbol", "ASTR")).upper()
        side = str(payload.get("side", "")).lower()
        typ = str(payload.get("type", "limit")).lower()
        qty, price = int(payload.get("quantity", 0)), int(payload.get("price", 0))
        reason = None
        if symbol != "ASTR": reason = "UNKNOWN_SYMBOL"
        elif side not in ("buy", "sell"): reason = "INVALID_SIDE"
        elif typ not in ("limit", "market"): reason = "INVALID_ORDER_TYPE"
        elif qty < 1 or qty > 10000: reason = "INVALID_QUANTITY"
        elif typ == "limit" and (price <= 0 or price % 100): reason = "INVALID_TICK_SIZE"
        elif typ == "limit" and user["cash"] < (price * qty // PRICE_SCALE if side == "buy" else 0): reason = "INSUFFICIENT_BUYING_POWER"
        else:
            position = self.db.execute("SELECT quantity FROM positions WHERE user_id=? AND symbol=?", (user["id"], symbol)).fetchone()
            current = position["quantity"] if position else 0
            if abs(current + (qty if side == "buy" else -qty)) > self.max_position:
                reason = "MAX_POSITION_EXCEEDED"
            book = self.engine.book()
            bid, ask = book.best_bid_price(), book.best_ask_price()
            reference = ((bid + ask) // 2) if bid and ask else (bid or ask)
            if not reason and typ == "limit" and reference and abs(price-reference)*10000 > reference*self.max_price_deviation_bps:
                reason = "PRICE_OUTSIDE_BAND"
        if reason:
            row = (user["id"], symbol, side or "buy", typ, price, max(0, qty), "REJECTED", now, now, key)
            cur = self.db.execute("INSERT INTO orders(user_id,symbol,side,type,price,quantity,status,created,updated,idempotency_key) VALUES(?,?,?,?,?,?,?,?,?,?)", row)
            self.db.commit()
            result = dict(self.db.execute("SELECT * FROM orders WHERE id=?", (cur.lastrowid,)).fetchone())
            result["reason_code"] = reason
            return result, {"server_receive_to_submit_us": 0, "engine_submit_us": 0, "server_send_time": time.time()}
        import exchange_simulator as ex
        order = ex.Order()
        order.id = int(time.time_ns() & 0x7fffffffffffffff)
        order.side = ex.Side.Buy if side == "buy" else ex.Side.Sell
        order.price = price if typ == "limit" else 0
        order.quantity = qty
        order.type = ex.OrderType.Limit if typ == "limit" else ex.OrderType.Market
        order.tif = ex.TimeInForce.GTC
        order.timestamp = time.time_ns()
        start = time.perf_counter_ns()
        fills = self.engine.submit(order)
        elapsed = (time.perf_counter_ns() - start) // 1000
        status = "FILLED" if order.is_filled() else "PARTIALLY_FILLED" if order.filled_quantity else "NEW"
        cur = self.db.execute("INSERT INTO orders(user_id,engine_id,symbol,side,type,price,quantity,filled,status,created,updated,idempotency_key) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
          (user["id"], order.id, symbol, side, typ, price, qty, order.filled_quantity, status, now, time.time(), key))
        oid = cur.lastrowid
        self.order_users[order.id] = user["id"]
        for fill in fills:
            self._apply_fill(user["id"], symbol, side, oid, fill.price, fill.quantity)
        self.db.commit()
        result = dict(self.db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone())
        return result, {"server_receive_to_submit_us": elapsed, "engine_submit_us": elapsed, "server_send_time": time.time()}

    def _apply_fill(self, uid, symbol, side, order_id, price, qty):
        pos = self.db.execute("SELECT * FROM positions WHERE user_id=? AND symbol=?", (uid,symbol)).fetchone()
        oldq, avg, realized = (pos["quantity"], pos["average_price"], pos["realized_pnl"]) if pos else (0,0,0)
        signed = qty if side == "buy" else -qty
        if oldq == 0 or oldq * signed > 0:
            avg = (abs(oldq)*avg + qty*price)//(abs(oldq)+qty)
        else:
            realized += min(abs(oldq), qty) * (price-avg) * (1 if oldq > 0 else -1)
            if abs(signed) > abs(oldq): avg = price
        self.db.execute("INSERT INTO positions VALUES(?,?,?,?,?) ON CONFLICT(user_id,symbol) DO UPDATE SET quantity=excluded.quantity,average_price=excluded.average_price,realized_pnl=excluded.realized_pnl", (uid,symbol,oldq+signed,avg,realized))
        self.db.execute("UPDATE users SET cash=cash+? WHERE id=?", (-price*qty//PRICE_SCALE if side=="buy" else price*qty//PRICE_SCALE, uid))
        self.db.execute("INSERT INTO fills(order_id,price,quantity,created) VALUES(?,?,?,?)", (order_id,price,qty,time.time()))

    def portfolio(self, user_id):
        user=self.db.execute("SELECT cash FROM users WHERE id=?",(user_id,)).fetchone()
        return {"cash":user["cash"],"positions":[dict(r) for r in self.db.execute("SELECT * FROM positions WHERE user_id=?",(user_id,))]}

    def user_orders(self, user_id, status=None):
        if status:
            return [dict(r) for r in self.db.execute("SELECT * FROM orders WHERE user_id=? AND status=? ORDER BY id DESC", (user_id,status.upper()))]
        return [dict(r) for r in self.db.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC", (user_id,))]

    def user_orders(self, user_id, status=None):
        if status:
            return [dict(r) for r in self.db.execute("SELECT * FROM orders WHERE user_id=? AND status=? ORDER BY id DESC", (user_id,status.upper()))]
        return [dict(r) for r in self.db.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC", (user_id,))]
