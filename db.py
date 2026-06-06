import os
import json
from flask import g
import psycopg
from psycopg.rows import dict_row
from contextlib import contextmanager

# Get database URL from environment
DATABASE_URL = os.environ.get('DATABASE_URL')

@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    if not DATABASE_URL:
        raise Exception("DATABASE_URL environment variable not set")
    
    # Fix Render's postgres:// URL if needed
    db_url = DATABASE_URL
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    
    conn = psycopg.connect(db_url, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_db():
    """Get database connection for Flask request context"""
    if 'db_conn' not in g:
        if not DATABASE_URL:
            raise Exception("DATABASE_URL environment variable not set")
        
        db_url = DATABASE_URL
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)
        
        g.db_conn = psycopg.connect(db_url, row_factory=dict_row)
    return g.db_conn

def close_db(e=None):
    """Close database connection when request ends"""
    if 'db_conn' in g:
        g.db_conn.close()
        del g.db_conn

def init_db(app):
    """Initialize database tables using modern PostgreSQL syntax"""
    app.teardown_appcontext(close_db)
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    phone TEXT UNIQUE,
                    password_hash TEXT NOT NULL,
                    balance DECIMAL DEFAULT 0.0,
                    role TEXT DEFAULT 'user',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1
                )
            """)
            
            # Transactions table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    type TEXT NOT NULL,
                    amount DECIMAL NOT NULL,
                    status TEXT DEFAULT 'pending',
                    reference TEXT,
                    note TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Matchdays table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS matchdays (
                    id SERIAL PRIMARY KEY,
                    matchday_number INTEGER NOT NULL,
                    league TEXT NOT NULL,
                    starts_at TIMESTAMP NOT NULL,
                    status TEXT DEFAULT 'upcoming',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Matches table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS matches (
                    id SERIAL PRIMARY KEY,
                    matchday_id INTEGER NOT NULL REFERENCES matchdays(id) ON DELETE CASCADE,
                    home_code TEXT NOT NULL,
                    away_code TEXT NOT NULL,
                    home_team TEXT NOT NULL,
                    away_team TEXT NOT NULL,
                    league TEXT NOT NULL,
                    home_score INTEGER DEFAULT 0,
                    away_score INTEGER DEFAULT 0,
                    ht_home INTEGER DEFAULT 0,
                    ht_away INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'upcoming',
                    current_minute INTEGER DEFAULT 0,
                    kickoff_time TIMESTAMP,
                    preset_home INTEGER DEFAULT NULL,
                    preset_away INTEGER DEFAULT NULL,
                    odds_json TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Match events table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS match_events (
                    id SERIAL PRIMARY KEY,
                    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
                    minute INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    description TEXT,
                    team TEXT,
                    is_home INTEGER DEFAULT 1
                )
            """)
            
            # Bets table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bets (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    total_stake DECIMAL NOT NULL,
                    potential_win DECIMAL NOT NULL,
                    status TEXT DEFAULT 'pending',
                    placed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    settled_at TIMESTAMP
                )
            """)
            
            # Bet selections table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bet_selections (
                    id SERIAL PRIMARY KEY,
                    bet_id INTEGER NOT NULL REFERENCES bets(id) ON DELETE CASCADE,
                    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
                    market TEXT NOT NULL,
                    selection TEXT NOT NULL,
                    odds DECIMAL NOT NULL,
                    result TEXT DEFAULT 'pending'
                )
            """)
            
            # Admin logs table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin_logs (
                    id SERIAL PRIMARY KEY,
                    admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    action TEXT NOT NULL,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for better performance
            cur.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_bets_user_id ON bets(user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_bets_status ON bets(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_matchday_id ON matches(matchday_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id)")

def query(sql, params=(), one=False):
    """Execute a SELECT query and return results"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Convert %s placeholders to PostgreSQL format
            # psycopg v3 uses %s format, but we need to handle it properly
            cur.execute(sql, params)
            if one:
                return cur.fetchone()
            return cur.fetchall()

def execute(sql, params=()):
    """Execute an INSERT/UPDATE/DELETE query and return lastrowid"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            # For INSERT queries, return the last inserted ID
            if sql.strip().upper().startswith('INSERT'):
                cur.execute("SELECT LASTVAL()")
                result = cur.fetchone()
                return result['lastval'] if result else None
            return None
