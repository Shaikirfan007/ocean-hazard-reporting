import folium
from folium import plugins
import json
import os
import logging
from typing import List, Dict, Tuple, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

DEFAULT_CENTER = (20.0, 78.0) # Center of India
DEFAULT_ZOOM = 5

COLOR_MAP = {
    "Flood": "#4A90E2",         # Blue
    "Cyclone": "#E74C3C",       # Red
    "Oil Spill": "#2C3E50",     # Dark Gray
    "Tsunami": "#9B59B6",       # Purple
    "Storm Surge": "#F39C12",   # Orange
    "Coastal Erosion": "#8D6E63", # Brown
    "Other": "#27AE60",         # Green
    "Unknown": "#95A5A6"        # Light Gray
}

SEVERITY_STYLES = {
    "Critical": {"radius": 15, "weight": 4, "opacity": 0.95},
    "High": {"radius": 12, "weight": 3, "opacity": 0.85},
    "Medium": {"radius": 9, "weight": 2, "opacity": 0.7},
    "Low": {"radius": 6, "weight": 1, "opacity": 0.55}
}

# Expanded KNOWN_LOCATIONS for better coverage and precision in India
KNOWN_LOCATIONS = {
    # Major Indian Cities
    "Mumbai": (19.0760, 72.8777),
    "Kolkata": (22.5726, 88.3639),
    "Delhi": (28.7041, 77.2090),
    "Bengaluru": (12.9716, 77.5946),
    "Hyderabad": (17.3850, 78.4867),
    "Ahmedabad": (23.0225, 72.5714),
    "Pune": (18.5204, 73.8567),
    "Surat": (21.1702, 72.8311),
    "Jaipur": (26.9124, 75.7873),
    "Lucknow": (26.8467, 80.9462),

    # Tamil Nadu Specific Cities
    "Chennai": (13.0827, 80.2707), # State Capital, prominent coastal city
    "Chennai Marina": (13.0674, 80.2818), # More specific to Marina Beach
    "Coimbatore": (11.0168, 76.9558),
    "Madurai": (9.9252, 78.1198),
    "Tiruchirappalli": (10.7905, 78.7047),
    "Salem": (11.6643, 78.1460),
    "Vellore": (12.9165, 79.1325),
    "Kanyakumari": (8.0883, 77.5385), # Southern tip
    "Thanjavur": (10.7870, 79.1378),
    "Tirunelveli": (8.7139, 77.7567),
    "Cuddalore": (11.7456, 79.7719),
    "Rameswaram": (9.2881, 79.3174),
    "Nagapattinam": (10.7659, 79.8428),
    "Tuticorin": (8.7642, 78.1348),
    "Chidambaram": (11.3915, 79.6953),
    "Kanchipuram": (12.8340, 79.7020),
    "Erode": (11.3410, 77.7282),

    # Kerala Specific Cities
    "Kochi": (9.9312, 76.2673),
    "Kochi Port": (9.9669, 76.2758), # More specific to Kochi Port
    "Thiruvananthapuram": (8.5241, 76.9366), # State Capital
    "Kozhikode": (11.2588, 75.7804),
    "Thrissur": (10.5276, 76.2144),
    "Alappuzha": (9.4981, 76.3388),
    "Kollam": (8.8932, 76.6141),
    "Palakkad": (10.7867, 76.6548),
    "Malappuram": (11.0717, 76.0700),
    "Kannur": (11.8745, 75.3704),
    "Kottayam": (9.5916, 76.5222),
    "Munnar": (10.0889, 77.0594),
    "Varkala": (8.7360, 76.7118),
    "Kasaragod": (12.5034, 74.9818),

    # Other Coastal / Important Cities in India
    "Visakhapatnam": (17.6868, 83.2185), # Andhra Pradesh
    "Vijayawada": (16.5062, 80.6480), # Andhra Pradesh
    "Guntur": (16.3000, 80.4500), # Andhra Pradesh
    "Nellore": (14.4449, 79.9864), # Andhra Pradesh
    "Goa": (15.2993, 74.1240), # Represents the state/union territory generally
    "Panaji": (15.4989, 73.8278), # Goa's capital
    "Mangalore": (12.9141, 74.8560), # Karnataka
    "Udupi": (13.3409, 74.7421), # Karnataka
    "Puducherry": (11.9416, 79.8083), # Union Territory
    "Bhubaneswar": (20.2961, 85.8245), # Odisha (near coast)
    "Cuttack": (20.4625, 85.8828), # Odisha
    "Puri": (19.8135, 85.8312), # Odisha
    "Port Blair": (11.6233, 92.7265), # Andaman and Nicobar Islands
    "Daman": (20.3974, 72.8407), # Daman and Diu
    "Diu": (20.7197, 70.9858), # Daman and Diu
    "Gandhinagar": (23.2156, 72.6369), # Gujarat
    "Ahmednagar": (19.0882, 74.7490), # Maharashtra

    # Punjab Cities (as previously included, kept for northern coverage)
    "Ludhiana": (30.9009, 75.8573),
    "Amritsar": (31.6340, 74.8723),
    "Jalandhar": (31.3260, 75.5762),
    "Patiala": (30.3398, 76.3869),
    "Bathinda": (30.2032, 74.9455),
    "Chandigarh": (30.7333, 76.7794),
    
    # Broad State-level Fallback (These should only match if no city within the state is found)
    "Tamil Nadu": (11.0, 79.0), # Central coordinates for Tamil Nadu
    "Kerala": (10.8505, 76.2711), # Central coordinates for Kerala
    "Karnataka": (14.0, 76.0),
    "Andhra Pradesh": (15.9129, 80.1539),
    "Odisha": (20.9517, 85.0985),
    "Gujarat": (22.2587, 71.1924),
    "Maharashtra": (19.7515, 75.7139),
    "West Bengal": (22.9868, 87.8550),
    "Punjab": (31.1471, 75.3412),
    "Goa State": (15.2993, 74.1240) 
}

