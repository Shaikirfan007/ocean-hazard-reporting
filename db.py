import sqlite3
import json
from typing import List, Dict, Optional
from datetime import datetime
import os
import logging

logger = logging.getLogger(__name__)

DB_FILE = "data/app.db" 
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY,
    hazard_type TEXT,
    description TEXT,
    location TEXT,
    latlon TEXT,
    timestamp TEXT,
    ai_label TEXT,
    ai_confidence REAL,
    final_confidence REAL,
    ai_is_real INTEGER,
    severity TEXT,
    reporter_id TEXT,
    media_path TEXT,
    status TEXT,
    social_evidence TEXT -- Stored as JSON string
);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY, -- User ID (e.g., username for simplicity or a UUID)
    username TEXT UNIQUE NOT NULL, -- NEW: For login
    password_hash TEXT NOT NULL, -- NEW: For storing hashed password
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    preferred_location TEXT
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER,
    user_id TEXT, 
    channel TEXT,
    status TEXT, 
    detail TEXT, 
    timestamp TEXT,
    FOREIGN KEY (report_id) REFERENCES reports (id),
    FOREIGN KEY (user_id) REFERENCES users (id) 
);
"""

def ensure_db():
    """Ensures the database file and its directory exist, and creates tables if they don't."""
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
    logger.info(f"Database ensured at: {DB_FILE}")

def insert_report(report: Dict):
    """
    Inserts or replaces a report record in the database.
    Note: 'social_evidence' is converted to a JSON string for storage.
    """
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cols = ("id", "hazard_type", "description", "location", "latlon", "timestamp",
            "ai_label", "ai_confidence", "final_confidence", "ai_is_real",
            "severity", "reporter_id", "media_path", "status", "social_evidence")
    
    report_data = report.copy()
    if 'social_evidence' in report_data and isinstance(report_data['social_evidence'], dict):
        report_data['social_evidence'] = json.dumps(report_data['social_evidence'])
    else:
        report_data['social_evidence'] = None 

    vals = tuple(report_data.get(c) for c in cols)
    
    q = f"""INSERT OR REPLACE INTO reports ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})"""
    cur.execute(q, vals)
    conn.commit()
    conn.close()
    logger.debug(f"Inserted/Updated report ID {report.get('id')} with location '{report.get('location')}'")

def update_report_status_and_confidence(report_id: int, status: str, ai_is_real: bool, final_confidence: float):
    """
    Updates the status, ai_is_real flag, and final_confidence of a report in the database.
    This is used for manual official review.
    """
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    q = """UPDATE reports SET status=?, ai_is_real=?, final_confidence=? WHERE id=?"""
    cur.execute(q, (status, 1 if ai_is_real else 0, final_confidence, report_id))
    conn.commit()
    conn.close()
    logger.info(f"Report ID {report_id} manually updated to Status: '{status}', Likely Real: {ai_is_real}, Final Confidence: {final_confidence}")


def get_report_by_id(report_id: int) -> Optional[Dict]:
    """
    Fetches a single report by its ID.
    Converts 'social_evidence' JSON string back to a dictionary.
    """
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        column_names = [description[0] for description in cur.description]
        rec = dict(zip(column_names, row))
        if rec.get("social_evidence"):
            try:
                rec["social_evidence"] = json.loads(rec["social_evidence"])
            except json.JSONDecodeError:
                rec["social_evidence"] = None 
        return rec
    return None

