import streamlit as st
import os
import json
from datetime import datetime, timedelta
import pandas as pd
import math
from typing import List, Dict, Tuple, Optional
import logging
import sys # Import sys to get module path

# Set up logging for app.py
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
logger = logging.getLogger(__name__)

# DEBUG PRINT: Check which alerts.py is being imported
try:
    import alerts
    if 'alerts' in sys.modules:
        print(f"DEBUG: Importing alerts.py from: {sys.modules['alerts'].__file__}")
except ImportError:
    print("DEBUG: alerts.py import failed (before it would have normally).")


# Fixed imports: map utilities from map_dashboard, DB functions from db
from map_dashboard import create_advanced_map, parse_latlon, get_report_statistics, KNOWN_LOCATIONS
from db import load_reports, next_report_id, insert_or_update_user, load_users, get_alerts_with_report_and_user_info, update_report_status_and_confidence, get_report_by_id
# Corrected import: send_alert is now a method of AlertSystem, so we only import AlertSystem and normalize_location_string_for_alerts
from alerts import AlertSystem, normalize_location_string_for_alerts 
import auth
from ai_model import classify_text
from social_ingest import ingest_from_csv, fetch_social_feed_stub
from utils import ensure_reports_file, save_reports, ensure_upload_dir
from streamlit_folium import st_folium
import plotly.express as px

from translations import t, LANGUAGES

# -----------------------
# Config / initial setup
# -----------------------
REPORTS_FILE = "reports.json"
UPLOAD_DIR = "uploads"
CONFIG_FILE = "app_config.json"

st.set_page_config(page_title="INCOIS: Ocean Hazard Hub", layout="wide", page_icon="🌊")
ensure_reports_file(REPORTS_FILE)
ensure_upload_dir(UPLOAD_DIR)

if "language" not in st.session_state:
    st.session_state.language = "en"

try:
    import db
    db.ensure_db()
    logger.info(f"Database ensured at: {os.path.abspath(db.DB_FILE)}")
except Exception as e:
    logger.error(f"Failed to initialize database: {e}. Some features may be limited.")
    st.error(f"Failed to initialize database: {e}. Some features may be limited.")
    pass

# Use the normalization function from alerts.py to ensure consistency
normalize_location_string = normalize_location_string_for_alerts

# -----------------------
# Helpers: time & geo
# -----------------------
def parse_timestamp(ts: str) -> datetime:
    if not ts:
        return datetime(2000, 1, 1)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return datetime(2000, 1, 1)

def haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    x = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))

