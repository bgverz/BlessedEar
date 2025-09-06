# BlessedEar

An intelligent music recommendation platform that discovers new tracks based on your Spotify listening history, built with FastAPI, React, and machine learning algorithms.

## Features

- **Smart Music Discovery**: AI-powered recommendations that filter out your existing library to suggest genuinely new music
- **Multi-Source Analysis**: Analyzes your top tracks, saved songs, and personal playlists for comprehensive taste profiling
- **Account Switching**: Seamless authentication flow supporting multiple Spotify accounts
- **Real-Time Analytics**: Interactive dashboard with audio feature visualizations and listening pattern insights
- **Mood-Based Playlists**: Generate curated playlists based on different moods (happy, chill, energetic, etc.)
- **Modern UI**: Glassmorphism design with smooth animations and responsive layout

## Tech Stack

**Backend:**
- FastAPI (Python) - High-performance async API framework
- Spotipy - Spotify Web API integration
- SQLAlchemy - Database ORM with PostgreSQL support
- JWT Authentication - Secure session management
- Pydantic - Data validation and settings management

**Frontend:**
- Next.js 14 - React framework with TypeScript
- Tailwind CSS - Utility-first styling
- Framer Motion - Smooth animations
- Lucide React - Modern icon library

**Machine Learning:**
- Custom recommendation engine with multiple fallback strategies
- Audio feature analysis and similarity scoring
- Collaborative filtering based on user listening patterns

## Project Structure

```
BlessedEar/
├── backend/
│   ├── app/
│   │   ├── api/           
│   │   │   ├── auth.py    
│   │   │   ├── recommendations.py
│   │   │   └── playlists.py
│   │   ├── core/          
│   │   │   ├── config.py
│   │   │   └── database.py
│   │   ├── ml/            
│   │   │   ├── recommender.py
│   │   │   └── audio_analyzer.py
│   │   └── models/        
│   │       ├── user.py
│   │       └── playlist.py
├── frontend/
│   ├── src/
│   │   ├── app/           
│   │   │   ├── dashboard/
│   │   │   └── login/
│   │   └── components/   
│   │       ├── auth/
│   │       ├── dashboard/
│   │       └── ui/
└── README.md
```

## Setup Instructions

### Prerequisites

- Python 3.11+
- Node.js 18+
- Spotify Developer Account
- PostgreSQL (optional, defaults to SQLite)

### 1. Spotify API Setup

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Note your **Client ID** and **Client Secret**
4. Add `http://127.0.0.1:8000/api/auth/callback` to Redirect URIs
5. Add user emails to "Users and Access" for development

### 2. Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env` file:
```env
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/api/auth/callback
JWT_SECRET_KEY=your-super-secret-jwt-key
DATABASE_URL=sqlite:///./blessedear.db
```

Start the backend:
```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The application will be available at `http://localhost:3000`

## API Endpoints

### Authentication
- `GET /api/auth/login` - Initiate Spotify OAuth flow
- `GET /api/auth/callback` - Handle OAuth callback
- `POST /api/auth/logout` - Clear user session
- `GET /api/auth/me` - Get current user info

### Recommendations
- `POST /api/recommendations/generate` - Generate personalized recommendations
- `POST /api/recommendations/mood-playlist` - Create mood-based playlist
- `GET /api/recommendations/profile` - Get user's music profile
- `GET /api/recommendations/top-tracks` - Get user's top tracks

### Playlists
- `POST /api/playlists/create` - Create Spotify playlist
- `GET /api/playlists/my-playlists` - Get user's playlists

## How It Works

1. **Authentication**: Users authenticate via Spotify OAuth 2.0
2. **Data Collection**: System analyzes user's top tracks, saved songs, and playlist contents
3. **Recommendation Engine**: 
   - Uses related artists and top tracks when Spotify's recommendation API is unavailable
   - Implements search-based discovery for genre exploration
   - Filters out existing user tracks to ensure only new music is recommended
4. **Smart Filtering**: Prevents recommending songs already in user's library
5. **Multiple Strategies**: Fallback systems ensure recommendations even when primary APIs fail

## Key Features

### Music Discovery Algorithm
- **Related Artist Analysis**: Discovers new music through artists similar to user preferences
- **Genre Exploration**: Uses intelligent search to find tracks in preferred genres
- **Duplicate Prevention**: Sophisticated filtering ensures only new tracks are recommended
- **Mood Matching**: Audio feature analysis for mood-specific playlist generation

### User Experience
- **Real-Time Dashboard**: Live updating analytics and recommendations
- **Account Management**: Switch between multiple Spotify accounts seamlessly
- **Responsive Design**: Works across desktop, tablet, and mobile devices
- **Performance Optimized**: Fast loading with efficient data caching

## Troubleshooting

### Common Issues

**"Authentication failed" error:**
- Verify Spotify app credentials in `.env` file
- Check that redirect URI matches exactly in Spotify dashboard
- Ensure user email is added to app's whitelist

**No recommendations generated:**
- Check backend logs for API errors
- Verify user has sufficient music history (songs, playlists)
- Ensure Spotify app has proper scopes enabled

**Frontend connection issues:**
- Confirm backend is running on port 8000
- Check CORS settings if accessing from different domain

## Development

### Adding New Features

1. **Backend**: Add new endpoints in `app/api/` directory
2. **Frontend**: Create components in `src/components/`
3. **ML**: Extend recommendation logic in `app/ml/recommender.py`

### Testing

```bash
# Backend tests
cd backend
python -m pytest

# Frontend tests  
cd frontend
npm test
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Spotify Web API for music data access
- Next.js and FastAPI
- Open source libraries