"""
Sports Companion MVP — Football fixtures + odds aggregation.

Run:
    pip install fastapi uvicorn httpx python-dotenv
    uvicorn main:app --reload

Then visit http://127.0.0.1:8000/docs
"""

import os
import time
import asyncio
import httpx
from datetime import date, timedelta
from difflib import SequenceMatcher
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

FOOTBALL_DATA_KEY = os.getenv("FOOTBALL_DATA_KEY", "")
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")

FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# football-data.org competition codes -> TheOddsAPI sport keys
# (free tier of football-data.org covers these 12 competitions)
LEAGUE_MAP = {
    "PL": {"name": "Premier League", "odds_key": "soccer_epl"},
    "PD": {"name": "La Liga", "odds_key": "soccer_spain_la_liga"},
    "SA": {"name": "Serie A", "odds_key": "soccer_italy_serie_a"},
    "BL1": {"name": "Bundesliga", "odds_key": "soccer_germany_bundesliga"},
    "FL1": {"name": "Ligue 1", "odds_key": "soccer_france_ligue_one"},
    "CL": {"name": "Champions League", "odds_key": "soccer_uefa_champs_league"},
    "WC": {"name": "FIFA World Cup", "odds_key": "soccer_fifa_world_cup"},
    "EC": {"name": "European Championship", "odds_key": "soccer_uefa_european_championship"},
}

app = FastAPI(
    title="Sports Companion MVP",
    description="Football fixtures + odds, aggregated. Free-tier data sources.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- tiny in-memory cache so we don't burn the free-tier quotas ----
_cache: dict[str, tuple[float, object]] = {}


def cache_get(key: str, ttl: int):
    entry = _cache.get(key)
    if entry and time.time() - entry[0] < ttl:
        return entry[1]
    return None


def cache_set(key: str, value):
    _cache[key] = (time.time(), value)


# ---- football-data.org client ----
async def fd_get(path: str, params: dict | None = None):
    if not FOOTBALL_DATA_KEY:
        raise HTTPException(500, "FOOTBALL_DATA_KEY not set in .env")

    cache_key = f"fd:{path}:{params}"
    cached = cache_get(cache_key, ttl=120)
    if cached is not None:
        return cached

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{FOOTBALL_DATA_BASE}{path}",
            headers={"X-Auth-Token": FOOTBALL_DATA_KEY},
            params=params or {},
            timeout=10.0,
        )
        if resp.status_code == 429:
            raise HTTPException(429, "football-data.org rate limit hit (10 req/min). Wait a moment.")
        resp.raise_for_status()
        data = resp.json()
        cache_set(cache_key, data)
        return data


# ---- TheOddsAPI client ----
async def odds_get(sport_key: str):
    if not ODDS_API_KEY:
        raise HTTPException(500, "ODDS_API_KEY not set in .env")

    cache_key = f"odds:{sport_key}"
    cached = cache_get(cache_key, ttl=180)
    if cached is not None:
        return cached

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ODDS_API_BASE}/sports/{sport_key}/odds",
            params={
                "apiKey": ODDS_API_KEY,
                "regions": "uk,eu",
                "markets": "h2h",
                "oddsFormat": "decimal",
            },
            timeout=10.0,
        )
        if resp.status_code == 401:
            raise HTTPException(401, "Invalid TheOddsAPI key")
        resp.raise_for_status()
        data = resp.json()
        cache_set(cache_key, data)
        return data


def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def match_odds_to_fixture(fixture: dict, odds_events: list) -> dict | None:
    """
    football-data.org and TheOddsAPI don't share IDs, so we match
    fixtures to odds events by team name similarity + kickoff date.
    """
    home = fixture["homeTeam"]["name"]
    away = fixture["awayTeam"]["name"]
    fixture_date = fixture["utcDate"][:10]

    best_match = None
    best_score = 0.0

    for event in odds_events:
        if event.get("commence_time", "")[:10] != fixture_date:
            continue
        score = (
            name_similarity(str(home), event.get("home_team", ""))
            + name_similarity(str(away), event.get("away_team", ""))
        ) / 2
        if score > best_score:
            best_score = score
            best_match = event

    # require a reasonably confident match
    if best_match and best_score > 0.55:
        return best_match
    return None