# -----------------------
# Application config
# -----------------------
if not os.path.exists(CONFIG_FILE):
    default_cfg = {
        "app_title": "INCOIS - Ocean Hazard Hub",
        "demo_mode": True,
        "alert_confidence_threshold": 0.7,
        "weights": {"ai": 0.6, "social": 0.4},
        "social_lookback_days": 3,
        "social_search_radius_km": 50
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(default_cfg, f, indent=2)

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    APP_CFG = json.load(f)

# NEW: Initialize the singleton AlertSystem instance with values from APP_CFG
# This must happen AFTER APP_CFG is loaded.
# THIS IS THE ONLY PLACE _alert_system_instance IS INSTANTIATED
_alert_system_instance = AlertSystem( # Renamed for clarity, it's the actual instance
    demo_mode=APP_CFG.get("demo_mode", True),
    threshold=APP_CFG.get("alert_confidence_threshold", 0.7)
)


# -----------------------
# Session & User Management
# -----------------------
if "user" not in st.session_state:
    st.session_state.user = None
if "role" not in st.session_state:
    st.session_state.role = "anonymous"

def _ensure_user_in_db(user_id, username, name, role, preferred_location=None, password_hash=None):
    normalized_preferred_location = normalize_location_string(preferred_location)
    user_data = {
        "id": user_id,
        "username": username,
        "name": name,
        "role": role,
        "preferred_location": normalized_preferred_location
    }
    if password_hash:
        user_data["password_hash"] = password_hash
    
    existing_user_db = db.get_user_by_username(username)
    if existing_user_db and "password_hash" in existing_user_db:
        user_data["password_hash"] = user_data.get("password_hash", existing_user_db["password_hash"])
    elif "password_hash" not in user_data:
         logger.error(f"Attempted to ensure user '{username}' in DB without password_hash and no existing hash found.")
         return False

    insert_or_update_user(user_data)
    logger.info(f"User '{name}' (ID: {user_id}) DB ensured. Preferred Location: '{normalized_preferred_location}'")
    return True

def login_page():
    current_lang = st.session_state.language

    lang_col1, lang_col2 = st.columns([3, 1])
    with lang_col2:
        selected_lang = st.selectbox(
            label=t("language_selector_label", current_lang),
            options=list(LANGUAGES.keys()),
            format_func=lambda x: LANGUAGES[x],
            index=list(LANGUAGES.keys()).index(st.session_state.language),
            key="login_lang_selector"
        )
        if selected_lang != st.session_state.language:
            st.session_state.language = selected_lang
            st.rerun()
    
    st.sidebar.empty()
    st.markdown(f"<h1 style='text-align:center'>{t('app_title', current_lang)}</h1>", unsafe_allow_html=True)
    st.markdown("---")

    login_tab, register_tab = st.tabs([
        t("login_tab_title", current_lang),
        t("register_tab_title", current_lang)
    ])

    with login_tab:
        st.subheader(t("login_subheader", current_lang))
        with st.form("login_form", clear_on_submit=True):
            username = st.text_input(t("username_label", current_lang), key="login_username")
            password = st.text_input(t("password_label", current_lang), type="password", key="login_password")
            login_button = st.form_submit_button(t("login_button", current_lang))

            if login_button:
                user = auth.authenticate_user(username, password)
                if user:
                    st.session_state.user = user
                    st.session_state.role = user["role"]
                    st.rerun()

    with register_tab:
        st.subheader(t("register_subheader", current_lang))
        with st.form("register_form", clear_on_submit=True):
            new_username = st.text_input(t("username_label", current_lang), key="register_username")
            new_password = st.text_input(t("password_label", current_lang), type="password", key="register_password")
            confirm_password = st.text_input(t("confirm_password_label", current_lang), type="password", key="confirm_password")
            new_name = st.text_input(t("your_name_label", current_lang), key="register_name")
            
            role_options_raw = ["citizen", "official", "analyst"]
            role_labels_translated = [
                t("citizen_role", current_lang),
                t("official_role", current_lang),
                t("analyst_role", current_lang)
            ]
            
            new_role = st.selectbox(
                t("account_type_label", current_lang),
                role_options_raw,
                format_func=lambda x: role_labels_translated[role_options_raw.index(x)],
                index=0,
                key="register_role"
            )
            
            if new_role == "official":
                admin_override_pwd = st.text_input(t("admin_override_pwd_label", current_lang), type="password", key="admin_override_pwd")
                
            register_button = st.form_submit_button(t("register_button", current_lang))

            if register_button:
                if new_password != confirm_password:
                    st.error(t("passwords_do_not_match_error", current_lang))
                elif new_role == "official" and admin_override_pwd != APP_CFG.get("admin_password"):
                    st.error(t("incorrect_admin_pwd_error", current_lang))
                else:
                    success = auth.register_user(new_username, new_password, new_name, new_role, preferred_location="")
                    if success:
                        st.success(f"{t('register_subheader', current_lang)} {t('successful', current_lang)}")
                        pass

# -----------------------
# Main App Logic (displayed only if logged in)
# -----------------------
def main_app():
    current_lang = st.session_state.language
    
    with st.sidebar:
        # Language selector in sidebar
        st.markdown(f"{t('language_selector_label', current_lang)}")
        selected_lang = st.selectbox(
            "",
            options=list(LANGUAGES.keys()),
            format_func=lambda x: LANGUAGES[x],
            index=list(LANGUAGES.keys()).index(st.session_state.language),
            key="sidebar_lang_selector"
        )
        if selected_lang != st.session_state.language:
            st.session_state.language = selected_lang
            st.rerun()
        
        st.markdown("---")
        
        st.header(t("access_header", current_lang))
        st.info(f"{t('signed_in_as', current_lang)} {st.session_state.user['name']} ({st.session_state.role})")
        
        st.markdown("---")
        st.subheader(t("personalized_alerts_subheader", current_lang))
        current_user_id = st.session_state.user["id"]
        current_user_db_info = db.get_user_by_username(st.session_state.user["username"])
        current_preferred_location = current_user_db_info.get("preferred_location", "") if current_user_db_info else ""

        preferred_location_input = st.text_input(
            t("preferred_location_for_alerts_label", current_lang),
            value=current_preferred_location,
            help="e.g., Chennai, Mumbai, or a specific lat,lon"
        )
        if st.button(t("save_preferred_location_button", current_lang)):
            normalized_preferred_location = normalize_location_string(preferred_location_input)
            success = _ensure_user_in_db(
                user_id=st.session_state.user["id"],
                username=st.session_state.user["username"],
                name=st.session_state.user["name"],
                role=st.session_state.user["role"],
                preferred_location=normalized_preferred_location
            )
            if success:
                st.session_state.user['preferred_location'] = normalized_preferred_location
                st.success(t("preferred_location_saved_success", current_lang).format(location=normalized_preferred_location))

        st.markdown("---") 
        if st.button(t("sign_out_button", current_lang)):
            st.session_state.user = None
            st.session_state.role = "anonymous"
            st.rerun()

        st.markdown("---")
        st.header(t("navigation_header", current_lang))
        
        menu_options_raw = ["Dashboard", "Submit Report", "Live Map", "Report Review", "Report Analysis", "Current Alerts", "Settings", "About"]
        menu_labels_translated = [
            t("menu_dashboard", current_lang),
            t("menu_submit_report", current_lang),
            t("menu_live_map", current_lang),
            t("menu_report_review", current_lang),
            t("menu_report_analysis", current_lang),
            t("menu_current_alerts", current_lang),
            t("menu_settings", current_lang),
            t("menu_about", current_lang)
        ]
        
        selected_menu_display = st.radio(t("go_to_radio", current_lang), menu_labels_translated)
        menu = menu_options_raw[menu_labels_translated.index(selected_menu_display)]

    # -----------------------
    # Load reports (and normalize locations)
    # -----------------------
    reports = load_reports()

    def normalize_loaded_reports_locations(reports_list: List[Dict]) -> None:
        for r in reports_list:
            original_location_string = r.get("location", "")
            original_latlon_string = r.get("latlon", "")

            if original_location_string:
                r["location"] = normalize_location_string(original_location_string)

            parsed_coords_from_location = parse_latlon(r["location"])

            if parsed_coords_from_location:
                r["latlon"] = f"{parsed_coords_from_location[0]},{parsed_coords_from_location[1]}"
            else:
                parsed_coords_from_original_latlon = parse_latlon(original_latlon_string)
                if parsed_coords_from_original_latlon:
                    r["latlon"] = f"{parsed_coords_from_original_latlon[0]},{parsed_coords_from_original_latlon[1]}"
                else:
                    r["latlon"] = ""

    normalize_loaded_reports_locations(reports) 

    def ensure_report_confidences(reports_list: List[Dict]) -> None:
        threshold = APP_CFG.get("alert_confidence_threshold", 0.7)
        for r in reports_list:
            if "ai_confidence" not in r:
                r["ai_confidence"] = 0.0
            if "final_confidence" not in r:
                r["final_confidence"] = float(r.get("ai_confidence", 0.0))
            if "ai_is_real" not in r:
                r["ai_is_real"] = bool(r.get("final_confidence", 0.0) >= threshold)
    ensure_report_confidences(reports)


    # -----------------------
    # Social evidence functions
    # -----------------------
    def gather_social_evidence(report: Dict,
                            lookback_days: int = None,
                            radius_km: float = None) -> Tuple[List[Dict], float, Optional[Tuple[float,float]]]:
        lookback_days = lookback_days if lookback_days is not None else APP_CFG.get("social_lookback_days", 3)
        radius_km = radius_km if radius_km is not None else APP_CFG.get("social_search_radius_km", 50)
        now = datetime.now()

        social_posts = []
        if "social_df" in st.session_state and isinstance(st.session_state.social_df, pd.DataFrame):
            df = st.session_state.social_df.copy()
            if "timestamp" in df.columns:
                df["timestamp_dt"] = df["timestamp"].apply(lambda t: parse_timestamp(t) if pd.notna(t) else datetime(2000,1,1))
                cutoff = now - timedelta(days=lookback_days)
                df = df[df["timestamp_dt"] >= cutoff]
            else:
                df["timestamp_dt"] = now
            social_posts = df.to_dict(orient="records")
        else:
            stub = fetch_social_feed_stub()
            social_posts = stub or []

        report_coords = None
        if report.get("latlon"):
            parsed = parse_latlon(report.get("latlon"))
            if parsed:
                report_coords = parsed

        relevant_posts = []
        social_scores = []
        latlon_candidate = None

        for sp in social_posts:
            text = sp.get("text") or sp.get("message") or ""
            if not text:
                continue

            if sp.get("timestamp"):
                ts = parse_timestamp(sp.get("timestamp"))
                if ts < (now - timedelta(days=lookback_days)):
                    continue

            post_coords = None
            if sp.get("latlon"):
                post_coords = parse_latlon(sp.get("latlon"))
            elif sp.get("location"):
                post_coords = parse_latlon(sp.get("location"))

            if report_coords and post_coords:
                try:
                    dist = haversine_km(report_coords, post_coords)
                except Exception:
                    dist = float("inf")
                if dist > radius_km:
                    continue  
            ct = classify_text(text)
            post_label, post_conf = (ct[0], ct[1]) if len(ct) >= 2 else (None, 0.0)
            social_scores.append(float(post_conf or 0.0))
            relevant_posts.append({
                "text": text,
                "timestamp": sp.get("timestamp"),
                "location": sp.get("location"),
                "latlon": sp.get("latlon"),
                "ai_label": post_label,
                "ai_confidence": float(post_conf or 0.0)
            })
            if not latlon_candidate and post_coords:
                latlon_candidate = post_coords

        social_confidence = float(max(0.0, min(1.0, (sum(social_scores) / len(social_scores)) if social_scores else 0.0)))

        return relevant_posts, social_confidence, latlon_candidate

    def combine_confidences(ai_conf: float, social_conf: float, weights: Dict[str,float] = None) -> float:
        """Combine model confidence and social evidence into a final confidence score."""
        if weights is None:
            weights = APP_CFG.get("weights", {"ai": 0.6, "social": 0.4})
        w_ai = float(weights.get("ai", 0.6))
        w_social = float(weights.get("social", 0.4))
        s = w_ai + w_social
        if s <= 0:
            return max(ai_conf, social_conf)
        final = (ai_conf * w_ai + social_conf * w_social) / s
        return float(max(0.0, min(1.0, final)))

    # --- Variables for filters, derived from 'reports' (moved to global scope within main_app) ---
    all_report_locations = sorted(list(set([r.get("location") for r in reports if r.get("location")])))
    hazard_options_for_filters = sorted(list({r.get("hazard_type","Other") for r in reports}))
    # ---------------------------------------------------------------------------------------------

    # -----------------------
    # Pages
    # -----------------------
    if menu == "Dashboard":
        st.subheader(t("overview_subheader", current_lang))
        
        location_options = all_report_locations
        selected_dashboard_location = st.selectbox(t("filter_reports_by_location_label", current_lang), ["All"] + location_options, index=0)

        dashboard_reports_filtered = reports
        if selected_dashboard_location != "All":
            dashboard_reports_filtered = [r for r in reports if r.get("location") == selected_dashboard_location]

        total = len(dashboard_reports_filtered)
        high_conf = len([r for r in dashboard_reports_filtered if r.get("final_confidence", r.get("ai_confidence", 0)) >= APP_CFG.get("alert_confidence_threshold", 0.7)])
        likely_real = len([r for r in dashboard_reports_filtered if r.get("ai_is_real", False)])
        last7 = len([r for r in dashboard_reports_filtered if (datetime.now() - parse_timestamp(r.get("timestamp"))).days < 7])

        c1, c2, c3, c4 = st.columns(4)
        
        c1.metric(t("total_reports_metric", current_lang), total) 
        c2.metric(t("likely_real_reports_metric", current_lang), likely_real)
        c3.metric(t("high_confidence_metric", current_lang), high_conf)
        c4.metric(t("last_7_days_metric", current_lang), last7)

        st.markdown(f"### {t('recent_reports_subheader', current_lang)}")
        if dashboard_reports_filtered: 
            df = pd.DataFrame(sorted(dashboard_reports_filtered, key=lambda r: r.get("timestamp",""), reverse=True)[:20])
            
            if "latlon" in df.columns:
                df["latlon_parsed"] = df["latlon"].apply(lambda v: parse_latlon(v) or "")
            if "ai_is_real" not in df.columns:
                df["ai_is_real"] = df["ai_confidence"].apply(
                    lambda c: c >= APP_CFG.get("alert_confidence_threshold", 0.7)
                )
            display_cols = ["id","timestamp","hazard_type","location","severity","ai_label","ai_confidence","final_confidence","ai_is_real"]
            display_cols = [c for c in display_cols if c in df.columns]
            st.dataframe(df[display_cols], width="stretch")
        else:
            st.info(t("no_reports_matching_filter_criteria", current_lang))

    elif menu == "Submit Report":
        st.header(t("menu_submit_report", current_lang))
        if st.session_state.role == "anonymous":
            st.warning(t("please_sign_in", current_lang))
        else:
            with st.form("report_form", clear_on_submit=True):
                hazard_options_raw = ["Flood", "Cyclone", "Oil Spill", "Tsunami", "Storm Surge", "Coastal Erosion", "Other"]
                hazard_labels_translated = [
                    t("hazard_type_flood", current_lang),
                    t("hazard_type_cyclone", current_lang),
                    t("hazard_type_oil_spill", current_lang),
                    t("hazard_type_tsunami", current_lang),
                    t("hazard_type_storm_surge", current_lang),
                    t("hazard_type_coastal_erosion", current_lang),
                    t("hazard_type_other", current_lang)
                ]

                selected_hazard_display = st.selectbox(t("hazard_type_label", current_lang), hazard_labels_translated)
                hazard_type = hazard_options_raw[hazard_labels_translated.index(selected_hazard_display)]
                
                location_raw_input = st.text_input(t("location_input_label", current_lang), placeholder="e.g., Chennai Marina or 13.0827,80.2707")
                description = st.text_area(t("description_textarea_label", current_lang), height=140)
                
                severity_options_raw = ["Low","Medium","High","Critical"]
                severity_labels_translated = [
                    t("severity_low", current_lang),
                    t("severity_medium", current_lang),
                    t("severity_high", current_lang),
                    t("severity_critical", current_lang)
                ]

                selected_severity_display = st.selectbox(t("severity_label", current_lang), severity_labels_translated)
                severity = severity_options_raw[severity_labels_translated.index(selected_severity_display)]
                
                media = st.file_uploader(t("media_uploader_label", current_lang), type=["png","jpg","jpeg","mp4","mov"], accept_multiple_files=False)
                submit = st.form_submit_button(t("submit_report_button", current_lang))

                if submit:
                    if not description:
                        st.error(t("please_write_description_error", current_lang))
                    else:
                        location_str = normalize_location_string(location_raw_input)
                        logger.info(f"UI Submit Report: Raw location '{location_raw_input}', Normalized: '{location_str}'")

                        ct = classify_text(description)
                        label, confidence = ct[:2] if len(ct) >= 2 else (None, 0.0)

                        parsed_latlon = parse_latlon(location_str) 
                        latlon_coords = f"{parsed_latlon[0]},{parsed_latlon[1]}" if parsed_latlon else ""

                        reporter_id = st.session_state.user.get("id") if st.session_state.user else "anonymous"
                        report = {
                            "id": next_report_id(),
                            "hazard_type": hazard_type,
                            "description": description,
                            "location": location_str or "Unknown", 
                            "latlon": latlon_coords,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "ai_label": label,
                            "ai_confidence": float(confidence or 0.0),
                            "final_confidence": float(confidence or 0.0),
                            "ai_is_real": False,
                            "severity": severity,
                            "reporter_id": reporter_id,
                            "status": "Submitted"
                        }
                        logger.debug(f"UI Submit Report: Report object before save: {report}")

                        if media:
                            save_path = os.path.join(UPLOAD_DIR, f"report_{report['id']}_{media.name}")
                            with open(save_path, "wb") as f:
                                f.write(media.getbuffer())
                            report["media_path"] = save_path

                        social_posts, social_confidence, social_latlon = gather_social_evidence(
                            report,
                            lookback_days=APP_CFG.get("social_lookback_days", 3),
                            radius_km=APP_CFG.get("social_search_radius_km", 50)
                        )

                        if not parsed_latlon and social_latlon:
                            report["latlon"] = f"{social_latlon[0]},{social_latlon[1]}"

                        final_conf = combine_confidences(report.get("ai_confidence", 0.0), social_confidence)
                        report["final_confidence"] = final_conf
                        threshold = APP_CFG.get("alert_confidence_threshold", 0.7)
                        report["ai_is_real"] = bool(final_conf >= threshold)
                        
                        if not report.get("ai_label"):
                            report["ai_label"] = "Likely Real (AI)" if report["ai_is_real"] else "Likely False (AI)"
                        elif report["ai_is_real"] and "False" in report["ai_label"]:
                            report["ai_label"] = report["ai_label"].replace("False", "Real") + " (AI)"
                        elif not report["ai_is_real"] and "Real" in report["ai_label"]:
                            report["ai_label"] = report["ai_label"].replace("Real", "False") + " (AI)"


                        report["social_evidence"] = {
                            "num_posts": len(social_posts),
                            "social_confidence": social_confidence,
                            "sample_posts": social_posts[:5]
                        }

                        reports.append(report)
                        save_reports(reports) 
                        db.insert_report(report) 

                        st.success(t("report_submitted_success", current_lang).format(report_id=report['id']))
                        st.info(f"AI: {report['ai_label']}, Model Conf: {report['ai_confidence']:.2f}, Social Evidence: {social_confidence:.2f}, Final Conf: {final_conf:.2f}, Likely Real: {report['ai_is_real']}")

                        if report["social_evidence"]["num_posts"] > 0:
                            st.markdown(f"#### {t('social_posts_evidence_subheader', current_lang)}")
                            for p in report["social_evidence"]["sample_posts"]:
                                st.write(f"- {p.get('timestamp','')} — {p.get('text','')[:200]} (conf {p.get('ai_confidence'):.2f})")

                        logger.info(f"UI Submit Report: Calling send_alert for report ID {report['id']} with location '{report['location']}'.")
                        _alert_system_instance.send_alert(report) # Corrected call to instance method

    elif menu == "Live Map":
        st.header(t("menu_live_map", current_lang))
        st.markdown(t("map_description", current_lang))
        
        map_filter_col1, map_filter_col2, map_filter_col3 = st.columns(3) 
        with map_filter_col1:
            selected_hazard_types = st.multiselect(t("filter_by_hazard_type_label", current_lang), options=["All"] + hazard_options_for_filters, default=["All"])
        with map_filter_col2:
            selected_confidence_level = st.select_slider(t("minimum_ai_confidence_label", current_lang),
                options=["Low", "Medium", "High", "Very High"], value="Low") # These options could also be translated
            min_conf_map = {"Low":0.0,"Medium":0.4,"High":0.6,"Very High":0.8}[selected_confidence_level]
        with map_filter_col3: 
            map_location_options = all_report_locations
            selected_map_location = st.selectbox(t("filter_map_by_location_label", current_lang), ["All"] + map_location_options, index=0)
            logger.debug(f"UI Live Map: Selected location filter: '{selected_map_location}'")


        filtered_reports = []
        for r in reports:
            if "All" not in selected_hazard_types and r.get("hazard_type") not in selected_hazard_types:
                continue
            if r.get("final_confidence", r.get("ai_confidence", 0)) < min_conf_map:
                continue
            if selected_map_location != "All" and r.get("location") != selected_map_location: 
                continue
            filtered_reports.append(r)

        st.info(t("reports_displayed_info", current_lang).format(num_filtered=len(filtered_reports), num_total=len(reports)))

        include_heatmap = st.checkbox(t("show_heatmap_checkbox", current_lang), value=True)
        cluster = st.checkbox(t("cluster_markers_checkbox", current_lang), value=True)
        show_only_real = st.checkbox(t("show_only_likely_real_checkbox", current_lang), value=False)
        
        map_reports = [r for r in filtered_reports if r.get("ai_is_real", False)] if show_only_real else filtered_reports

        map_obj = create_advanced_map(map_reports, include_heatmap=include_heatmap, cluster_markers=cluster, include_reference_points=True)
        if map_obj:
            st_data = st_folium(map_obj, width=1100, height=600)
        else:
            st.warning(t("no_valid_location_data_for_mapping", current_lang))


    elif menu == "Report Review":
        st.header(t("menu_report_review", current_lang))
        st.markdown(t("report_review_description", current_lang))
        
        if st.session_state.role != "official":
            st.info(t("official_only_info", current_lang))
            
        review_status_options_raw = ["All", "Submitted", "Verified Real", "False Alarm"]
        review_status_labels_translated = [
            t("status_all", current_lang),
            t("status_submitted", current_lang),
            t("status_verified_real", current_lang),
            t("status_false_alarm", current_lang)
        ]

        selected_review_status_display = st.selectbox(t("filter_by_status_label", current_lang), review_status_labels_translated, index=0)
        selected_review_status = review_status_options_raw[review_status_labels_translated.index(selected_review_status_display)]

        review_hazard_options = hazard_options_for_filters
        selected_review_hazard_types = st.multiselect(t("filter_by_hazard_type_label", current_lang), options=["All"] + review_hazard_options, default=["All"])

        review_reports = reports
        if selected_review_status != "All":
            review_reports = [r for r in review_reports if r.get("status") == selected_review_status]
        if "All" not in selected_review_hazard_types:
            review_reports = [r for r in review_reports if r.get("hazard_type") in selected_review_hazard_types]
        
        st.info(t("displaying_reports_for_review_info", current_lang).format(num_reports=len(review_reports)))

        for r in sorted(review_reports, key=lambda x: parse_timestamp(x.get("timestamp")), reverse=True):
            col_id, col_info, col_action = st.columns([1, 4, 2])
            with col_id:
                st.write(f"{t('id_label', current_lang)}:** {r['id']}")
                st.write(f"{t('status_label_short', current_lang)}:** {r.get('status', 'N/A')}")
            with col_info:
                st.write(f"{t('hazard_label_short', current_lang)}:** {r.get('hazard_type', 'N/A')}")
                st.write(f"{t('location_label_short', current_lang)}:** {r.get('location', 'N/A')} ({r.get('latlon', 'N/A')})")
                st.write(f"{t('description_label_short', current_lang)}:** {r.get('description', '')[:100]}...")
                st.write(f"{t('ai_conf_label_short', current_lang)}:** {r.get('ai_confidence', 0.0):.2f}, *{t('final_conf_label_short', current_lang)}:* {r.get('final_confidence', 0.0):.2f}, *{t('ai_is_real_label_short', current_lang)}:* {r.get('ai_is_real', False)}")
            with col_action:
                if st.button(t("mark_as_verified_real_button", current_lang).format(report_id=r['id']), key=f"verify_{r['id']}"):
                    update_report_status_and_confidence(r['id'], "Verified Real", True, 1.0)
                    st.success(t("report_marked_verified_success", current_lang).format(report_id=r['id']))
                    st.rerun()
                if st.button(t("mark_as_false_alarm_button", current_lang).format(report_id=r['id']), key=f"false_{r['id']}"):
                    update_report_status_and_confidence(r['id'], "False Alarm", False, 0.0)
                    st.warning(t("report_marked_false_alarm_warning", current_lang).format(report_id=r['id']))
                    st.rerun()
            st.markdown("---")


    elif menu == "Report Analysis":
        st.header(t("report_analysis_header", current_lang))
        st.markdown(t("analysis_description", current_lang))

        if reports:
            df = pd.DataFrame(reports)
            df["timestamp_dt"] = df["timestamp"].apply(parse_timestamp)
            df["date"] = df["timestamp_dt"].dt.date

            if "final_confidence" not in df.columns:
                df["final_confidence"] = df["ai_confidence"].fillna(0.0)
            if "ai_is_real" not in df.columns:
                df["ai_is_real"] = df["final_confidence"].apply(lambda c: c >= APP_CFG.get("alert_confidence_threshold", 0.7))

            time_range = st.slider(t("time_range_slider", current_lang), min_value=0, max_value=365, value=30)
            end_date, start_date = datetime.now(), datetime.now() - timedelta(days=time_range)
            df_filtered_analysis = df[(df["timestamp_dt"] >= start_date) & (df["timestamp_dt"] <= end_date)]
            st.subheader(t("analysis_for_last_x_days_subheader", current_lang).format(time_range=time_range, num_reports=len(df_filtered_analysis)))

            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"### {t('hazard_type_distribution_subheader', current_lang)}")
                if not df_filtered_analysis.empty:
                    fig_hazard = px.pie(df_filtered_analysis, names="hazard_type", title=t("reported_hazard_types_chart_title", current_lang))
                    st.plotly_chart(fig_hazard, width="stretch")
                else:
                    st.info(t("no_reports_in_time_range_info", current_lang))
            with col2:
                st.markdown(f"### {t('severity_distribution_subheader', current_lang)}")
                if not df_filtered_analysis.empty:
                    severity_order = ["Low", "Medium", "High", "Critical"]
                    df_filtered_analysis["severity"] = pd.Categorical(df_filtered_analysis["severity"], categories=severity_order, ordered=True)
                    fig_severity = px.bar(df_filtered_analysis.groupby("severity", observed=False).size().reset_index(name='count'), 
                                        x="severity", y="count", title=t("reported_severity_levels_chart_title", current_lang), 
                                        category_orders={"severity": severity_order})
                    st.plotly_chart(fig_severity, width="stretch")
                else:
                    st.info(t("no_reports_in_time_range_info", current_lang))

        st.markdown("---")
        st.subheader(t("social_media_analytics_subheader", current_lang))
        st.info(t("social_media_analytics_info", current_lang))

        if st.button(t("fetch_sample_social_feed_button", current_lang)):
            social_posts_stub = fetch_social_feed_stub()
            if social_posts_stub:
                st.session_state.social_df = pd.DataFrame(social_posts_stub)
                st.success(t("fetched_social_posts_success", current_lang).format(num_posts=len(social_posts_stub)))
            else:
                st.warning(t("could_not_fetch_social_posts_warning", current_lang))

        csv_file = st.file_uploader(t("upload_social_csv_label", current_lang), type=["csv"])
        if csv_file:
            try:
                st.session_state.social_df = ingest_from_csv(csv_file)
                st.success(t("csv_uploaded_success", current_lang))
            except ValueError as e:
                st.error(t("error_processing_csv", current_lang).format(error=e))

        if "social_df" in st.session_state and not st.session_state.social_df.empty:
            st.markdown(f"#### {t('preview_social_media_data_subheader', current_lang)}")
            st.dataframe(st.session_state.social_df.head(), width="stretch")

            st.markdown(f"#### {t('keyword_counts_subheader', current_lang)}")
            if "keywords" in st.session_state.social_df.columns:
                all_keywords = [k for sublist in st.session_state.social_df["keywords"] for k in sublist]
                if all_keywords:
                    kw_counts = pd.Series(all_keywords).value_counts().reset_index()
                    kw_counts.columns = ["keyword", "count"]
                    fig_kw = px.bar(kw_counts, x="keyword", y="count", title=t("keyword_counts_subheader", current_lang))
                    st.plotly_chart(fig_kw, width="stretch")
                else:
                    st.info(t("no_keywords_extracted_info", current_lang))
            else:
                st.info(t("no_keyword_extraction_available_info", current_lang))

    elif menu == "Current Alerts":
        st.header(t("current_active_alerts_header", current_lang))
        st.markdown(t("alerts_description", current_lang))

        try:
            alerts_data = get_alerts_with_report_and_user_info(location=None)
            if alerts_data:
                alerts_df = pd.DataFrame(alerts_data)
                
                status_options = ["All"] + sorted(list(alerts_df["status"].unique())) if "status" in alerts_df.columns else ["All"]
                
                translated_status_options = [t(f"status_{s.lower().replace(' ', '_')}", current_lang) if s != "All" else t("status_all", current_lang) for s in status_options]

                selected_status_display = st.selectbox(t("filter_by_alert_status_label", current_lang), translated_status_options)
                
                selected_status = status_options[translated_status_options.index(selected_status_display)]

                if selected_status != "All":
                    alerts_df = alerts_df[alerts_df["status"] == selected_status]

                display_cols = ["alert_id", "timestamp", "report_hazard_type", "report_location", "status", "detail", "reporter_name", "alert_recipient_name"]
                available_cols = [col for col in display_cols if col in alerts_df.columns]
                
                if not alerts_df.empty and available_cols:
                    st.dataframe(alerts_df[available_cols].sort_values("timestamp", ascending=False), 
                               use_container_width=True)
                else:
                    st.info(t("no_alerts_match_criteria_info", current_lang))
            else:
                st.info(t("no_active_alerts_system_info", current_lang))
        except Exception as e:
            st.error(t("error_loading_alerts", current_lang).format(error=e))


    elif menu == "Settings":
        st.header(t("settings_header", current_lang))
        if st.session_state.role != "official":
            st.warning(t("settings_access_warning", current_lang))
        else:
            st.subheader(t("app_config_subheader", current_lang))
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                current_app_cfg = json.load(f)

            new_app_title = st.text_input(t("app_title_settings_label", current_lang), value=current_app_cfg.get("app_title", "INCOIS - Ocean Hazard Hub"))
            demo_mode = st.checkbox(t("demo_mode_checkbox", current_lang), value=current_app_cfg.get("demo_mode", True))
            alert_threshold = st.slider(t("alert_confidence_threshold_slider", current_lang), 0.0, 1.0, value=current_app_cfg.get("alert_confidence_threshold", 0.7), help=t("alert_threshold_help", current_lang))
            new_admin_pwd = st.text_input(t("admin_password_input", current_lang), value=APP_CFG.get("admin_password", "sih2025"), type="password")


            w_ai = st.slider(t("ai_weight_slider", current_lang), 0.0, 1.0, APP_CFG.get("weights", {}).get("ai", 0.6))
            w_social = 1.0 - w_ai
            st.info(t("social_evidence_weight_info", current_lang).format(weight=w_social))

            new_social_lookback_days = st.number_input(t("social_lookback_days_label", current_lang), min_value=1, max_value=30, value=APP_CFG.get("social_lookback_days", 3))
            new_social_search_radius_km = st.number_input(t("social_search_radius_label", current_lang), min_value=1, max_value=200, value=APP_CFG.get("social_search_radius_km", 50))


            if st.button(t("save_settings_button", current_lang)):
                current_app_cfg["app_title"] = new_app_title
                current_app_cfg["demo_mode"] = demo_mode
                current_app_cfg["alert_confidence_threshold"] = alert_threshold
                current_app_cfg["admin_password"] = new_admin_pwd
                current_app_cfg["weights"] = {"ai": w_ai, "social": w_social}
                current_app_cfg["social_lookback_days"] = int(new_social_lookback_days)
                current_app_cfg["social_search_radius_km"] = int(new_social_search_radius_km)

                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(current_app_cfg, f, indent=2)
                st.success(t("settings_saved_success", current_lang))
                APP_CFG.update(current_app_cfg)
                # IMPORTANT: Update the live _alert_system_instance as well
                _alert_system_instance.demo_mode = current_app_cfg.get("demo_mode", True)
                _alert_system_instance.threshold = current_app_cfg.get("alert_confidence_threshold", 0.7)
                logger.info("UI Settings: Configuration saved and AlertSystem updated.")

            st.markdown("---")
            st.subheader(t("alert_history_subheader", current_lang))
            full_alert_history = get_alerts_with_report_and_user_info(location=None) 
            if full_alert_history:
                ah_df = pd.DataFrame(full_alert_history)
                ah_df['alert_recipient_name'] = ah_df['alert_recipient_name'].fillna('N/A')
                ah_df['reporter_name'] = ah_df['reporter_name'].fillna('Anonymous')
                st.dataframe(ah_df.sort_values("timestamp", ascending=False).head(50), use_container_width=True)
                if st.button(t("clear_alert_history_button", current_lang)):
                    st.warning(t("clear_alert_history_warning", current_lang))
            else:
                st.info(t("no_alerts_sent_info", current_lang))


            st.markdown("---")
            st.subheader(t("data_management_subheader", current_lang))
            if st.button(t("clear_demo_reports_button", current_lang)):
                if os.path.exists(REPORTS_FILE):
                    os.remove(REPORTS_FILE)
                st.warning(t("clear_demo_reports_warning", current_lang))
                ensure_reports_file(REPORTS_FILE)
                reports.clear()
                st.success(t("json_reports_cleared_success", current_lang))
                logger.info("UI Data Management: JSON reports file cleared.")

            if st.button(t("seed_demo_data_button", current_lang)):
                base = next_report_id()
                seed_examples = [
                    {"id": base, "hazard_type":"Flood", "description":"Water level rising near the pier", "location":"Chennai Marina", "latlon":"13.0827,80.2707", "timestamp":datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "ai_label":"Flood","ai_confidence":0.88,"final_confidence":0.88,"ai_is_real":True,"severity":"High","reporter_id":"user_seed","status":"Submitted"},
                    {"id": base+1, "hazard_type":"Oil Spill", "description":"Black oily patch along coast near Kochi port", "location":"Kochi Port", "latlon":"9.9312,76.2673", "timestamp":(datetime.now()-timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"), "ai_label":"Oil Spill","ai_confidence":0.91,"final_confidence":0.91,"ai_is_real":True,"severity":"Critical","reporter_id":"user_seed","status":"Submitted"},
                    {"id": base+2, "hazard_type":"Other", "description":"Looks like algae bloom but unsure", "location":"Visakhapatnam", "latlon":"17.6868,83.2185", "timestamp":(datetime.now()-timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"), "ai_label":"Other","ai_confidence":0.45,"final_confidence":0.45,"ai_is_real":False,"severity":"Low","reporter_id":"user_seed","status":"Submitted"}
                ]
                
                for example in seed_examples:
                    example["location"] = normalize_location_string(example["location"])
                    reports.append(example) 
                    db.insert_report(example) 

                save_reports(reports) 
                st.success(t("seeded_demo_reports_success", current_lang))
                logger.info("UI Data Management: Seeded demo reports.")

    elif menu == "About":
        st.header(t("menu_about", current_lang))
        
        st.markdown(t("problem_statement", current_lang))
        st.markdown(t("prototype_does", current_lang))
        for item in t("features_list", current_lang):
            st.markdown(item)
        
        st.markdown(f"### {t('demo_highlights', current_lang)}")
        
        st.markdown(f"### {t('future_enhancements', current_lang)}")

        st.markdown(t("team_vision_header", current_lang))
        for item in t("team_vision_points", current_lang):
            st.markdown(item)
        
        st.markdown(t("demo_tips_header", current_lang))
        for item in t("demo_tips_points", current_lang):
            st.markdown(item)

    # Footer
    st.markdown("---")
    st.caption(t("footer_message", current_lang))

# Main app entry point: show login if not authenticated, else show main app
if __name__ == "__main__":
    try:
        if st.session_state.user is None:
            login_page()
        else:
            main_app()
    except Exception as e:
        st.error("An unexpected error occurred during application execution. Check the terminal for more details if showErrorDetails is enabled.")
        st.exception(e)
        logger.exception("Unhandled exception during Streamlit app execution.")