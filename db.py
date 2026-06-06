import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
from flask import g
from contextlib import contextmanager

# Connection pool for better performance
db_pool = None

def get_db_pool():
    global db_pool
    if db_pool is None:
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            raise Exception("DATABASE_URL environment variable not set")
        
        # Render provides postgres://, but psycopg2 needs postgresql://
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        
        # Create connection pool (min 1, max 10 connections)
        db_pool = ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=database_url
        )
    return db_pool

@contextmanager
def get_db_cursor():
    """Context manager for database connections - use this in all routes"""
    pool = get_db_pool()
    conn = pool.getconn()
    try:
        yield conn.cursor(cursor_factory=RealDictCursor)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)

def get_db():
    """Backward compatibility for existing code that expects g.db"""
    if 'db_conn' not in g:
        pool = get_db_pool()
        g.db_conn = pool.getconn()
        g.db_cursor = g.db_conn.cursor(cursor_factory=RealDictCursor)
    return g.db_cursor

def close_db(e=None):
    """Return connection to pool when request ends"""
    if 'db_conn' in g:
        pool = get_db_pool()
        pool.putconn(g.db_conn)
        del g.db_conn
        del g.db_cursor

def init_db(app):
    """Initialize database tables using PostgreSQL syntax"""
    app.teardown_appcontext(close_db)
    
    with get_db_cursor() as cur:
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
        cur.execute("CREATE INDEX IF NOT EXISTS idx_admin_logs_timestamp ON admin_logs(timestamp)")

def query(sql, params=(), one=False):
    """Execute a SELECT query and return results"""
    with get_db_cursor() as cur:
        cur.execute(sql, params)
        if one:
            return cur.fetchone()
        return cur.fetchall()

def execute(sql, params=()):
    """Execute an INSERT/UPDATE/DELETE query and return lastrowid"""
    with get_db_cursor() as cur:
        cur.execute(sql, params)
        # For INSERT queries, return the last inserted ID
        if sql.strip().upper().startswith('INSERT'):
            cur.execute("SELECT LASTVAL()")
            return cur.fetchone()['lastval']
        return None