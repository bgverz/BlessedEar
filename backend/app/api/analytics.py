from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List

from app.api.auth import get_current_user
from app.ml.recommender import RecommendationEngine
from app.ml.analytics_engine import AnalyticsEngine

router = APIRouter()
recommendation_engine = RecommendationEngine()
analytics_engine = AnalyticsEngine()

@router.get("/listening-profile")
async def get_listening_profile(current_user: dict = Depends(get_current_user)):
    """Get comprehensive listening analytics built from real Spotify data"""
    try:
        spotify_tokens = current_user.get("spotify_tokens", {})
        access_token = spotify_tokens.get("access_token")

        if not access_token:
            raise HTTPException(status_code=401, detail="Spotify access token required")

        sp = await recommendation_engine.get_spotify_client(access_token)

        short_term = await recommendation_engine.get_user_top_tracks(sp, "short_term", 50)
        medium_term = await recommendation_engine.get_user_top_tracks(sp, "medium_term", 50)
        long_term = await recommendation_engine.get_user_top_tracks(sp, "long_term", 50)

        profile = await analytics_engine.build_profile(sp, short_term, medium_term, long_term)

        if "error" in profile:
            raise HTTPException(status_code=404, detail=profile["error"])

        insights = generate_listening_insights(profile)

        return {
            **profile,
            "insights": insights,
            "time_ranges": {
                "short_term_count": len(short_term),
                "medium_term_count": len(medium_term),
                "long_term_count": len(long_term),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analytics error: {str(e)}")

def generate_listening_insights(profile: Dict[str, Any]) -> List[str]:
    """Generate human-readable insights from the real analytics profile"""
    insights = []

    genre_breakdown = profile.get("genre_breakdown", [])
    if genre_breakdown:
        top_genre = genre_breakdown[0]
        insights.append(
            f"{top_genre['genre'].title()} is your most-played genre, "
            f"making up about {round(top_genre['share'] * 100)}% of your listening."
        )

    popularity = profile.get("popularity_profile", {})
    if popularity.get("taste_label") == "Mainstream":
        insights.append("You gravitate toward popular, chart-friendly tracks.")
    elif popularity.get("taste_label") == "Deep cuts / niche":
        insights.append("You lean toward deep cuts and lesser-known artists.")
    else:
        insights.append("You strike a balance between popular hits and lesser-known tracks.")

    diversity = profile.get("diversity_score", 0)
    if diversity > 0.7:
        insights.append("Your taste spans a wide range of genres.")
    elif diversity < 0.3 and genre_breakdown:
        insights.append("You have a focused, consistent genre preference.")

    era_distribution = profile.get("era_distribution", [])
    if era_distribution:
        dominant_era = max(era_distribution, key=lambda e: e['count'])
        if len(era_distribution) >= 4:
            insights.append(f"You dig across {len(era_distribution)} different decades of music.")
        else:
            insights.append(f"Most of what you listen to is from the {dominant_era['decade']}.")

    taste_shift = profile.get("taste_shift", {})
    if taste_shift.get("description"):
        insights.append(taste_shift["description"])

    return insights
