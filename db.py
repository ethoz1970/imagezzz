import sqlite3
import os
import time
import uuid
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "imagezzz.db")

def init_db():
    """Create tables if they don't exist. Call once at app startup."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            role TEXT DEFAULT 'free',
            token_balance INTEGER DEFAULT 0,
            tracking_id TEXT,
            created_at REAL,
            last_login REAL
        );

        CREATE TABLE IF NOT EXISTS token_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(id),
            amount INTEGER NOT NULL,
            balance_after INTEGER NOT NULL,
            type TEXT NOT NULL,
            stripe_session_id TEXT,
            description TEXT,
            created_at REAL
        );

        CREATE TABLE IF NOT EXISTS gen_sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT REFERENCES users(id),
            tracking_id TEXT,
            name TEXT,
            public INTEGER DEFAULT 0,
            created_at REAL
        );

        CREATE TABLE IF NOT EXISTS images (
            filename TEXT PRIMARY KEY,
            session_id TEXT REFERENCES gen_sessions(id),
            user_id TEXT REFERENCES users(id),
            tracking_id TEXT,
            prompt TEXT,
            original_prompt TEXT,
            generation_time REAL,
            public INTEGER DEFAULT 0,
            created_at REAL
        );

        CREATE INDEX IF NOT EXISTS idx_gen_sessions_tracking ON gen_sessions(tracking_id);
        CREATE INDEX IF NOT EXISTS idx_gen_sessions_user ON gen_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_images_session ON images(session_id);
        CREATE INDEX IF NOT EXISTS idx_images_user ON images(user_id);
        CREATE INDEX IF NOT EXISTS idx_images_tracking ON images(tracking_id);
        CREATE INDEX IF NOT EXISTS idx_token_tx_user ON token_transactions(user_id);
        CREATE INDEX IF NOT EXISTS idx_users_tracking ON users(tracking_id);
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
    """)
    conn.close()


def get_db():
    """Get a new database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# --- User helpers ---

def create_user(email, password_hash, display_name=None, tracking_id=None):
    user_id = str(uuid.uuid4())
    now = time.time()
    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (id, email, password_hash, display_name, role, token_balance, tracking_id, created_at, last_login) "
            "VALUES (?, ?, ?, ?, 'free', 0, ?, ?, ?)",
            (user_id, email.lower().strip(), password_hash, display_name, tracking_id, now, now)
        )
        db.commit()
        return user_id
    finally:
        db.close()


def get_user_by_email(email):
    db = get_db()
    try:
        row = db.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),)).fetchone()
        return dict(row) if row else None
    finally:
        db.close()


def get_user_by_id(user_id):
    db = get_db()
    try:
        row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        db.close()


def update_last_login(user_id):
    db = get_db()
    try:
        db.execute("UPDATE users SET last_login = ? WHERE id = ?", (time.time(), user_id))
        db.commit()
    finally:
        db.close()


def claim_anonymous_data(user_id, tracking_id):
    """Link anonymous sessions/images to a registered user."""
    db = get_db()
    try:
        db.execute(
            "UPDATE gen_sessions SET user_id = ? WHERE tracking_id = ? AND user_id IS NULL",
            (user_id, tracking_id)
        )
        db.execute(
            "UPDATE images SET user_id = ? WHERE tracking_id = ? AND user_id IS NULL",
            (user_id, tracking_id)
        )
        db.execute(
            "UPDATE users SET tracking_id = ? WHERE id = ? AND tracking_id IS NULL",
            (tracking_id, user_id)
        )
        db.commit()
    finally:
        db.close()


# --- Token helpers ---

def get_token_balance(user_id):
    db = get_db()
    try:
        row = db.execute("SELECT token_balance FROM users WHERE id = ?", (user_id,)).fetchone()
        return row["token_balance"] if row else 0
    finally:
        db.close()


def credit_tokens(user_id, amount, tx_type, stripe_session_id=None, description=""):
    """Add tokens to a user's balance. Returns new balance."""
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT token_balance FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            db.execute("ROLLBACK")
            raise ValueError("User not found")

        # Idempotency: skip if this Stripe session was already processed
        if stripe_session_id:
            existing = db.execute(
                "SELECT id FROM token_transactions WHERE stripe_session_id = ?",
                (stripe_session_id,)
            ).fetchone()
            if existing:
                db.execute("ROLLBACK")
                return row["token_balance"]

        new_balance = row["token_balance"] + amount
        db.execute("UPDATE users SET token_balance = ? WHERE id = ?", (new_balance, user_id))
        db.execute(
            "INSERT INTO token_transactions (user_id, amount, balance_after, type, stripe_session_id, description, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, amount, new_balance, tx_type, stripe_session_id, description, time.time())
        )
        db.commit()
        return new_balance
    except Exception:
        db.execute("ROLLBACK")
        raise
    finally:
        db.close()


class InsufficientTokens(Exception):
    pass


