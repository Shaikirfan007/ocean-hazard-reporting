import pandas as pd
from typing import List, Dict
import re
from datetime import datetime, timedelta # Added this import to resolve the previous error

# Placeholder for real-time keywords, could be expanded or dynamically loaded
REALTIME_KEYWORDS = ["emergency", "alert", "breaking", "now", "just happened", "live", "urgent"]

def ingest_from_csv(file_obj):
    """
    Accepts a CSV file (uploaded via Streamlit) with columns:
    'text', 'timestamp', 'location' (optional), 'latlon' (optional).
    Returns a pandas DataFrame with sentiment and keyword extraction columns.
    """
    df = pd.read_csv(file_obj)
    if "text" not in df.columns:
        raise ValueError("CSV must contain a 'text' column for social media posts.")
    df["text"] = df["text"].astype(str)
    
    # Simple sentiment (stub) - could be replaced with a more advanced NLP model
    df["sentiment_score"] = df["text"].apply(_simple_sentiment)
    df["keywords"] = df["text"].apply(_extract_keywords)
    
    return df

def _simple_sentiment(text: str) -> float:
    """
    A very basic sentiment analysis stub. In a real application,
    you'd use a dedicated NLP sentiment model (e.g., from NLTK, spaCy, or HuggingFace).
    Returns a score between -1.0 (very negative) and 1.0 (very positive).
    """
    neg = ["not", "no", "nope", "never", "scare", "fear", "panic", "bad", "worry", "damage", "crisis"]
    pos = ["safe", "ok", "fine", "stable", "good", "calm", "clear", "relief"]
    t = text.lower()
    score = 0.0
    for w in pos:
        if w in t:
            score += 0.5
    for w in neg:
        if w in t:
            score -= 0.6
    # clamp score
    return max(-1.0, min(1.0, score))

def _extract_keywords(text: str) -> List[str]:
    """
    Extracts relevant keywords from text. This is a basic stub.
    In a real system, this would use more sophisticated NLP techniques (e.g., TF-IDF, NER).
    """
    # Expanded list of potential keywords related to hazards and real-time indicators
    candidates = [
        "tsunami", "flood", "wave", "storm", "oil", "evacuate", "surge", "coast", "beach",
        "rain", "wind", "port", "ship", "boat", "erosion", "algae", "accident", "warning",
        "damage", "rescue", "missing", "urgent", "emergency", "help"
    ]
    found = []
    t = text.lower()
    for c in candidates:
        if c in t:
            found.append(c)
    return found

def fetch_social_feed_stub(source="twitter", q=None, max_items=50) -> List[Dict]:
    """
    *** CRITICAL FOR REAL-TIME ACCURACY ***
    
    THIS IS A STUB FUNCTION.
    
    To make the AI work accurately based on REAL-TIME situations,
    you MUST replace this function with actual API calls to social media platforms
    (e.g., Twitter/X API, Instagram API, local news APIs, etc.).

    This function should:
    1. Connect to a live social media stream or search API.
    2. Query for posts relevant to potential hazards, possibly filtered by keywords or location.
    3. Parse the API response into a list of dictionaries with consistent keys:
       {'text': str, 'timestamp': str, 'location': Optional[str], 'latlon': Optional[str]}
       Include actual geotags ('latlon') if available from the social media post.
    
    The current implementation only returns a few hardcoded sample posts.
    """
    
    # Example of a hardcoded stub
    sample = [
        {"text": "Breaking: massive waves hitting coastal areas near Chennai right now! #TsunamiAlert #Chennai", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "location":"Chennai Marina", "latlon": "13.0827,80.2707"},
        {"text": "Urgent flooding in Kochi, water levels rising fast near the market. #KochiFlood #Emergency", "timestamp": (datetime.now() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S"), "location":"Kochi", "latlon": "9.9312,76.2673"},
        {"text": "Oil slick reported close to Visakhapatnam shore, environmental impact expected. #OilSpill #Vizag", "timestamp": (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"), "location":"Visakhapatnam", "latlon": "17.6868,83.2185"},
        {"text": "Strong storm surge warnings issued for Mumbai coast. Stay safe! #MumbaiStorm #WeatherAlert", "timestamp": (datetime.now() - timedelta(hours=1, minutes=15)).strftime("%Y-%m-%d %H:%M:%S"), "location":"Mumbai", "latlon": "19.0760,72.8777"},
        {"text": "Fishermen reporting unusually high tides and rough seas in Goa. Stay alert. #GoaCoast #HighWaves", "timestamp": (datetime.now() - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S"), "location":"Goa", "latlon": "15.2993,74.1240"},
        {"text": "Local boat capsized off Mangalore coast. Rescue operations underway. #Mangalore #BoatAccident", "timestamp": (datetime.now() - timedelta(hours=1, minutes=5)).strftime("%Y-%m-%d %H:%M:%S"), "location":"Mangalore", "latlon": "12.9141,74.8560"},
        {"text": "Seaweed bloom turning waters green near Puducherry beaches. #AlgaeBloom #Pondy", "timestamp": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"), "location":"Puducherry", "latlon": "11.9416,79.8083"},
        {"text": "Heavy rain causing coastal erosion in some parts of Odisha. #CoastalErosion #Odisha", "timestamp": (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"), "location":"Bhubaneswar", "latlon": "20.2961,85.8245"},
        {"text": "Minor localized flooding in residential areas of Chennai due to heavy downpour. #ChennaiRains", "timestamp": (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S"), "location":"Chennai", "latlon": "13.0450,80.2500"}, # A slightly different Chennai coord
        # --- Added sample data for Punjab floods ---
        {"text": "URGENT: Massive floods hitting Ludhiana, Punjab! Roads submerged. #PunjabFloods #Ludhiana", "timestamp": (datetime.now() - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S"), "location":"Ludhiana", "latlon": "30.9009,75.8573"},
        {"text": "Heavy rainfall and river overflow in Amritsar. Stay indoors! #AmritsarFloods #Safety", "timestamp": (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"), "location":"Amritsar", "latlon": "31.6340,74.8723"},
        {"text": "Reports of widespread waterlogging across Jalandhar, rescue teams on standby. #JalandharFlood", "timestamp": (datetime.now() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"), "location":"Jalandhar", "latlon": "31.3260,75.5762"},
        # ------------------------------------------
    ]
    
    # Filter by query if provided (simple text match)
    filtered_sample = []
    if q:
        q_lower = q.lower()
        for post in sample:
            if q_lower in post.get("text", "").lower() or \
               q_lower in post.get("location", "").lower():
                filtered_sample.append(post)
    else:
        filtered_sample = sample

    return filtered_sample[:max_items]