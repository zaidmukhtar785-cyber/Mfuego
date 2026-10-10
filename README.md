# Fuegos — Discord Bot + Live Dashboard

A starter project for a Discord bot and FastAPI dashboard deployed as separate Railway services, sharing one PostgreSQL database.

## Included
- Python `discord.py` bot with hybrid slash/prefix commands (`/ping`, `!ping`, `/setprefix`, `!setprefix`, `/config`, `!config`, `/setwelcome`, `!setwelcome`, `/modhelp`)
- Configurable per-server prefixes, welcome channel/message and basic moderation command
- Discord OAuth2 dashboard login
- Server list restricted to servers where the user has Manage Server or Administrator permissions
- Dashboard settings saved in the same database used by the bot
- Basic responsive dashboard UI with auto-refresh to show changes made elsewhere
- Health endpoints for Railway

## Deploy on Railway

Create a GitHub repository and upload this folder's contents. In Railway, create:
1. A PostgreSQL service.
2. A bot service from this repo with start command: `python -m app.bot`
3. A dashboard web service from this repo with start command: `uvicorn app.web:app --host 0.0.0.0 --port $PORT`

Set the same `DATABASE_URL` on both services using Railway's PostgreSQL reference variable. Railway URLs can use `postgresql://`; this project normalizes it to `postgresql+asyncpg://`.

### Required variables
- `DISCORD_BOT_TOKEN` — Discord bot token; only set in Railway variables, never commit it.
- `DISCORD_CLIENT_ID` — Discord application/client ID.
- `DISCORD_CLIENT_SECRET` — OAuth2 client secret, only for dashboard.
- `DISCORD_REDIRECT_URI` — exact callback URL, e.g. `https://YOUR-DASHBOARD.up.railway.app/auth/callback`
- `SESSION_SECRET` — long random secret.
- `DATABASE_URL` — Railway PostgreSQL URL.
- `DASHBOARD_BASE_URL` — public dashboard URL, e.g. `https://YOUR-DASHBOARD.up.railway.app`
- Optional `DEFAULT_PREFIX` — defaults to `!`.

Add this OAuth2 redirect URL in Discord Developer Portal → OAuth2 → Redirects:
`https://YOUR-DASHBOARD.up.railway.app/auth/callback`

Enable **Server Members Intent** in the Developer Portal for welcome messages. Enable **Message Content Intent** for prefix commands. Invite the bot with `bot` and `applications.commands` scopes and only the permissions it needs.

## Local development
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Fill in .env; do not share your token.
python -m app.bot
# In another terminal:
uvicorn app.web:app --reload --port 8000
```

## Important notes
- This is a functional starter, not a claim that every feature in a large A–Z bot is already implemented. Anti-nuke, tickets, advanced role panels, economy and audit-log automation are not included yet.
- Dashboard writes are persisted in PostgreSQL and read by the bot on demand. Dashboard polling refreshes the UI; it is not a WebSocket push implementation.
- The OAuth2 callback checks Discord login and the selected server's permissions. Keep secrets private and configure a strong `SESSION_SECRET`.
- Railway deployments and database connections must be configured in your own account. This archive does not deploy itself.


## Music (Lavalink v4 + Wavelink)

The bot includes music commands powered by Wavelink and requires a separate Lavalink v4 service. Configure these variables on the **bot service**:

- `LAVALINK_HOST`: the Lavalink service hostname reachable from the bot (Railway private domain is preferred when available).
- `LAVALINK_PORT`: the Lavalink service port, usually `2333` unless your deployment uses another port.
- `LAVALINK_PASSWORD`: exactly the password configured in Lavalink's `application.yml`.

Music commands: `/play` (or `!play`), `/skip`, `/pause`, `/resume`, `/stop`, `/queue`, `/nowplaying`, and `/volume`. The bot must have Connect and Speak permissions. Users need to join a voice channel before using `/play`.

This integration does not itself deploy Lavalink, and music-source availability depends on the Lavalink plugins/source configuration. Spotify metadata/API credentials alone do not provide playback. The app should be tested after deployment with a reachable Lavalink v4 node.

### Deploying the Lavalink service from this repository

The `lavalink/` folder includes a Dockerfile and minimal Lavalink v4 config. Create a **second Railway service** from the same GitHub repository and set its **Root Directory** to `/lavalink` (or deploy that folder as its own repository). Add a variable named `LAVALINK_SERVER_PASSWORD` with a strong password. The bot service must use the same value as `LAVALINK_PASSWORD`. Set `LAVALINK_HOST` to the Lavalink service's Railway private domain and `LAVALINK_PORT` to the port the service listens on. If you configure public TCP networking instead, use the actual assigned host and port. Do not assume the public port is 2333.

The included Lavalink config deliberately disables the built-in YouTube source because source support changes over time and often requires a compatible plugin. SoundCloud, Bandcamp, Twitch, Vimeo and HTTP sources are enabled; actual results depend on source availability and network access. Spotify playback requires additional plugin setup such as LavaSrc and its configuration; it is not enabled by this minimal config.
