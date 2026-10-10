import secrets
import httpx
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select
from app.config import (DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, DISCORD_REDIRECT_URI,
                        SESSION_SECRET, DASHBOARD_BASE_URL)
from app.db import init_db, SessionLocal, GuildConfig, get_guild_config

app = FastAPI(title="Fuegos Dashboard")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax", https_only=DASHBOARD_BASE_URL.startswith("https://"))
templates = Jinja2Templates(directory="templates")
API = "https://discord.com/api/v10"

@app.on_event("startup")
async def startup():
    await init_db()

@app.get("/health")
async def health():
    return {"ok": True, "service": "fuegos-dashboard"}

def current_user(request: Request):
    return request.session.get("user")

async def discord_get(path: str, token: str):
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(API + path, headers={"Authorization": f"Bearer {token}"})
    if response.status_code >= 400:
        raise HTTPException(status_code=401, detail="Discord authorization expired. Please log in again.")
    return response.json()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = current_user(request)
    if not user:
        return templates.TemplateResponse("login.html", {"request": request})
    guilds = request.session.get("guilds", [])
    selected = request.session.get("selected_guild")
    cfg = None
    if selected and any(str(g["id"]) == str(selected) for g in guilds):
        async with SessionLocal() as session:
            cfg = await get_guild_config(session, int(selected))
            cfg = {"guild_id": cfg.guild_id, "prefix": cfg.prefix,
                   "welcome_enabled": cfg.welcome_enabled,
                   "welcome_channel_id": cfg.welcome_channel_id,
                   "welcome_message": cfg.welcome_message}
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user, "guilds": guilds,
        "selected": str(selected) if selected else None, "cfg": cfg,
    })

@app.get("/login")
async def login(request: Request):
    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state
    url = (f"https://discord.com/oauth2/authorize?client_id={DISCORD_CLIENT_ID}"
           f"&response_type=code&redirect_uri={httpx.QueryParams({'redirect_uri': DISCORD_REDIRECT_URI})['redirect_uri']}"
           f"&scope=identify%20guilds&state={state}")
    return RedirectResponse(url)

@app.get("/auth/callback")
async def callback(request: Request, code: str = "", state: str = ""):
    if not code or not state or not secrets.compare_digest(state, request.session.get("oauth_state", "")):
        raise HTTPException(status_code=400, detail="Invalid OAuth state. Please try logging in again.")
    async with httpx.AsyncClient(timeout=20) as client:
        token_response = await client.post("https://discord.com/api/oauth2/token", data={
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": DISCORD_REDIRECT_URI,
        }, headers={"Content-Type": "application/x-www-form-urlencoded"})
        if token_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Discord OAuth exchange failed. Check client settings.")
        token_data = token_response.json()
        headers = {"Authorization": f"Bearer {token_data['access_token']}"}
        user_resp = await client.get(API + "/users/@me", headers=headers)
        guild_resp = await client.get(API + "/users/@me/guilds", headers=headers)
    if user_resp.status_code != 200 or guild_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Unable to load Discord account.")
    user = user_resp.json()
    # Only servers with Manage Guild or Administrator are selectable.
    manageable = []
    for guild in guild_resp.json():
        try:
            perms = int(guild.get("permissions", "0"))
        except (ValueError, TypeError):
            perms = 0
        if perms & 0x20 or perms & 0x8:
            manageable.append({"id": str(guild["id"]), "name": guild["name"],
                               "icon": guild.get("icon"), "owner": guild.get("owner", False)})
    request.session.clear()
    request.session["user"] = {"id": user["id"], "username": user["username"],
                               "avatar": user.get("avatar")}
    request.session["access_token"] = token_data["access_token"]
    request.session["guilds"] = manageable
    request.session["oauth_state"] = None
    if manageable:
        request.session["selected_guild"] = manageable[0]["id"]
    return RedirectResponse("/", status_code=303)

@app.post("/select-guild")
async def select_guild(request: Request, guild_id: str = Form(...)):
    if not current_user(request):
        return RedirectResponse("/login", status_code=303)
    allowed = {str(g["id"]) for g in request.session.get("guilds", [])}
    if guild_id not in allowed:
        raise HTTPException(status_code=403, detail="You do not have permission to manage that server.")
    request.session["selected_guild"] = guild_id
    return RedirectResponse("/", status_code=303)

@app.post("/settings")
async def update_settings(request: Request,
                          prefix: str = Form("!"),
                          welcome_enabled: str | None = Form(None),
                          welcome_channel_id: str = Form(""),
                          welcome_message: str = Form("Welcome {user} to {server}!")):
    user = current_user(request)
    guild_id = request.session.get("selected_guild")
    allowed = {str(g["id"]) for g in request.session.get("guilds", [])} if user else set()
    if not user or not guild_id or str(guild_id) not in allowed:
        raise HTTPException(status_code=403, detail="Log in and select a server you can manage.")
    prefix = prefix.strip()
    if not 1 <= len(prefix) <= 4 or any(c.isspace() for c in prefix):
        raise HTTPException(status_code=400, detail="Prefix must be 1–4 non-space characters.")
    channel_id = None
    if welcome_channel_id.strip():
        if not welcome_channel_id.strip().isdigit():
            raise HTTPException(status_code=400, detail="Channel ID must be numeric.")
        channel_id = int(welcome_channel_id.strip())
    if len(welcome_message) > 1800:
        raise HTTPException(status_code=400, detail="Welcome message must be under 1800 characters.")
    async with SessionLocal() as session:
        cfg = await get_guild_config(session, int(guild_id))
        cfg.prefix = prefix
        cfg.welcome_enabled = welcome_enabled == "on"
        cfg.welcome_channel_id = channel_id
        cfg.welcome_message = welcome_message
        await session.commit()
    return RedirectResponse("/", status_code=303)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)

@app.get("/api/status")
async def status(request: Request):
    if not current_user(request):
        raise HTTPException(status_code=401, detail="Login required")
    guild_id = request.session.get("selected_guild")
    if not guild_id:
        return {"selected_guild": None}
    async with SessionLocal() as session:
        cfg = await get_guild_config(session, int(guild_id))
        return {"selected_guild": str(guild_id), "prefix": cfg.prefix,
                "welcome_enabled": cfg.welcome_enabled,
                "welcome_channel_id": cfg.welcome_channel_id,
                "welcome_message": cfg.welcome_message,
                "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None}
