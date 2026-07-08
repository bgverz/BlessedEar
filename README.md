# BlessedEar

A music recommendation platform built on top of your own Spotify listening
history — genre and era breakdowns, mainstream-vs-niche taste analysis, and
recommendations generated from the artists, albums, and genres you already
play. Built with FastAPI and Next.js.

## Features

- **Music discovery**: recommendations built from artist/album co-occurrence
  in your library, scored by real listening frequency — not simulated scores
- **Genre discovery**: surfaces tracks from genres outside your current
  rotation via Spotify search
- **Mood playlists**: keyword-matches your library against a mood, with a
  transparent match-strength score
- **Sound Profile analytics**: genre breakdown, era distribution, popularity
  (mainstream vs. niche), library growth over time, and a taste-shift
  indicator — all computed from real Spotify data (tracks, artists, genres,
  timestamps), since Spotify deprecated the audio-features/recommendations
  endpoints for new apps in late 2024
- **Playlist management**: save generated playlists, browse them, export any
  saved playlist back to Spotify as a real playlist
- **Spotify OAuth**: session persisted via JWT + localStorage, with automatic
  Spotify token refresh and real server-side logout (clears stored tokens)

## Tech Stack

**Backend:** FastAPI, SQLAlchemy (SQLite by default, Postgres-ready), Spotipy,
PyJWT, Pydantic Settings

**Frontend:** Next.js 14 (App Router) + TypeScript, Tailwind CSS,
Framer Motion, Recharts, react-hot-toast

## Project Structure

```
BlessedEar/
├── backend/
│   └── app/
│       ├── api/            # auth.py, recommendations.py, analytics.py, playlists.py
│       ├── core/           # config.py, database.py
│       ├── ml/             # recommender.py, analytics_engine.py
│       └── models/         # user.py, playlist.py
├── frontend/
│   └── src/
│       ├── app/            # /, /login, /dashboard
│       ├── components/     # layout/, dashboard/, ui/
│       └── lib/            # api-client.ts, auth-context.tsx
└── docker-compose.yml
```

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- A Spotify Developer app

### 1. Spotify app setup

1. Create an app at the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Note the **Client ID** and **Client Secret**
3. Add `http://127.0.0.1:8000/api/auth/callback` to Redirect URIs
4. Add your account under "Users and Access" (required for apps in development mode)

### 2. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create `backend/.env`:
```env
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/api/auth/callback
FRONTEND_URL=http://localhost:3000
JWT_SECRET_KEY=a-long-random-secret
DATABASE_URL=sqlite:///./blessedear.db
DEBUG=true
```

Run it:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
```

Create `frontend/.env.local`:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

```bash
npm run dev
```

The app runs at `http://localhost:3000`.

### Docker (optional)

```bash
JWT_SECRET_KEY=... SPOTIFY_CLIENT_ID=... SPOTIFY_CLIENT_SECRET=... docker compose up --build
```

Runs Postgres, the backend, and the frontend together. See `docker-compose.yml`
for the full environment variable list.

## API

**Auth** — `GET /api/auth/login`, `GET /api/auth/callback`, `GET /api/auth/me`,
`POST /api/auth/logout`, `POST /api/auth/refresh`

**Recommendations** — `POST /api/recommendations/generate`,
`POST /api/recommendations/mood-playlist`, `GET /api/recommendations/profile`,
`GET /api/recommendations/top-tracks`, `GET /api/recommendations/discover/{type}`
(`similar` | `new-genres` | `trending` | `deep-cuts`), `GET /api/recommendations/genres`

**Analytics** — `GET /api/analytics/listening-profile`

**Playlists** — `POST /api/playlists/save`, `GET /api/playlists/my-playlists`,
`GET /api/playlists/{id}`, `DELETE /api/playlists/{id}`,
`POST /api/playlists/{id}/export-to-spotify`

Debug endpoints under `/api/recommendations/debug/*` only respond when
`DEBUG=true`.

## How it works

Spotify deprecated its audio-features and seed-based recommendations
endpoints for apps without extended quota access in late 2024, so this app
avoids them entirely:

- **Recommendations** come from artist/album co-occurrence in your top
  tracks, saved tracks, playlists, and recently played — deep cuts from
  artists and albums you already play, scored by how often they show up in
  your library.
- **Genre discovery** uses Spotify's search endpoint (`genre:"x"` queries),
  picking genres your listening data doesn't already cover.
- **Analytics** aggregates real artist `genres` tags, track/artist
  `popularity`, album `release_date`, and save/listen timestamps — no
  simulated or random data anywhere in the pipeline.

## License

MIT
