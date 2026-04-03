"""SQLite database initialization and connection management."""
import aiosqlite
from pathlib import Path
from typing import Optional
from utils.logger import logger

# Database path: <project_root>/backend/data/admin.db
DB_PATH = Path(__file__).parent.parent.parent / "backend" / "data" / "admin.db"


class _DatabaseContext:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def __aenter__(self) -> aiosqlite.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


async def get_db() -> _DatabaseContext:
    """Return an async context manager for a SQLite connection.

    Existing code uses `async with await get_db() as db:`. Returning this wrapper
    preserves that calling convention while ensuring the connection is opened and
    closed exactly once per usage.
    """
    return _DatabaseContext(DB_PATH)


async def init_db() -> None:
    """Create all tables if they do not exist and seed initial config."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # ──────────────────────────────────────────────
        # admin_config – single-row system configuration
        # ──────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                notebooklm_url TEXT NOT NULL DEFAULT '',
                default_language TEXT NOT NULL DEFAULT 'en',
                active_theme_id TEXT NOT NULL DEFAULT 'T02',
                config_version INTEGER NOT NULL DEFAULT 1,
                maintenance_mode INTEGER NOT NULL DEFAULT 0,
                maintenance_title TEXT NOT NULL DEFAULT '',
                maintenance_message TEXT NOT NULL DEFAULT '',
                maintenance_start TEXT,
                maintenance_end TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # ──────────────────────────────────────────────
        # notice_banner – maintenance announcement
        # ──────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notice_banner (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                title TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                start_time TEXT,
                end_time TEXT,
                timezone TEXT NOT NULL DEFAULT 'America/Toronto',
                severity TEXT NOT NULL DEFAULT 'info',
                enabled INTEGER NOT NULL DEFAULT 0,
                version INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # ──────────────────────────────────────────────
        # themes – preset and custom themes
        # ──────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS themes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                is_preset INTEGER NOT NULL DEFAULT 0,
                definition TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # ──────────────────────────────────────────────
        # theme_snapshots – last 3 active-theme snapshots
        # ──────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS theme_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                theme_id TEXT NOT NULL,
                definition TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # ──────────────────────────────────────────────
        # chat_logs – user request summary log
        # No IP fields – Law 25 compliance
        # ──────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL DEFAULT '',
                requested_at TEXT NOT NULL DEFAULT (datetime('now')),
                question_summary TEXT NOT NULL DEFAULT '',
                answer_summary TEXT NOT NULL DEFAULT '',
                user_agent TEXT NOT NULL DEFAULT '',
                browser_name TEXT NOT NULL DEFAULT '',
                browser_version TEXT NOT NULL DEFAULT '',
                os_name TEXT NOT NULL DEFAULT '',
                os_version TEXT NOT NULL DEFAULT '',
                device_type TEXT NOT NULL DEFAULT '',
                country TEXT NOT NULL DEFAULT '',
                province TEXT NOT NULL DEFAULT '',
                city TEXT NOT NULL DEFAULT '',
                language_pref TEXT NOT NULL DEFAULT '',
                referer TEXT NOT NULL DEFAULT '',
                response_ms INTEGER NOT NULL DEFAULT 0,
                is_error INTEGER NOT NULL DEFAULT 0,
                error_summary TEXT,
                error_detail TEXT,
                google_raw_request TEXT,
                google_raw_response TEXT
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_chat_logs_session ON chat_logs(session_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_chat_logs_requested_at ON chat_logs(requested_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_chat_logs_is_error ON chat_logs(is_error)")

        # ──────────────────────────────────────────────
        # admin_audit_logs
        # ──────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_email TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL DEFAULT '',
                result TEXT NOT NULL DEFAULT 'success',
                before_summary TEXT,
                after_summary TEXT,
                browser TEXT NOT NULL DEFAULT '',
                os TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON admin_audit_logs(created_at)")

        # ──────────────────────────────────────────────
        # admin_sessions
        # ──────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_sessions (
                id TEXT PRIMARY KEY,
                admin_email TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                expires_at TEXT NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0
            )
        """)

        # ──────────────────────────────────────────────
        # notebooklm_auth_jobs
        # ──────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notebooklm_auth_jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                method TEXT NOT NULL DEFAULT 'browser',
                auth_url TEXT,
                started_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                admin_email TEXT NOT NULL DEFAULT ''
            )
        """)

        # ──────────────────────────────────────────────
        # Seed: admin_config (single row, id=1)
        # ──────────────────────────────────────────────
        await db.execute("""
            INSERT OR IGNORE INTO admin_config (id) VALUES (1)
        """)

        # ──────────────────────────────────────────────
        # Seed: notice_banner (single row, id=1)
        # ──────────────────────────────────────────────
        await db.execute("""
            INSERT OR IGNORE INTO notice_banner (id) VALUES (1)
        """)

        # ──────────────────────────────────────────────
        # Seed: preset themes
        # ──────────────────────────────────────────────
        preset_themes = [
            ("T01", "Classic Gold", '{"primary":"#F59E0B","background":"#FFFBEB","headerBg":"from-yellow-500 to-yellow-600","userBubble":"bg-blue-600","assistantBubble":"bg-white"}'),
            ("T02", "Professional Blue", '{"primary":"#1D4ED8","background":"#EFF6FF","headerBg":"from-blue-700 to-blue-800","userBubble":"bg-blue-700","assistantBubble":"bg-white"}'),
            ("T03", "Fresh Green", '{"primary":"#059669","background":"#ECFDF5","headerBg":"from-green-600 to-green-700","userBubble":"bg-green-700","assistantBubble":"bg-white"}'),
            ("T04", "Dark Minimal", '{"primary":"#6366F1","background":"#1E1E2E","headerBg":"from-gray-900 to-gray-800","userBubble":"bg-indigo-600","assistantBubble":"bg-gray-800"}'),
            ("T05", "Saint-Louis Campus", '{"primary":"#1E3A5F","background":"#F8F9FA","headerBg":"from-blue-900 to-blue-800","userBubble":"bg-blue-900","assistantBubble":"bg-white"}'),
        ]
        for theme_id, name, definition in preset_themes:
            await db.execute(
                "INSERT OR IGNORE INTO themes (id, name, is_preset, definition) VALUES (?, ?, 1, ?)",
                (theme_id, name, definition)
            )

        await db.commit()
    logger.info("Database initialized at %s", DB_PATH)