def parse_latlon(location_str: str) -> Optional[Tuple[float,float]]:
    """
    Parses a location string into (latitude, longitude) tuple.
    Prioritizes explicit 'lat,lon' format, then robustly tries known city/state coordinates.
    """
    if not location_str or not isinstance(location_str, str):
        return None
    s = location_str.strip()
    low_s = s.lower()
    
    # 1. Try to parse comma-separated coordinates (e.g., "13.08, 80.27")
    if "," in s:
        parts = [p.strip() for p in s.split(",")]
        if len(parts) >= 2:
            try:
                lat = float(parts[0])
                lon = float(parts[1])
                # Basic validation for realistic coordinates
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    logger.debug(f"Parsed explicit coordinates for '{location_str}': ({lat}, {lon})")
                    return (lat, lon)
            except ValueError:
                pass # Not valid floats, try next method
    
    # 2. Try to match against known city/state names
    # First, check for an EXACT match of the entire input string (case-insensitive)
    for city_name, coords in KNOWN_LOCATIONS.items():
        if low_s == city_name.lower():
            logger.debug(f"Exact match found for '{location_str}': {city_name} -> {coords}")
            return coords

    # If no exact match, then try SUBSTRING matching, prioritizing LONGER matches.
    # This is crucial: e.g., "Chennai, Tamil Nadu" should match "Chennai" before "Tamil Nadu".
    # Sort KNOWN_LOCATIONS by key length (descending) for this purpose.
    sorted_known_locations_by_length = sorted(KNOWN_LOCATIONS.items(), key=lambda item: len(item[0]), reverse=True)
    
    for city_name, coords in sorted_known_locations_by_length:
        if city_name.lower() in low_s:
            logger.debug(f"Substring match found for '{location_str}': {city_name} -> {coords}")
            return coords
            
    # 3. Handle common variations and misspellings as a last resort
    variations = {
        "vizag": "Visakhapatnam", "bombay": "Mumbai", "madras": "Chennai",
        "calcutta": "Kolkata", "cochin": "Kochi", "pondy": "Puducherry",
        "hyd": "Hyderabad", "blr": "Bengaluru", "trivandrum": "Thiruvananthapuram"
    }
    for variation, standard in variations.items():
        if variation in low_s:
            if standard in KNOWN_LOCATIONS:
                logger.debug(f"Variation match found for '{location_str}': {variation} -> {standard} -> {KNOWN_LOCATIONS[standard]}")
                return KNOWN_LOCATIONS[standard]
    
    logger.debug(f"No known location match found for '{location_str}'")
    return None

def calculate_map_center(reports):
    """Calculate optimal map center based on report locations."""
    coords = []
    for r in reports:
        # Try latlon field first, then location
        coord_str = r.get("latlon", "") or r.get("location", "")
        p = parse_latlon(coord_str)
        if p:
            coords.append(p)
    
    if not coords:
        return DEFAULT_CENTER
    
    lats, lons = zip(*coords)
    return (sum(lats)/len(lats), sum(lons)/len(lons))