def summarize_odds(event: dict) -> dict | None:
    """Pull best available decimal odds per outcome across bookmakers."""
    if not event or not event.get("bookmakers"):
        return None

    best = {}  # outcome name -> {price, bookmaker}
    for bookmaker in event["bookmakers"]:
        for market in bookmaker.get("markets", []):
            if market["key"] != "h2h":
                continue
            for outcome in market["outcomes"]:
                name = outcome["name"]
                price = outcome["price"]
                if name not in best or price > best[name]["price"]:
                    best[name] = {"price": price, "bookmaker": bookmaker["title"]}

    return best or None


# ---------------- endpoints ----------------

@app.get("/")
async def root():
    return {
        "app": "Sports Companion MVP",
        "docs": "/docs",
        "leagues": list(LEAGUE_MAP.keys()),
        "configured": {
            "football_data_key": bool(FOOTBALL_DATA_KEY),
            "odds_api_key": bool(ODDS_API_KEY),
        },
    }


@app.get("/leagues")
async def leagues():
    return LEAGUE_MAP


@app.get("/fixtures/{league_code}")
async def get_fixtures(
    league_code: str,
    days_ahead: int = Query(7, ge=1, le=14, description="How many days ahead to fetch"),
):
    """Raw upcoming fixtures for one league (no odds)."""
    league_code = league_code.upper()
    if league_code not in LEAGUE_MAP:
        raise HTTPException(404, f"Unknown league. Choose from {list(LEAGUE_MAP)}")

    date_from = date.today().isoformat()
    date_to = (date.today() + timedelta(days=days_ahead)).isoformat()

    data = await fd_get(
        f"/competitions/{league_code}/matches",
        params={"dateFrom": date_from, "dateTo": date_to, "status": "SCHEDULED"},
    )
    return data


async def build_league_block(league_code: str, days_ahead: int):
    """Build a single league block object (league, count, odds_warning, fixtures)"""
    league_code = league_code.upper()
    league_info = LEAGUE_MAP[league_code]

    date_from = date.today().isoformat()
    date_to = (date.today() + timedelta(days=days_ahead)).isoformat()

    fixtures_data = await fd_get(
        f"/competitions/{league_code}/matches",
        params={"dateFrom": date_from, "dateTo": date_to, "status": "SCHEDULED"},
    )
    fixtures = fixtures_data.get("matches", [])

    odds_events = []
    odds_error = None
    try:
        odds_events = await odds_get(league_info["odds_key"])
    except HTTPException as e:
        odds_error = e.detail

    results = []
    for fixture in fixtures:
        matched_event = match_odds_to_fixture(fixture, odds_events) if odds_events else None
        odds_summary = summarize_odds(matched_event) if matched_event else None

        results.append({
            "fixture_id": fixture["id"],
            "competition": league_info["name"],
            "matchday": fixture.get("matchday"),
            "kickoff_utc": fixture["utcDate"],
            "status": fixture["status"],
            "home_team": fixture["homeTeam"]["name"],
            "away_team": fixture["awayTeam"]["name"],
            "odds": odds_summary,
        })

    return {
        "league": league_info["name"],
        "count": len(results),
        "odds_warning": odds_error,
        "fixtures": results,
    }


@app.get("/fixtures-with-odds/{league_code}")
async def fixtures_with_odds(
    league_code: str,
    days_ahead: int = Query(7, ge=1, le=14),
):
    """Return a single league block (keeps compatibility)."""
    league_code = league_code.upper()
    if league_code not in LEAGUE_MAP:
        raise HTTPException(404, f"Unknown league. Choose from {list(LEAGUE_MAP)}")

    block = await build_league_block(league_code, days_ahead)
    return block


@app.get("/fixtures-with-odds")
async def fixtures_with_odds_all(days_ahead: int = Query(7, ge=1, le=14)):
    """Return a mapping of league_code -> league block for all configured leagues."""
    # build blocks concurrently to speed up responses
    tasks = [build_league_block(code, days_ahead) for code in LEAGUE_MAP.keys()]
    blocks = await asyncio.gather(*tasks)
    return {code: block for code, block in zip(LEAGUE_MAP.keys(), blocks)}


@app.get("/health")
async def health():
    return {"status": "ok", "cached_keys": len(_cache)}