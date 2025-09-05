from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from app.api.auth import get_current_user
from app.ml.recommender import RecommendationEngine

router = APIRouter()
recommendation_engine = RecommendationEngine()

@router.get("/listening-profile")
async def get_listening_profile(current_user: dict = Depends(get_current_user)):
    """Get comprehensive listening analytics"""
    try:
        spotify_tokens = current_user.get("spotify_tokens", {})
        access_token = spotify_tokens.get("access_token")
        
        if not access_token:
            raise HTTPException(status_code=401, detail="Spotify access token required")
        
        sp = await recommendation_engine.get_spotify_client(access_token)

        short_term = await recommendation_engine.get_user_top_tracks(sp, "short_term", 50)
        medium_term = await recommendation_engine.get_user_top_tracks(sp, "medium_term", 50)
        long_term = await recommendation_engine.get_user_top_tracks(sp, "long_term", 50)

        all_track_ids = list(set([t['id'] for t in short_term + medium_term + long_term]))
        features_df = await recommendation_engine.extract_audio_features(sp, all_track_ids)
        
        if features_df.empty:
            return {"error": "Could not analyze listening profile"}
        
        feature_stats = {
            "avg_danceability": float(features_df['danceability'].mean()),
            "avg_energy": float(features_df['energy'].mean()),
            "avg_valence": float(features_df['valence'].mean()),
            "avg_acousticness": float(features_df['acousticness'].mean()),
            "diversity_score": float(features_df.std().mean()),
            "total_tracks_analyzed": len(features_df)
        }
        
        # Generate insights
        insights = generate_listening_insights(feature_stats)
        
        return {
            "feature_analysis": feature_stats,
            "insights": insights,
            "time_ranges": {
                "short_term_count": len(short_term),
                "medium_term_count": len(medium_term),
                "long_term_count": len(long_term)
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analytics error: {str(e)}")

def generate_listening_insights(stats: Dict[str, float]) -> List[str]:
    """Generate personalized insights from listening data"""
    insights = []
    
    if stats["avg_energy"] > 0.7:
        insights.append("You prefer high-energy music that gets you pumped up!")
    elif stats["avg_energy"] < 0.3:
        insights.append("You enjoy calm, low-energy music for relaxation.")
    
    if stats["avg_valence"] > 0.7:
        insights.append("Your music taste skews toward happy, upbeat songs.")
    elif stats["avg_valence"] < 0.3:
        insights.append("You gravitate toward more melancholic or emotional music.")
    
    if stats["avg_danceability"] > 0.7:
        insights.append("You love danceable tracks - perfect for moving to the beat!")
    
    if stats["diversity_score"] > 0.2:
        insights.append("You have diverse musical tastes across different moods and styles.")
    else:
        insights.append("You have consistent preferences - you know what you like!")
    
    return insights