def determine_zoom_level(reports):
    """Determine appropriate zoom level based on report spread."""
    coords = []
    for r in reports:
        coord_str = r.get("latlon", "") or r.get("location", "")
        p = parse_latlon(coord_str)
        if p:
            coords.append(p)
    
    if len(coords) < 2:
        return DEFAULT_ZOOM + 2 # Zoom in a bit more for few reports
    
    lats, lons = zip(*coords)
    lat_range = max(lats) - min(lats)  
    lon_range = max(lons) - min(lons)
    max_range = max(lat_range, lon_range)

    # Better zoom calculation for Indian geography
    if max_range > 30: return 4
    if max_range > 15: return 5  
    if max_range > 8: return 6
    if max_range > 4: return 7
    if max_range > 2: return 8
    if max_range > 1: return 9
    if max_range > 0.5: return 10
    return 11 # Closest zoom for very localized events

def create_advanced_map(reports: List[Dict],
                        start_center: Optional[Tuple[float, float]]=None,
                        zoom_start: Optional[int]=None,
                        include_heatmap: bool=True,
                        include_reference_points: bool=True,
                        cluster_markers: bool=True) -> folium.Map:
    """
    Create enhanced map with accurate location plotting and distinct symbols for report status.
    """
    center = start_center or calculate_map_center(reports)
    zoom = zoom_start or determine_zoom_level(reports)
    
    m = folium.Map(location=center, zoom_start=zoom, tiles=None)
    
    # Add tile layers
    folium.TileLayer('openstreetmap', name='Street Map', control=True).add_to(m)
    folium.TileLayer('CartoDB positron', name='Light Map', control=True).add_to(m)
    folium.TileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        name='Satellite', attr='Esri', control=True
    ).add_to(m)

    # Add reference points
    if include_reference_points:
        ref_group = folium.FeatureGroup(name="Reference Cities").add_to(m)
        # Display only a subset of KNOWN_LOCATIONS for clarity as reference points
        for city, coords in KNOWN_LOCATIONS.items():
            if city in ["Mumbai", "Chennai", "Kolkata", "Kochi", "Thiruvananthapuram", "Visakhapatnam", "Goa", "Delhi", "Bengaluru", "Hyderabad"]:
                 folium.CircleMarker(
                    location=coords, 
                    radius=3, 
                    color="#34495E", 
                    fill=True, 
                    fillColor="#34495E",
                    popup=f"Reference: {city}",
                    tooltip=f"Reference: {city}"
                ).add_to(ref_group)

    # Setup marker container
    if cluster_markers and reports:
        target_layer = plugins.MarkerCluster(name="Hazard Reports").add_to(m)
    else:
        target_layer = folium.FeatureGroup(name="Individual Reports").add_to(m)

    heat_data = []
    valid_reports = 0
    
    for r in reports:
        # Get coordinates with priority: latlon field > parsed location
        loc = None
        if r.get("latlon"):
            loc = parse_latlon(r.get("latlon"))
        if not loc and r.get("location"): # If latlon didn't parse or was empty, try location string
            loc = parse_latlon(r.get("location"))
        
        if not loc:
            logger.warning(f"Could not parse location for report {r.get('id')}: '{r.get('location')}' / '{r.get('latlon')}'")
            continue
            
        lat, lon = loc
        valid_reports += 1
        
        hazard = r.get("hazard_type", "Unknown")
        severity = r.get("severity", "Medium")
        ai_conf = float(r.get("final_confidence", r.get("ai_confidence", 0.0) or 0.0))
        is_real = bool(r.get("ai_is_real", False)) # Use the ai_is_real flag directly
        report_status = r.get("status", "Submitted")

        color = COLOR_MAP.get(hazard, COLOR_MAP["Unknown"])
        style = SEVERITY_STYLES.get(severity, SEVERITY_STYLES["Medium"])
        
        # Determine marker icon and color based on ai_is_real and status
        icon_color = "blue"
        icon_name = "info"
        marker_tooltip_prefix = ""

        if is_real: # Report is considered 'real' by AI or official
            if report_status == "Verified Real":
                icon_color = "darkgreen"
                icon_name = "check-circle"
                marker_tooltip_prefix = "✅ VERIFIED "
            elif severity == "Critical":
                icon_color = "darkred"
                icon_name = "exclamation-triangle"
                marker_tooltip_prefix = "⚠ LIKELY REAL "
            else:
                icon_color = "green"
                icon_name = "check"
                marker_tooltip_prefix = "✔ LIKELY REAL "
        else: # Report is considered 'not real'
            if report_status == "False Alarm":
                icon_color = "gray"
                icon_name = "ban" # or times-circle
                marker_tooltip_prefix = "❌ FALSE ALARM "
            else: # Likely False by AI or still under review but low confidence
                icon_color = "lightgray"
                icon_name = "times" # or question-circle
                marker_tooltip_prefix = "❓ UNLIKELY REAL "
                

        # Create enhanced popup
        popup_html = f"""
        <div style="width:320px; font-family: 'Poppins', sans-serif; padding:10px; background-color:white; border-radius:8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
          <h4 style="margin:0; padding-bottom:5px; color:{color}; border-bottom: 1px solid #eee;">{hazard} - {severity}</h4>
          <p style="margin:10px 0 5px 0; font-size:13px;"><strong>Description:</strong><br>
          {r.get('description', 'No description')[:200]}{'...' if len(r.get('description', '')) > 200 else ''}</p>
          <ul style="list-style-type: none; padding:0; margin:0; font-size:12px;">
            <li><strong style="color:#555;">📅 Timestamp:</strong> {r.get('timestamp', 'N/A')}</li>
            <li><strong style="color:#555;">📍 Location:</strong> {r.get('location', 'Unknown Location')}</li>
            <li><strong style="color:#555;">🤖 AI Confidence:</strong> {r.get('ai_confidence', 0.0):.2f}</li>
            <li><strong style="color:#555;">📈 Final Confidence:</strong> {ai_conf:.2f}</li>
            <li><strong style="color:#555;">✅ Likely Real Status:</strong> {'True' if is_real else 'False'}</li>
            <li><strong style="color:#555;">📊 Official Status:</strong> {report_status}</li>
            <li><strong style="color:#555;">👤 Reporter:</strong> {r.get('reporter_id', 'Anonymous')}</li>
            <li><strong style="color:#555;">🌍 Coordinates:</strong> {lat:.4f}, {lon:.4f}</li>
          </ul>
        </div>
        """
        
        # Use Folium's Icon for better visual control based on status
        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=350),
            icon=folium.Icon(color=icon_color, icon=icon_name, prefix='fa'),
            tooltip=f"{marker_tooltip_prefix}{hazard} - {severity} (Conf: {ai_conf:.2f})"
        ).add_to(target_layer)
        
        # Add to heatmap with confidence weighting (scale up for better visibility)
        heat_data.append([lat, lon, ai_conf * 10])

    # Add heatmap if we have data
    if include_heatmap and heat_data:
        plugins.HeatMap(
            heat_data, 
            radius=25, 
            blur=20, 
            name="Hazard Intensity Heatmap",
            min_opacity=0.2
        ).add_to(m)

    # Add layer control
    folium.LayerControl().add_to(m)
    
    # Add info about data quality (ensuring this is always visible)
    info_html_fixed = f"""
        <div style="position: fixed; 
                    bottom: 10px; left: 10px; width: 220px; height: 80px; 
                    background-color:rgba(255,255,255,0.9); border:1px solid #ccc; border-radius:5px; z-index:9999; 
                    font-size:12px; padding:10px; box-shadow: 0 2px 5px rgba(0,0,0,0.2);">
        <p style="margin:0;"><b>Map Statistics:</b><br>
        📍 <strong>Reports Mapped:</strong> {valid_reports}/{len(reports)}<br>
        🎯 <strong>Map Center:</strong> {center[0]:.2f}, {center[1]:.2f}</p>
        </div>
        """
    m.get_root().html.add_child(folium.Element(info_html_fixed))

    logger.info(f"Created map with {valid_reports}/{len(reports)} valid locations")
    return m

def get_report_statistics(reports):
    """Calculate enhanced statistics."""
    if not reports:
        return {"total": 0}
    
    stats = {"total": len(reports)}
    hazards = {}
    locations = {}
    total_confidence = 0.0
    high_conf_count = 0
    valid_locations = 0
    
    for r in reports:
        # Hazard distribution
        h = r.get("hazard_type", "Unknown")
        hazards[h] = hazards.get(h, 0) + 1
        
        # Location distribution
        loc = r.get("location", "Unknown")
        locations[loc] = locations.get(loc, 0) + 1
        
        # Confidence statistics
        conf = float(r.get("final_confidence", r.get("ai_confidence", 0.0) or 0.0))
        total_confidence += conf
        if conf >= 0.7:
            high_conf_count += 1
            
        # Location accuracy
        if parse_latlon(r.get("latlon", "") or r.get("location", "")):
            valid_locations += 1
    
    stats.update({
        "hazard_distribution": hazards,
        "location_distribution": locations,
        "avg_confidence": (total_confidence / len(reports)) if reports else 0, # Avoid division by zero
        "high_confidence_count": high_conf_count,
        "location_accuracy_percent": (valid_locations / len(reports) * 100) if reports else 0
    })
    
    return stats