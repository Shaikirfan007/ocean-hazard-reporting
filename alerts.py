import logging
from datetime import datetime
from typing import Dict, List, Optional
import json
import os

logger = logging.getLogger(__name__)

_db_functions_are_fallback = False

try:
    from db import save_alert_history_entry, load_users
except Exception:
    logger.error("Could not import db functions. Using fallback for alert history.", exc_info=True)
    _db_functions_are_fallback = True

    def save_alert_history_entry(entry: Dict):
        try:
            path = "alert_history.json"
            lst = []
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    lst = json.load(f) or []
            lst.append(entry)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(lst, f, indent=2)
        except Exception as e:
            logger.exception("Failed to save fallback alert history entry: %s", e)

    def load_users() -> List[Dict]:
        return []

def normalize_location_string_for_alerts(location_input: str) -> str:
    """Normalizes a location string for consistent comparison."""
    if not location_input:
        return ""
    return location_input.strip().title()


class AlertSystem:
    def __init__(self, demo_mode: bool = True, threshold: float = 0.7):
        # DEBUG PRINT: Added for visibility, can remove later
        print(f"DEBUG: AlertSystem _init_ called with demo_mode={demo_mode}, threshold={threshold}")
        self.demo_mode = demo_mode
        self.threshold = threshold
        self.alert_history: List[Dict] = self._load_fallback_alert_history() if _db_functions_are_fallback else []
        logger.info(f"AlertSystem initialized. Demo Mode: {self.demo_mode}, Threshold: {self.threshold:.2f}")


    def _load_fallback_alert_history(self) -> List[Dict]:
        try:
            path = "alert_history.json"
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f) or []
        except Exception:
            logger.exception("Failed to load fallback alert history.")
        return []

    def should_send_report(self, report: Dict) -> bool:
        """
        Determines if the report itself is worthy of an alert based on confidence and severity.
        This is separate from who should receive the alert.
        """
        try:
            conf = float(report.get("final_confidence") or report.get("ai_confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
            logger.warning(f"Could not parse confidence for report {report.get('id')}. Defaulting to 0.0. Report data: {report}")

        if conf < self.threshold:
            logger.debug(f"Alert skipped globally for report {report.get('id')} due to low confidence ({conf:.2f} < {self.threshold:.2f}).")
            return False
        logger.debug(f"Report {report.get('id')} passes global confidence threshold ({conf:.2f} >= {self.threshold:.2f}).")
        return True

    def get_alert_channels_for_report(self, report: Dict) -> List[str]:
        """Determine general channels based on report severity."""
        severity = (report.get("severity") or "Low")
        if severity == "Critical":
            return ["email", "sms", "push"]
        if severity == "High":
            return ["email", "push"]
        return ["email"]


    def send_alert(self, report: Dict, override_channels: Optional[List[str]] = None): # THIS IS NOW A METHOD OF AlertSystem
        """
        Sends personalized alerts for a given report to relevant users.
        Records alert events in the alert history (either to DB or a JSON file).
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not self.should_send_report(report):
            entry = {
                "report_id": report.get("id"),
                "user_id": None,
                "channel": "system",
                "status": "skipped_global",
                "detail": "Alert skipped for all users due to low overall report confidence.",
                "timestamp": timestamp
            }
            save_alert_history_entry(entry)
            if _db_functions_are_fallback:
                self.alert_history.append(entry)
            return {}

        normalized_report_location = normalize_location_string_for_alerts(report.get("location"))
        logger.debug(f"Processing alert for report ID {report.get('id')}, normalized location: '{normalized_report_location}'")

        all_users = load_users()
        overall_results = {}
        alert_sent_to_any_user = False

        if not all_users:
            logger.warning("No users registered in the system for personalized alerts.")
            entry = {
                "report_id": report.get("id"),
                "user_id": None,
                "channel": "system",
                "status": "no_recipients",
                "detail": f"No users registered for personalized alerts for report location '{normalized_report_location}'.",
                "timestamp": timestamp
            }
            save_alert_history_entry(entry)
            if _db_functions_are_fallback:
                self.alert_history.append(entry)
            return {}

        for user in all_users:
            user_id = user["id"]
            normalized_user_preferred_location = normalize_location_string_for_alerts(user.get("preferred_location"))
            logger.debug(f"  - Checking user {user_id} ('{user.get('name')}'): Preferred location '{normalized_user_preferred_location}'")

            if normalized_user_preferred_location and normalized_report_location == normalized_user_preferred_location:
                channels_to_use = override_channels if override_channels is not None else self.get_alert_channels_for_report(report)

                for ch in channels_to_use:
                    detail = f"Alert simulated via {ch} for {user['name']} (demo mode)." if self.demo_mode else f"Alert sent via {ch} to {user['name']}."
                    entry = {
                        "report_id": report.get("id"),
                        "user_id": user_id,
                        "channel": ch,
                        "status": "sent",
                        "detail": detail,
                        "timestamp": timestamp
                    }
                    save_alert_history_entry(entry)
                    if _db_functions_are_fallback:
                        self.alert_history.append(entry)
                    overall_results[f"{user_id}_{ch}"] = True
                    alert_sent_to_any_user = True
                    logger.info(f"    -> Alert SENT for report {report.get('id')} to user {user_id} via {ch} for location '{normalized_report_location}'.")
            else:
                entry = {
                    "report_id": report.get("id"),
                    "user_id": user_id,
                    "channel": "system",
                    "status": "skipped_location",
                    "detail": f"Alert skipped for {user['name']} (ID: {user_id}) - report location '{normalized_report_location}' does not match preferred location '{normalized_user_preferred_location or 'N/A'}'.",
                    "timestamp": timestamp
                }
                save_alert_history_entry(entry)
                if _db_functions_are_fallback:
                    self.alert_history.append(entry)
                logger.debug(f"    -> Alert SKIPPED for report {report.get('id')} to user {user_id}: Location mismatch ('{normalized_report_location}' vs '{normalized_user_preferred_location or 'N/A'}').")

        if not alert_sent_to_any_user:
            entry = {
                "report_id": report.get("id"),
                "user_id": None,
                "channel": "system",
                "status": "no_recipients",
                "detail": f"No users found with preferred location matching report location '{normalized_report_location}' for alert.",
                "timestamp": timestamp
            }
            save_alert_history_entry(entry)
            if _db_functions_are_fallback:
                self.alert_history.append(entry)
            logger.info(f"No recipients found for report {report.get('id')} for location '{normalized_report_location}'.")

        return overall_results

# Remove the global _alert_system = None and the top-level send_alert function
# app.py will create the instance and call its method.
# _alert_system: AlertSystem = None # REMOVED from here

# def send_alert(report: Dict, override_channels: Optional[List[str]] = None): # REMOVED from here
#    """Public interface to send an alert using the singleton AlertSystem."""
#    return _alert_system.send_alert(report, override_channels) # REMOVED from here