import os
import json
from typing import Dict, List

REPORTS_FILE = "reports.json"
UPLOAD_DIR = "uploads"
CONFIG_FILE = "app_config.json" # Added CONFIG_FILE here for consistency

def ensure_upload_dir(path=UPLOAD_DIR):
    """Make sure the uploads directory exists."""
    os.makedirs(path, exist_ok=True)

def ensure_reports_file(path=REPORTS_FILE):
    """Make sure reports.json exists (initialize empty list if missing)."""
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump([], f)

def save_media_file(uploaded_file, dest_folder=UPLOAD_DIR, dest_name=None):
    """Save an uploaded media file to the uploads folder."""
    ensure_upload_dir(dest_folder)
    name = dest_name or uploaded_file.name
    path = os.path.join(dest_folder, name)
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return path

def load_config(path=CONFIG_FILE): # Using CONFIG_FILE constant
    """Load app configuration from JSON file (create default if missing)."""
    if not os.path.exists(path):
        default = {
            "app_title": "INCOIS - Ocean Hazard Hub",
            "demo_mode": True,
            "alert_confidence_threshold": 0.7,
            "admin_password": "sih2025",
            "weights": {"ai": 0.6, "social": 0.4}
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(cfg: Dict, path=CONFIG_FILE): # Using CONFIG_FILE constant
    """Save app configuration to JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def save_reports(reports: List[Dict], path=REPORTS_FILE):
    """Save reports list into reports.json."""
    # This function is now superseded by db.insert_report for DB persistence.
    # However, keeping it for local file fallback/consistency if needed.
    with open(path, "w", encoding="utf-8") as f:
        json.dump(reports, f, indent=2)

def next_report_id(path=REPORTS_FILE):
    """
    Generate the next report ID based on existing reports.
    In a full DB integration, this would query the DB for the max ID.
    For file-based reports, it reads the JSON file.
    """
    try:
        # If db.py is imported and functional, it should handle report IDs
        import db
        return db.next_report_id()
    except Exception:
        # Fallback to file-based ID generation if DB is not used/available
        try:
            with open(path, "r", encoding="utf-8") as f:
                reports = json.load(f)
            if reports:
                last_id = max(r.get("id", 0) for r in reports)
                return last_id + 1
            else:
                return 1
        except (FileNotFoundError, json.JSONDecodeError):
            return 1