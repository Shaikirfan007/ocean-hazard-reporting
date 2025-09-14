import os
import re
from typing import Tuple
from dotenv import load_dotenv

load_dotenv()
HF_TOKEN = os.getenv("HF_TOKEN", None)

# Enhanced keywords with better coverage and confidence scoring
KEYWORDS = {
    "Tsunami": {
        "high": ["tsunami", "massive waves", "giant wave", "wall of water", "sea surge"],
        "medium": ["huge waves", "tidal wave", "big wave", "abnormal waves", "ocean surge"],
        "low": ["large waves", "high tide", "wave activity"]
    },
    "Flood": {
        "high": ["flash flood", "flooding", "inundation", "submerged", "water logging"],
        "medium": ["flood", "waterlogged", "overflow", "heavy rain", "water level rising"],
        "low": ["water level", "rain", "wet"]
    },
    "Cyclone": {
        "high": ["cyclone", "hurricane", "typhoon", "severe storm", "wind damage"],
        "medium": ["storm", "strong winds", "gale", "low pressure", "tempest"],
        "low": ["wind", "weather", "cloudy"]
    },
    "High Waves": {
        "high": ["dangerous waves", "rough sea", "choppy sea", "sea turbulence"],
        "medium": ["high waves", "wave height", "swells", "tidal surge"],
        "low": ["waves", "sea conditions"]
    },
    "Oil Spill": {
        "high": ["oil spill", "petroleum spill", "crude oil leak", "environmental disaster"],
        "medium": ["oil slick", "oil pollution", "tar balls", "chemical spill"],
        "low": ["oil", "pollution", "slick"]
    },
    "Coastal Erosion": {
        "high": ["severe erosion", "coast eroding", "land loss", "beach receding"],
        "medium": ["erosion", "shoreline damage", "sand loss"],
        "low": ["shore", "beach", "coast"]
    },
    "Storm Surge": {
        "high": ["storm surge", "coastal inundation", "surge flooding"],
        "medium": ["high tide surge", "tidal surge", "coastal flooding"],
        "low": ["high tide", "surge"]
    },
    "Algal Bloom": {
        "high": ["toxic algae", "red tide", "algal bloom", "water contamination"],
        "medium": ["algae bloom", "green tide", "water discoloration"],
        "low": ["algae", "green water"]
    },
    "Ship Accident": {
        "high": ["ship accident", "vessel collision", "boat capsized", "maritime disaster"],
        "medium": ["shipwreck", "boat accident", "ferry accident"],
        "low": ["ship", "boat", "vessel"]
    },
    "Drowning": {
        "high": ["drowning emergency", "person swept away", "rescue needed urgently"],
        "medium": ["drowning", "man overboard", "missing swimmer"],
        "low": ["swimming", "water rescue"]
    }
}

# Enhanced urgency indicators with weights
URGENT_WORDS = {
    "critical": 1.0,
    "emergency": 0.9,
    "urgent": 0.8,
    "help": 0.7,
    "danger": 0.8,
    "crisis": 0.9,
    "alert": 0.7,
    "immediate": 0.8,
    "now": 0.6,
    "breaking": 0.7,
    "live": 0.6
}

# Location confidence boosters (Indian coastal areas)
COASTAL_LOCATIONS = [
    "mumbai", "chennai", "kolkata", "kochi", "visakhapatnam", "goa", "mangalore",
    "puducherry", "bhubaneswar", "karaikal", "daman", "diu", "paradip", "haldia",
    "kandla", "jawaharlal nehru port", "cochin port", "chennai port", "kolkata port"
]

def _enhanced_heuristic_classify(text: str) -> Tuple[str, float, bool]:
    """
    Enhanced heuristic classification with improved accuracy and confidence calculation.
    """
    if not text:
        return "Unknown", 0.0, False
        
    t = text.lower()
    hazard_scores = {}
    matched_keywords = {}
    
    # Calculate weighted scores for each hazard type
    for hazard, keyword_groups in KEYWORDS.items():
        score = 0.0
        matches = []
        
        for confidence_level, keywords in keyword_groups.items():
            weight = {"high": 0.4, "medium": 0.25, "low": 0.1}[confidence_level]
            for keyword in keywords:
                if keyword in t:
                    score += weight
                    matches.append(keyword)
        
        if score > 0:
            hazard_scores[hazard] = score
            matched_keywords[hazard] = matches
    
    # Determine best hazard match
    if not hazard_scores:
        return "Unknown", 0.15, False
    
    best_hazard = max(hazard_scores.keys(), key=lambda k: hazard_scores[k])
    base_confidence = min(0.95, hazard_scores[best_hazard])
    
    # Boost confidence based on urgency words
    urgency_boost = 0.0
    for urgent_word, weight in URGENT_WORDS.items():
        if urgent_word in t:
            urgency_boost += weight * 0.15  # Max boost of ~0.15
    
    # Boost confidence if location is coastal
    location_boost = 0.0
    for location in COASTAL_LOCATIONS:
        if location in t:
            location_boost = 0.1
            break
    
    # Calculate final confidence
    final_confidence = min(0.98, base_confidence + urgency_boost + location_boost)
    
    # Determine if report is likely real based on multiple factors
    is_real = (
        (final_confidence >= 0.7) or  # High confidence threshold
        (final_confidence >= 0.5 and urgency_boost > 0.3) or  # Medium confidence with high urgency
        (final_confidence >= 0.6 and location_boost > 0)  # Medium-high confidence with location match
    )
    
    return best_hazard, round(final_confidence, 2), bool(is_real)

