# ZYVORA MUSIC BOT

Multi-server Discord music bot starter using discord.py, Wavelink and Lavalink v4.

## Current scope
- Slash commands: /play, /search, /skip, /pause, /resume, /stop, /queue, /volume, /loop, /nowplaying, /leave, /autoplay.
- Independent voice player and queue per Discord server.
- Docker Compose for the bot and Lavalink.
- FastAPI health endpoint at /health.
- Environment-based secrets; never commit .env.

## Important provider and copyright limits
A Spotify, Apple Music, Deezer or TIDAL URL is not itself a playable audio stream. This starter recognizes those link types and refuses to extract protected audio. Provider metadata/API adapters are not yet implemented. Playback must use a source and stream that you are authorized to play. YouTube must only be integrated through a terms-compliant, authorized method. No DRM bypass, scraping workaround, or unofficial extraction is included.

## Setup
1. Create a bot at https://discord.com/developers/applications.
2. Enable the bot and invite it with the bot and applications.commands scopes. Grant Connect, Speak, and Use Voice Activity as needed.
3. Copy .env.example to .env and set DISCORD_TOKEN and a strong LAVALINK_PASSWORD.
4. Run `docker compose up --build -d`.
5. Check `http://localhost:8080/health` and `docker compose logs -f bot`.
6. Join a voice channel and use `/play` with a supported, permitted source query or direct stream URL.

## Local development
Python 3.12 is recommended.
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Start a compatible Lavalink v4 node separately, then:
python -m bot
```

## Commands
| Command | Purpose |
|---|---|
| /play query | Play or queue an authorized source |
| /search query | Search configured Lavalink sources |
| /skip | Skip current track |
| /pause, /resume | Pause or resume |
| /stop | Stop and clear queue |
| /queue | Show current and upcoming tracks |
| /volume value | Set volume from 0 to 100 |
| /loop mode | Set off, track, or queue |
| /nowplaying | Show current track |
| /leave | Disconnect |
| /autoplay | Toggle the autoplay preference (preference only in this starter) |

## Production status
This is a starter implementation, not yet a production-ready premium SaaS. Persistent settings, interactive search selection, real autoplay, provider metadata adapters, premium billing/entitlements, authenticated dashboard, database, observability and deployment hardening remain future work. Do not expose an unauthenticated admin dashboard. Review provider terms and copyright permissions for your region and use case.