def deduct_tokens(user_id, amount, tx_type="generation", description=""):
    """Remove tokens from a user's balance. Raises InsufficientTokens if not enough."""
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT token_balance FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            db.execute("ROLLBACK")
            raise ValueError("User not found")

        if row["token_balance"] < amount:
            db.execute("ROLLBACK")
            raise InsufficientTokens(f"Need {amount} tokens, have {row['token_balance']}")

        new_balance = row["token_balance"] - amount
        db.execute("UPDATE users SET token_balance = ? WHERE id = ?", (new_balance, user_id))
        db.execute(
            "INSERT INTO token_transactions (user_id, amount, balance_after, type, description, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, -amount, new_balance, tx_type, description, time.time())
        )
        db.commit()
        return new_balance
    except InsufficientTokens:
        raise
    except Exception:
        db.execute("ROLLBACK")
        raise
    finally:
        db.close()


# --- Session helpers ---

def save_gen_session(session_id, name, tracking_id, user_id=None, public=False, created_at=None):
    db = get_db()
    try:
        db.execute(
            "INSERT OR REPLACE INTO gen_sessions (id, user_id, tracking_id, name, public, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, user_id, tracking_id, name, 1 if public else 0, created_at or time.time())
        )
        db.commit()
    finally:
        db.close()


def get_all_sessions():
    db = get_db()
    try:
        rows = db.execute("SELECT * FROM gen_sessions ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def get_sessions_by_tracking(tracking_id):
    db = get_db()
    try:
        rows = db.execute(
            "SELECT * FROM gen_sessions WHERE tracking_id = ? ORDER BY created_at DESC",
            (tracking_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def get_sessions_by_user(user_id):
    db = get_db()
    try:
        rows = db.execute(
            "SELECT * FROM gen_sessions WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def get_session_by_id(session_id):
    db = get_db()
    try:
        row = db.execute("SELECT * FROM gen_sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row) if row else None
    finally:
        db.close()


def delete_gen_session(session_id):
    db = get_db()
    try:
        db.execute("DELETE FROM images WHERE session_id = ?", (session_id,))
        db.execute("DELETE FROM gen_sessions WHERE id = ?", (session_id,))
        db.commit()
    finally:
        db.close()


def update_session_name(session_id, name):
    db = get_db()
    try:
        db.execute("UPDATE gen_sessions SET name = ? WHERE id = ?", (name, session_id))
        db.commit()
    finally:
        db.close()


def update_session_public(session_id, public):
    db = get_db()
    try:
        db.execute("UPDATE gen_sessions SET public = ? WHERE id = ?", (1 if public else 0, session_id))
        db.execute("UPDATE images SET public = ? WHERE session_id = ?", (1 if public else 0, session_id))
        db.commit()
    finally:
        db.close()


# --- Image helpers ---

def save_image(filename, session_id, tracking_id, prompt, original_prompt,
               generation_time=None, user_id=None, public=False, created_at=None):
    db = get_db()
    try:
        db.execute(
            "INSERT OR REPLACE INTO images (filename, session_id, user_id, tracking_id, prompt, original_prompt, generation_time, public, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (filename, session_id, user_id, tracking_id, prompt, original_prompt,
             generation_time, 1 if public else 0, created_at or time.time())
        )
        db.commit()
    finally:
        db.close()


def get_images_by_session(session_id):
    db = get_db()
    try:
        rows = db.execute(
            "SELECT * FROM images WHERE session_id = ? ORDER BY created_at DESC",
            (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def get_image_by_filename(filename):
    db = get_db()
    try:
        row = db.execute("SELECT * FROM images WHERE filename = ?", (filename,)).fetchone()
        return dict(row) if row else None
    finally:
        db.close()


def delete_image(filename):
    db = get_db()
    try:
        db.execute("DELETE FROM images WHERE filename = ?", (filename,))
        db.commit()
    finally:
        db.close()


def toggle_image_public(filename):
    """Toggle public flag. Returns new value."""
    db = get_db()
    try:
        row = db.execute("SELECT public FROM images WHERE filename = ?", (filename,)).fetchone()
        if not row:
            return None
        new_val = 0 if row["public"] else 1
        db.execute("UPDATE images SET public = ? WHERE filename = ?", (new_val, filename))
        db.commit()
        return bool(new_val)
    finally:
        db.close()


# --- Rate limiting (for free tier, replaces daily_limits.json) ---

def get_free_usage_count(identifier, window_hours=8):
    """Count generations in the rolling window for a tracking_id or user_id."""
    cutoff = time.time() - window_hours * 3600
    db = get_db()
    try:
        # Check by tracking_id first, then user_id
        row = db.execute(
            "SELECT COUNT(*) as cnt, MIN(created_at) as oldest FROM images "
            "WHERE (tracking_id = ? OR user_id = ?) AND created_at > ?",
            (identifier, identifier, cutoff)
        ).fetchone()
        return row["cnt"], row["oldest"]
    finally:
        db.close()


# --- Admin helpers ---

def get_all_users():
    db = get_db()
    try:
        rows = db.execute("SELECT id, email, display_name, role, token_balance, tracking_id, created_at, last_login FROM users ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def set_user_role(user_id, role):
    db = get_db()
    try:
        db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        db.commit()
    finally:
        db.close()