# Try to load HuggingFace model safely
USE_HF = False
classifier = None

try:
    if HF_TOKEN:
        from huggingface_hub import login
        try:
            login(HF_TOKEN)
        except Exception:
            pass

    from transformers import pipeline
    # Use a more appropriate model for disaster/emergency classification
    try:
        classifier = pipeline(
            "text-classification", 
            model="cardiffnlp/twitter-roberta-base-sentiment-latest",
            return_all_scores=True
        )
        USE_HF = True
    except Exception:
        # Fallback to basic sentiment model
        classifier = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")
        USE_HF = True
        
except Exception as e:
    USE_HF = False
    classifier = None

def classify_text(text: str) -> Tuple[str, float, bool]:
    """
    Enhanced text classification with improved accuracy for ocean hazard detection.
    Returns (label, confidence, is_real).
    
    This function combines keyword matching with ML sentiment analysis for better accuracy.
    For production, integrate with real-time verification systems.
    """
    if not text:
        return "Unknown", 0.0, False

    # Always run enhanced heuristic classification
    heuristic_result = _enhanced_heuristic_classify(text)
    
    if not USE_HF or classifier is None:
        return heuristic_result
    
    # Enhance with HuggingFace model if available
    try:
        snippet = text if len(text) <= 512 else text[:510] + "..."
        
        # Get sentiment/classification from model
        model_result = classifier(snippet)
        
        if isinstance(model_result, list) and len(model_result) > 0:
            # Handle models that return all scores
            if isinstance(model_result[0], list):
                negative_score = 0.0
                for result in model_result[0]:
                    if result.get("label", "").upper() in ["NEGATIVE", "LABEL_0"]:
                        negative_score = result.get("score", 0.0)
                        break
                sentiment_confidence = negative_score
            else:
                # Handle single result
                result = model_result[0] if isinstance(model_result, list) else model_result
                sentiment_label = result.get("label", "")
                sentiment_confidence = result.get("score", 0.0)
                
                # Convert positive sentiment models to negative-focused scoring
                if sentiment_label.upper() in ["POSITIVE", "LABEL_1"]:
                    sentiment_confidence = 1.0 - sentiment_confidence
        else:
            sentiment_confidence = 0.0
        
        # Combine heuristic and ML results
        heuristic_label, heuristic_conf, heuristic_real = heuristic_result
        
        # Weight the combination based on confidence levels
        if heuristic_conf >= 0.7:  # High heuristic confidence
            final_confidence = 0.7 * heuristic_conf + 0.3 * sentiment_confidence
        elif sentiment_confidence >= 0.7:  # High ML confidence
            final_confidence = 0.4 * heuristic_conf + 0.6 * sentiment_confidence
        else:  # Balanced combination
            final_confidence = 0.5 * heuristic_conf + 0.5 * sentiment_confidence
        
        final_confidence = min(0.98, max(0.0, final_confidence))
        
        # Determine if real based on combined analysis
        is_real = (
            final_confidence >= 0.65 or
            (heuristic_real and final_confidence >= 0.5) or
            (sentiment_confidence >= 0.8 and heuristic_conf >= 0.4)
        )
        
        return heuristic_label, round(final_confidence, 2), bool(is_real)
        
    except Exception as e:
        # Fallback to heuristic if ML fails
        return heuristic_result

# Quick test function for validation
def test_classification():
    """Test function to validate classification accuracy"""
    test_cases = [
        ("Massive tsunami waves hitting Chennai Marina right now! Emergency!", "Tsunami", True),
        ("Heavy flooding in Kochi port area, water rising rapidly", "Flood", True),
        ("Oil spill reported near Visakhapatnam coast, urgent cleanup needed", "Oil Spill", True),
        ("Just saw a ship in the distance, looks normal", "Unknown", False),
        ("Nice weather at the beach today", "Unknown", False),
        ("URGENT: Cyclone approaching Mumbai coast, winds 120 kmph", "Cyclone", True),
        ("Boat capsized near Mangalore, rescue operations underway", "Ship Accident", True)
    ]
    
    print("Testing AI Model Classification:")
    print("-" * 50)
    
    for text, expected_hazard, expected_real in test_cases:
        label, conf, is_real = classify_text(text)
        status = "✓" if (is_real == expected_real) else "✗"
        print(f"{status} Text: {text[:50]}...")
        print(f"   Result: {label} (conf: {conf:.2f}, real: {is_real})")
        print(f"   Expected: {expected_hazard} (real: {expected_real})")
        print()

if __name__ == "_main_":
    test_classification()