def next_report_id() -> int:
    """Returns the next available report ID."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT MAX(id) FROM reports")
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        return row[0] + 1
    return 1

def load_reports(limit: Optional[int]=None) -> List[Dict]:
    """
    Loads reports from the database, optionally limiting the number.
    Converts 'social_evidence' JSON string back to a dictionary.
    """
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    q = "SELECT * FROM reports ORDER BY timestamp DESC"
    if limit:
        q += f" LIMIT {limit}"
    cur.execute(q)
    rows = cur.fetchall()
    
    column_names = [description[0] for description in cur.description]

    results = []
    for r in rows:
        rec = dict(zip(column_names, r))
        if rec.get("social_evidence"):
            try:
                rec["social_evidence"] = json.loads(rec["social_evidence"])
            except json.JSONDecodeError:
                rec["social_evidence"] = None 
        results.append(rec)
    conn.close()
    logger.debug(f"Loaded {len(results)} reports from DB.")
    return results

def insert_or_update_user(user_data: Dict):
    """
    Inserts a new user or updates an existing user's details,
    including username, password_hash, name, role, and preferred_location.
    """
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    
    user_id = user_data["id"] # This is usually the username now
    username = user_data["username"]
    password_hash = user_data["password_hash"]
    name = user_data["name"]
    role = user_data["role"]
    preferred_location = user_data.get("preferred_location")

    cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    existing_user = cur.fetchone()

    if existing_user:
        q = """UPDATE users SET username=?, password_hash=?, name=?, role=?, preferred_location=? WHERE id=?"""
        cur.execute(q, (username, password_hash, name, role, preferred_location, user_id))
        logger.debug(f"Updated user ID {user_id} (username: {username}) with preferred_location '{preferred_location}'")
    else:
        q = """INSERT INTO users (id, username, password_hash, name, role, preferred_location) VALUES (?,?,?,?,?,?)"""
        cur.execute(q, (user_id, username, password_hash, name, role, preferred_location))
        logger.debug(f"Inserted user ID {user_id} (username: {username}) with preferred_location '{preferred_location}'")
    conn.commit()
    conn.close()

def load_users() -> List[Dict]:
    """Loads all users from the database (without password hashes)."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    # Exclude password_hash for general loading
    cur.execute("SELECT id, username, name, role, preferred_location FROM users")
    rows = cur.fetchall()
    column_names = [description[0] for description in cur.description]
    results = [dict(zip(column_names, r)) for r in rows]
    conn.close()
    logger.debug(f"Loaded {len(results)} users from DB.")
    return results

def get_user_by_username(username: str) -> Optional[Dict]:
    """
    Fetches a single user's details by username, including the password hash, for authentication.
    """
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id, username, password_hash, name, role, preferred_location FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    if row:
        column_names = [description[0] for description in cur.description]
        user_data = dict(zip(column_names, row))
        logger.debug(f"Fetched user '{username}' from DB.")
        return user_data
    logger.debug(f"User '{username}' not found in DB.")
    return None

def save_alert_history_entry(entry: Dict):
    """Saves an alert history entry to the 'alerts' table, including user_id."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT INTO alerts (report_id, user_id, channel, status, detail, timestamp) VALUES (?,?,?,?,?,?)",
                (entry.get("report_id"), entry.get("user_id"), entry.get("channel"), entry.get("status"), entry.get("detail"), entry.get("timestamp")))
    conn.commit()
    conn.close()
    logger.debug(f"Saved alert for report {entry.get('report_id')} to user {entry.get('user_id')} with status '{entry.get('status')}'")


def get_alerts_with_report_and_user_info(location: Optional[str] = None) -> List[Dict]:
    """
    Loads alerts, joining with reports to get location and description,
    and with users to get the original reporter's name.
    Optionally filters by report location.
    """
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    query = """
    SELECT
        a.id AS alert_id,
        a.report_id,
        r.location AS report_location,
        r.description AS report_description,
        r.hazard_type AS report_hazard_type,
        u_reporter.name AS reporter_name, -- Name of the user who submitted the report
        a.user_id AS alert_recipient_id, -- ID of the user who received this alert
        u_recipient.name AS alert_recipient_name, -- Name of the user who received this alert
        a.channel,
        a.status,
        a.detail,
        a.timestamp
    FROM
        alerts a
    JOIN
        reports r ON a.report_id = r.id
    LEFT JOIN -- Use LEFT JOIN for users in case reporter_id is null or user doesn't exist
        users u_reporter ON r.reporter_id = u_reporter.id
    LEFT JOIN -- Use LEFT JOIN for users who received the alert (if user_id is null for system alerts)
        users u_recipient ON a.user_id = u_recipient.id
    """
    params = []

    if location and location != "All":
        query += " WHERE LOWER(r.location) LIKE LOWER(?)"
        params.append(location) 
        logger.debug(f"DB Querying alerts for normalized location: '{location}'")

    query += " ORDER BY a.timestamp DESC"

    cur.execute(query, params)
    rows = cur.fetchall()
    
    column_names = [description[0] for description in cur.description]
    
    results = [dict(zip(column_names, row)) for row in rows]
    conn.close()
    logger.debug(f"Fetched {len(results)} alerts from DB for location '{location or 'All'}'.")
    return results