import aiosqlite
import json
from contextlib import asynccontextmanager
from config.config import config

class Database:
    def __init__(self):
        self.db_path = config.DB_NAME

    @asynccontextmanager
    async def get_connection(self):
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            yield conn

    async def create_tables(self):
        async with self.get_connection() as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous=NORMAL;")
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    arb_alerts INTEGER DEFAULT 0,
                    alert_markets INTEGER DEFAULT 0,
                    alert_events INTEGER DEFAULT 0
                )
            ''')

            await db.execute('''
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    market_id TEXT,
                    market_slug TEXT,
                    alert_price REAL,
                    condition TEXT,
                    outcome TEXT DEFAULT 'YES', 
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )
            ''')

            await db.execute('''
                CREATE TABLE IF NOT EXISTS tracked_wallets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    wallet_address TEXT,
                    alias TEXT,
                    last_tx_hash TEXT,
                    min_vol REAL DEFAULT 0,
                    price_target REAL DEFAULT 0,
                    price_cond TEXT DEFAULT 'NONE',
                    notify_new_markets INTEGER DEFAULT 1,
                    seen_markets TEXT DEFAULT '[]',
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )
            ''')
            
            try:
                await db.execute("ALTER TABLE users ADD COLUMN arb_alerts INTEGER DEFAULT 0")
            except: pass

            try:
                await db.execute("ALTER TABLE users ADD COLUMN alert_markets INTEGER DEFAULT 0")
            except: pass

            try:
                await db.execute("ALTER TABLE users ADD COLUMN alert_events INTEGER DEFAULT 0")
            except: pass
            
            await db.commit()

    async def add_user(self, user_id, username):
        async with self.get_connection() as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", 
                (user_id, username)
            )
            await db.commit()

    async def get_user_settings(self, user_id):
        async with self.get_connection() as db:
            cursor = await db.execute("SELECT arb_alerts, alert_markets, alert_events FROM users WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
            return dict(row) if row else {'arb_alerts': 0, 'alert_markets': 0, 'alert_events': 0}

    async def toggle_arb_alerts(self, user_id):
        async with self.get_connection() as db:
            cursor = await db.execute("SELECT arb_alerts FROM users WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
            current = row['arb_alerts'] if row else 0
            new_val = 1 if current == 0 else 0
            await db.execute("UPDATE users SET arb_alerts = ? WHERE user_id = ?", (new_val, user_id))
            await db.commit()
            return new_val

    async def toggle_market_alerts(self, user_id):
        async with self.get_connection() as db:
            cursor = await db.execute("SELECT alert_markets FROM users WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
            current = row['alert_markets'] if row else 0
            new_val = 1 if current == 0 else 0
            await db.execute("UPDATE users SET alert_markets = ? WHERE user_id = ?", (new_val, user_id))
            await db.commit()
            return new_val

    async def toggle_event_alerts(self, user_id):
        async with self.get_connection() as db:
            cursor = await db.execute("SELECT alert_events FROM users WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
            current = row['alert_events'] if row else 0
            new_val = 1 if current == 0 else 0
            await db.execute("UPDATE users SET alert_events = ? WHERE user_id = ?", (new_val, user_id))
            await db.commit()
            return new_val

    async def get_users_for_arb(self):
        async with self.get_connection() as db:
            cursor = await db.execute("SELECT user_id FROM users WHERE arb_alerts = 1")
            rows = await cursor.fetchall()
            return [row['user_id'] for row in rows]

    async def get_users_for_markets(self):
        async with self.get_connection() as db:
            cursor = await db.execute("SELECT user_id FROM users WHERE alert_markets = 1")
            rows = await cursor.fetchall()
            return [row['user_id'] for row in rows]

    async def get_users_for_events(self):
        async with self.get_connection() as db:
            cursor = await db.execute("SELECT user_id FROM users WHERE alert_events = 1")
            rows = await cursor.fetchall()
            return [row['user_id'] for row in rows]

    async def add_to_watchlist(self, user_id, market_id, slug, price, condition, outcome="YES"):
        async with self.get_connection() as db:
            await db.execute(
                "INSERT INTO watchlist (user_id, market_id, market_slug, alert_price, condition, outcome) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, market_id, slug, price, condition, outcome)
            )
            await db.commit()

    async def get_all_watchlists(self):
        async with self.get_connection() as db:
            cursor = await db.execute("SELECT * FROM watchlist")
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_user_watchlist(self, user_id):
        async with self.get_connection() as db:
            cursor = await db.execute("SELECT * FROM watchlist WHERE user_id = ?", (user_id,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_alert_by_id(self, alert_id):
        async with self.get_connection() as db:
            cursor = await db.execute("SELECT * FROM watchlist WHERE id = ?", (alert_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_alert(self, alert_id, price, condition, outcome):
        async with self.get_connection() as db:
            await db.execute(
                "UPDATE watchlist SET alert_price = ?, condition = ?, outcome = ? WHERE id = ?",
                (price, condition, outcome, alert_id)
            )
            await db.commit()

    async def delete_alert(self, alert_id, user_id):
        async with self.get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM watchlist WHERE id = ? AND user_id = ?", 
                (alert_id, user_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def add_wallet(self, user_id, address, alias):
        async with self.get_connection() as db:
            await db.execute(
                "INSERT INTO tracked_wallets (user_id, wallet_address, alias, seen_markets) VALUES (?, ?, ?, ?)",
                (user_id, address, alias, json.dumps([]))
            )
            await db.commit()

    async def get_tracked_wallets(self):
        async with self.get_connection() as db:
            cursor = await db.execute("SELECT * FROM tracked_wallets")
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_user_wallets(self, user_id):
        async with self.get_connection() as db:
            cursor = await db.execute("SELECT * FROM tracked_wallets WHERE user_id = ?", (user_id,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def get_wallet_by_id(self, wallet_id):
        async with self.get_connection() as db:
            cursor = await db.execute("SELECT * FROM tracked_wallets WHERE id = ?", (wallet_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def delete_wallet(self, wallet_id, user_id):
        async with self.get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM tracked_wallets WHERE id = ? AND user_id = ?", 
                (wallet_id, user_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def update_wallet_tx(self, wallet_id, tx_hash):
        async with self.get_connection() as db:
            await db.execute(
                "UPDATE tracked_wallets SET last_tx_hash = ? WHERE id = ?", 
                (tx_hash, wallet_id)
            )
            await db.commit()

    async def update_wallet_seen_markets(self, wallet_id, seen_list):
        async with self.get_connection() as db:
            await db.execute(
                "UPDATE tracked_wallets SET seen_markets = ? WHERE id = ?",
                (json.dumps(seen_list), wallet_id)
            )
            await db.commit()

    async def update_wallet_settings(self, wallet_id, min_vol, price_target, price_cond, notify_new):
        async with self.get_connection() as db:
            await db.execute(
                '''
                UPDATE tracked_wallets 
                SET min_vol = ?, price_target = ?, price_cond = ?, notify_new_markets = ?
                WHERE id = ?
                ''',
                (min_vol, price_target, price_cond, notify_new, wallet_id)
            )
            await db.commit()

db = Database()