# ZYVORA MUSIC BOT

Multi-server Discord music bot built with discord.py, Wavelink and Lavalink v4.

## Features
- Slash commands and no-prefix text commands.
- Per-server voice player, queue and loop mode.
- Play/search, skip, pause, resume, stop, queue, volume, loop, shuffle, clear, now-playing, join and leave.
- No-prefix commands are recognized only when the message starts with a known command word; ordinary chat is ignored.
- Docker Compose deployment and FastAPI health endpoint at /health.
- Environment-based secrets; never commit .env.

## No-prefix command setup
1. Open the Discord Developer Portal and select your application.
2. Go to **Bot → Privileged Gateway Intents** and enable **Message Content Intent**.
3. Re-invite/update the bot if needed, then restart it.
4. In any server text channel, type commands such as: `play faded`, `skip`, `pause`, `resume`, `queue`, `shuffle`, `volume 50`, `loop track`, `clear`, `stop`, `nowplaying`, `join`, `leave`, or `help`.
5. The user requesting playback must be connected to a voice channel. The bot needs View Channel, Send Messages, Read Message History, Connect and Speak permissions.

## Server moderation
The bot includes permission-gated slash commands:
- `/kick member reason`
- `/ban member reason delete_message_days`
- `/unban user_id reason`
- `/timeout member minutes reason` (up to 28 days)
- `/untimeout member reason`
- `/warn member reason` (DM attempt plus optional log)
- `/purge amount` (1-100 recent messages)
- `/slowmode seconds` (0-21600)
- `/lock` and `/unlock`

Moderation commands are restricted by Discord's native command permissions and check role hierarchy for member actions. The bot's highest role must be above the target. For action logs, create a private moderation-log text channel, copy its channel ID, and set `MOD_LOG_CHANNEL_ID=<channel_id>` in `.env`. Give the bot permission to view and send messages in that channel. Warnings are not stored in a database in this version; the bot attempts to DM the member and writes to the configured log channel when available.

## Provider and copyright limits
A Spotify, Apple Music, Deezer or TIDAL URL is not itself a playable audio stream. The bot does not extract protected audio or bypass DRM. Provider metadata/API adapters are not yet implemented. Playback must use a source and stream that you are authorized to play. YouTube must only be integrated through a terms-compliant, authorized method.


## Community features
- `/rules` posts a ready-to-use server rules and regulations embed.
- `/announce channel title message` posts a staff announcement (Manage Server required).
- `/giveaway prize duration_minutes winners` runs a reaction-entry giveaway and announces randomly selected winners when it ends (Manage Server required). Giveaways are held in memory; restarting the bot cancels active giveaways.
- `/youtube_add channel_id announce_channel`, `/youtube_remove channel_id`, and `/youtube_list` manage upload notifications per server.
- YouTube notifications use the official YouTube Data API v3. Create an API key with YouTube Data API v3 enabled and set `YOUTUBE_API_KEY`. Use the channel ID (usually begins with `UC`); polling runs every five minutes. API quota and channel visibility can affect delivery. Subscription records are stored in `community.sqlite3`; persist this file in Docker.

## Setup
1. Create a bot at https://discord.com/developers/applications.
2. Invite it with the bot and applications.commands scopes. Grant Connect, Speak, View Channel, Send Messages and Read Message History as needed.
3. Copy .env.example to .env and set DISCORD_TOKEN and a strong LAVALINK_PASSWORD.
4. Enable Message Content Intent as described above.
5. Run `docker compose up --build -d`.
6. Check `http://localhost:8080/health` and `docker compose logs -f bot`.
7. Join a voice channel and use `/play` or `play <song>`.

## Local development
Python 3.12 is recommended.
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Start a compatible Lavalink v4 node separately, then:
python -m bot
```

## Command reference
| Slash command | No-prefix text command | Purpose |
|---|---|---|
| /play query | play <song> or p <song> | Play or queue an authorized source |
| /search query | search <song> | Search configured Lavalink sources |
| /skip | skip or next | Skip current track |
| /pause | pause | Pause |
| /resume | resume | Resume |
| /stop | stop | Stop and clear queue |
| /queue | queue or q | Show current and upcoming tracks |
| /volume value | volume <0-100> | Set volume |
| /loop mode | loop <off\|track\|queue> | Set loop mode |
| — | shuffle | Shuffle upcoming queue |
| — | clear | Clear upcoming queue |
| /nowplaying | nowplaying or np | Show current track |
| — | join | Join your voice channel |
| /leave | leave or disconnect | Disconnect |
| — | help | Show text command help |
| /autoplay | — | Preference toggle only; recommendation engine not implemented |

## Production status
This is an upgraded foundation, not yet a fully production-ready premium SaaS. Persistent database-backed settings, interactive search selection, real autoplay recommendations, provider metadata adapters, premium billing/entitlements, authenticated dashboard, observability, rate limiting and deployment hardening remain future work. Do not expose an unauthenticated admin dashboard. Test provider terms and copyright permissions for your region and use case.
