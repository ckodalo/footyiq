# footyIQ

Football fixtures + odds, aggregated in one board. Covers the top 5 domestic
leagues, the Champions League, and international tournaments (World Cup,
Euros) — useful when club leagues are out of season.

## Structure

```
footyiq/
├── backend/          FastAPI service
│   ├── main.py
│   ├── requirements.txt
│   └── .env           (not committed — see Setup)
├── frontend/          React + TypeScript (Vite)
│   ├── src/
│   │   ├── App.tsx
│   │   ├── App.css
│   │   ├── main.tsx
│   │   └── vite-env.d.ts
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── .env           (not committed — see Setup)
├── .gitignore
└── README.md
```

## How it works

- **Fixtures** come from [football-data.org](https://www.football-data.org)
  (free tier — 12 competitions, 10 req/min).
- **Odds** come from [The Odds API](https://the-odds-api.com)
  (free tier — 500 req/month).
- The backend matches fixtures to odds events by team name similarity +
  kickoff date, since the two providers don't share fixture IDs. Unmatched
  fixtures return `odds: null` rather than a wrong pairing.
- Both API clients cache responses in-memory (TTL-based) to stay within
  free-tier rate limits.
- The frontend polls `GET /fixtures-with-odds` every 60s and renders all
  tracked competitions as sections, skipping any with zero fixtures.

## Setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env` and fill in:

```
FOOTBALL_DATA_KEY=your_key_here
ODDS_API_KEY=your_key_here
```

Run it:

```bash
uvicorn main:app --reload
```

→ `http://127.0.0.1:8000` · interactive docs at `/docs`

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
```

`frontend/.env` should point at your backend:

```
VITE_API_BASE=http://127.0.0.1:8000
```

Run it:

```bash
npm run dev
```

→ `http://localhost:5173`

Both services need to be running simultaneously for the board to populate.

## Getting API keys

- **football-data.org**: register at https://www.football-data.org/client/register
  — key arrives by email instantly, no card required.
- **The Odds API**: sign up at https://the-odds-api.com
  — free key issued instantly, no card required.

## Known limitations

- football-data.org's free tier does **not** include World Cup/Euro
  qualifiers, AFCON, Copa América, or most friendlies — only the WC/EC final
  tournaments themselves.
- Odds matching is fuzzy by design (no shared IDs across providers). A
  confidence threshold means some fixtures will show `odds: null` even when
  odds technically exist upstream, if the match score is too low to trust.
- In-memory caching means cache state resets on every backend restart —
  fine for a single-instance MVP, not suitable as-is for multi-worker
  production deployment (swap for Redis at that point).