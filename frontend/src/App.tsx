import { useEffect, useState, useCallback, useMemo } from "react";

// ---------------- Types ----------------

interface OddsOutcome {
  price: number;
  bookmaker: string;
}

type OddsSummary = Record<string, OddsOutcome> | null;

interface Fixture {
  fixture_id: number;
  competition: string;
  matchday: number | null;
  kickoff_utc: string;
  status: string;
  home_team: string;
  away_team: string;
  odds: OddsSummary;
}

interface LeagueBlock {
  league: string;
  count: number;
  odds_warning: string | null;
  fixtures: Fixture[];
  error?: string;
}

type AllFixturesResponse = Record<string, LeagueBlock | null>;

// ---------------- Config ----------------

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

const LEAGUE_ORDER = ["WC", "EC", "CL", "PL", "PD", "SA", "BL1", "FL1"];

const LEAGUE_LABEL: Record<string, string> = {
  WC: "World Cup",
  EC: "Euros",
  CL: "Champions League",
  PL: "Premier League",
  PD: "La Liga",
  SA: "Serie A",
  BL1: "Bundesliga",
  FL1: "Ligue 1",
};

// ---------------- Helpers ----------------

function formatKickoff(iso: string): { date: string; time: string; isToday: boolean } {
  const d = new Date(iso);
  const now = new Date();
  const isToday = d.toDateString() === now.toDateString();

  const date = d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
  const time = d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });

  return { date, time, isToday };
}

function bestOutcomeEntries(odds: OddsSummary): [string, OddsOutcome][] {
  if (!odds) return [];
  const entries = Object.entries(odds);
  return entries.sort((a, b) => {
    if (a[0] === "Draw") return 0;
    if (b[0] === "Draw") return 0;
    return a[0].localeCompare(b[0]);
  });
}

// ---------------- Component: Odds pill ----------------

function OddsRow({ odds }: { odds: OddsSummary }) {
  if (!odds) {
    return <span className="odds-row odds-row--empty">odds pending</span>;
  }

  const entries = bestOutcomeEntries(odds);

  return (
    <div className="odds-row">
      {entries.map(([name, outcome]) => (
        <div className="odds-pill" key={name} title={`Best price via ${outcome.bookmaker}`}>
          <span className="odds-pill__label">{name}</span>
          <span className="odds-pill__price">{outcome.price.toFixed(2)}</span>
        </div>
      ))}
    </div>
  );
}

// ---------------- Component: Fixture row ----------------

function FixtureRow({ fixture }: { fixture: Fixture }) {
  const { date, time, isToday } = formatKickoff(fixture.kickoff_utc);
  const isLive = fixture.status === "IN_PLAY" || fixture.status === "PAUSED";

  return (
    <div className="fixture-row">
      <div className="fixture-row__time">
        {isLive ? (
          <span className="live-dot">LIVE</span>
        ) : (
          <>
            <span className="fixture-row__date">{isToday ? "Today" : date}</span>
            <span className="fixture-row__hour">{time}</span>
          </>
        )}
      </div>

      <div className="fixture-row__teams">
        <span className="team">{fixture.home_team}</span>
        <span className="vs">v</span>
        <span className="team">{fixture.away_team}</span>
      </div>

      <div className="fixture-row__odds">
        <OddsRow odds={fixture.odds} />
      </div>
    </div>
  );
}

// ---------------- Component: League section ----------------

function LeagueSection({ code, block }: { code: string; block: LeagueBlock | null }) {
  if (!block) {
    return null; // backend returned nothing usable for this league — skip quietly
  }

  const label = LEAGUE_LABEL[code] ?? block.league;

  if (block.error) {
    return (
      <section className="league-section">
        <header className="league-section__header">
          <h2>{label}</h2>
        </header>
        <p className="league-section__error">Couldn't load this competition: {block.error}</p>
      </section>
    );
  }

  if (block.fixtures.length === 0) {
    return null; // skip empty leagues silently — keeps the board tight
  }

  return (
    <section className="league-section">
      <header className="league-section__header">
        <h2>{label}</h2>
        <span className="league-section__count">{block.count} upcoming</span>
      </header>

      {block.odds_warning && (
        <p className="league-section__warning">Odds unavailable: {block.odds_warning}</p>
      )}

      <div className="fixture-list">
        {block.fixtures.map((f) => (
          <FixtureRow key={f.fixture_id} fixture={f} />
        ))}
      </div>
    </section>
  );
}

// ---------------- Main App ----------------

export default function App() {
  const [data, setData] = useState<AllFixturesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchFixtures = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/fixtures-with-odds?days_ahead=10`);
      if (!res.ok) throw new Error(`API returned ${res.status}`);
      const json: AllFixturesResponse = await res.json();
      setData(json);
      setLastUpdated(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch fixtures");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFixtures();
    const interval = setInterval(fetchFixtures, 60_000); // refresh every 60s
    return () => clearInterval(interval);
  }, [fetchFixtures]);

  const orderedLeagues = useMemo(() => {
    if (!data) return [];
    const known = LEAGUE_ORDER.filter((code) => code in data);
    const unknown = Object.keys(data).filter((code) => !LEAGUE_ORDER.includes(code));
    return [...known, ...unknown];
  }, [data]);

  const totalFixtures = useMemo(() => {
    if (!data) return 0;
    return Object.values(data).reduce(
      (sum, block) => sum + (block?.fixtures?.length ?? 0),
      0
    );
  }, [data]);

  return (
    <div className="app">
      <header className="app__header">
        <div className="brand">
          <span className="brand__mark">⚽</span>
          <span className="brand__name">footy<span className="brand__name--accent">IQ</span></span>
        </div>

        <div className="app__status">
          {lastUpdated && (
            <span className="status-text">
              {totalFixtures} fixtures · updated {lastUpdated.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
          <button className="refresh-btn" onClick={fetchFixtures} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </header>

      <main className="app__main">
        {error && (
          <div className="error-banner">
            <strong>Couldn't reach the API.</strong> Is the FastAPI server running at {API_BASE}? ({error})
          </div>
        )}

        {loading && !data && <div className="loading-state">Loading fixtures…</div>}

        {data && (
          <div className="board">
            {orderedLeagues.map((code) => (
              <LeagueSection key={code} code={code} block={data[code]} />
            ))}
          </div>
        )}
      </main>

      <footer className="app__footer">
        <span>Fixtures: football-data.org · Odds: The Odds API</span>
      </footer>
    </div>
  );
}