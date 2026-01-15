from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any
import os
import json
import sqlite3
import time
import secrets
import hmac
import hashlib
import threading
import httpx
from jose import jwt
from urllib.parse import urlencode, urlparse

BASE_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(BASE_DIR, "configs_folder", "setings.json")
DB_PATH = os.path.join(BASE_DIR, "bot_state.db")

# Load config
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    _cfg = json.load(f)

CLIENT_ID = _cfg.get("APP_ID")
CLIENT_SECRET = _cfg.get("DISCORD_SECRET")
FRONTEND_URL = _cfg.get("FRONTEND_URL") or "https://pollpi.netlify.app"
# The callback the Discord app must be configured to use
REDIRECT_URI = _cfg.get("OAUTH_REDIRECT_URI") or f"https://bot-hosting.net/auth/discord/callback"
SESSION_SECRET = os.getenv("SESSION_SECRET") or _cfg.get("DISCORD_SECRET")

# Token settings
JWT_ALG = "HS256"
JWT_EXP = 900  # 15 minutes
REFRESH_EXP = 7 * 24 * 3600  # 7 days

# Simple in-memory rate limiter (per user_id or per IP) - not shared across processes
_rate_limits: dict = {}

def _rate_allow(key: str, limit: int, per: int) -> bool:
    now = int(time.time())
    window = now - (now % per)
    rec = _rate_limits.get((key, window), 0)
    if rec >= limit:
        return False
    _rate_limits[(key, window)] = rec + 1
    # cleanup old windows lazily
    if len(_rate_limits) > 10000:
        keys = list(_rate_limits.keys())
        for k in keys:
            if k[1] < window - (per * 5):
                _rate_limits.pop(k, None)
    return True

app = FastAPI(title="pollpi auth API")

# CORS — allow frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"]
)

# DB helpers
def _get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def _init_db():
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS oauth_state (
            state TEXT PRIMARY KEY,
            return_to TEXT,
            created INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            refresh_token TEXT PRIMARY KEY,
            user_id INTEGER,
            allowed_guilds TEXT,
            refresh_expires INTEGER,
            csrf TEXT
        )
        """
    )
    # store guild configs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS guild_configs (
            guild_id INTEGER PRIMARY KEY,
            cfg TEXT
        )
    """)
    # store active tunnels (public_url, secret, created)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tunnels (
            public_url TEXT,
            secret TEXT,
            created INTEGER
        )
    """)
    conn.commit()
    conn.close()

_init_db()

# Bot instance will be injected from bot.py
BOT = None


def set_bot(bot):
    global BOT
    BOT = bot


# Utilities

def generate_state() -> str:
    return secrets.token_urlsafe(32)


def create_jwt(payload: Dict[str, Any]) -> str:
    claims = payload.copy()
    claims["exp"] = int(time.time()) + JWT_EXP
    token = jwt.encode(claims, SESSION_SECRET, algorithm=JWT_ALG)
    return token


def decode_jwt(token: str) -> Dict[str, Any]:
    try:
        data = jwt.decode(token, SESSION_SECRET, algorithms=[JWT_ALG])
        return data
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# Security helpers: require TLS and verify Origin/Referer matches FRONTEND_URL when present
def _origin_base_from_header(h: Optional[str]) -> Optional[str]:
    if not h:
        return None
    try:
        p = urlparse(h)
        if not p.scheme or not p.netloc:
            return None
        return f"{p.scheme}://{p.netloc}"
    except Exception:
        return None


def _get_latest_tunnel_secret() -> Optional[str]:
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT secret FROM tunnels ORDER BY created DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return row[0]
    except Exception:
        return None


def _require_https_and_origin(request: Request):
    # Enforce HTTPS (honor X-Forwarded-Proto when present) and check Origin/Referer matches FRONTEND_URL if provided
    proto = request.headers.get('x-forwarded-proto') or request.url.scheme
    if proto != 'https':
        # allow when tunneled via ngrok (ngrok presents https externally) — but keep check for tunnel secret header
        secret = request.headers.get('X-TUNNEL-SECRET')
        latest = _get_latest_tunnel_secret()
        if not secret or (latest and secret != latest):
            raise HTTPException(status_code=403, detail='Insecure connection — use HTTPS')
    origin = request.headers.get('origin') or request.headers.get('referer')
    origin_base = _origin_base_from_header(origin) if origin else None
    if origin_base and origin_base != FRONTEND_URL:
        # allow when valid tunnel secret provided
        secret = request.headers.get('X-TUNNEL-SECRET')
        latest = _get_latest_tunnel_secret()
        if not secret or (latest and secret != latest):
            raise HTTPException(status_code=403, detail='Invalid request origin')


# OAuth start (legacy; server-generated redirect)
@app.get("/auth/discord/start")
async def auth_start(return_to: Optional[str] = None, request: Request = None):
    # Security: require HTTPS and validate origin when present
    _require_https_and_origin(request)

    state = generate_state()
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO oauth_state(state, return_to, created) VALUES (?, ?, ?)", (state, return_to or "", int(time.time())))
    conn.commit()
    conn.close()

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "identify guilds",
        "state": state,
        "prompt": "consent",
    }
    url = f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"
    return RedirectResponse(url)


# New endpoint: request a server-generated state (recommended for client-side direct OAuth)
@app.get('/auth/discord/state')
async def auth_state(request: Request):
    """Return a server-generated state token (stored in DB) for the client to use in the OAuth redirect."""
    import logging
    logger = logging.getLogger('discord_bot.web')
    # Security check: require HTTPS and validate Origin/Referer matches FRONTEND_URL when present
    _require_https_and_origin(request)

    state = generate_state()
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("INSERT INTO oauth_state(state, return_to, created) VALUES (?, ?, ?)", (state, '', int(time.time())))
        conn.commit()
        conn.close()
        ip = request.client.host if request.client else 'unknown'
        logger.info('issued oauth state to %s: %s', ip, state)
        return JSONResponse({'state': state})
    except Exception as e:
        logger.exception('failed to create oauth state')
        raise HTTPException(status_code=500, detail='failed to create state')


# OAuth callback
@app.get("/auth/discord/callback")
async def auth_callback(code: Optional[str] = None, state: Optional[str] = None, request: Request = None):
    # Security: require HTTPS; Origin/Referer will be validated when present
    _require_https_and_origin(request)

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT return_to, created FROM oauth_state WHERE state = ?", (state,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="Invalid state")
    return_to, created = row[0], row[1]
    # state valid for 5 minutes
    if time.time() - created > 300:
        cur.execute("DELETE FROM oauth_state WHERE state = ?", (state,))
        conn.commit()
        conn.close()
        raise HTTPException(status_code=400, detail="State expired")
    cur.execute("DELETE FROM oauth_state WHERE state = ?", (state,))
    conn.commit()
    conn.close()

    # Exchange code
    async with httpx.AsyncClient() as client:
        data = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        r = await client.post("https://discord.com/api/oauth2/token", data=data, headers=headers, timeout=10)
        if r.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Token exchange failed: {r.text}")
        token_data = r.json()

        # Get user
        r = await client.get("https://discord.com/api/users/@me", headers={"Authorization": f"Bearer {token_data['access_token']}"}, timeout=10)
        if r.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch user")
        user = r.json()

        # Get guilds
        r = await client.get("https://discord.com/api/users/@me/guilds", headers={"Authorization": f"Bearer {token_data['access_token']}"}, timeout=10)
        if r.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch guilds")
        guilds = r.json()  # list of guilds with 'id', 'name', 'permissions'

    user_id = int(user.get("id"))

    # Filter guilds: keep guilds where user has ADMINISTRATOR (0x8) or MANAGE_GUILD (0x20), and bot is present OR user has HOST role
    allowed = []
    from .services_folder import hlpr_perms_manager
    from .services_folder.hlpr_perms_manager import PermRole

    user_has_host = hlpr_perms_manager.has_perm(user_id, PermRole.HOST)
    bot_guild_ids = set(g.id for g in (BOT.guilds if BOT else []))

    for g in guilds:
        try:
            perms = int(g.get("permissions", 0))
        except Exception:
            perms = 0
        is_admin = bool(perms & 0x8) or bool(perms & 0x20)
        gid = int(g.get("id"))
        # Include only guilds where bot is present; host or admin are acceptable
        if gid in bot_guild_ids and (user_has_host or is_admin):
            allowed.append({"id": gid, "name": g.get("name")})

    # Create session: access JWT (short) + refresh token (long-lived)
    csrf_token = secrets.token_urlsafe(16)
    refresh_token = secrets.token_urlsafe(48)
    refresh_expires = int(time.time()) + REFRESH_EXP

    jwt_payload = {"user_id": user_id, "allowed_guilds": [g["id"] for g in allowed], "csrf": csrf_token}
    access_token = create_jwt(jwt_payload)

    # Save refresh session in DB
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO sessions(refresh_token, user_id, allowed_guilds, refresh_expires, csrf) VALUES (?, ?, ?, ?, ?)", (refresh_token, user_id, json.dumps([g["id"] for g in allowed]), refresh_expires, csrf_token))
    conn.commit()
    conn.close()

    # Return small HTML that posts message to opener (safer than putting token in URL) and set HttpOnly refresh cookie
    html = f"""
    <html>
      <body>
        <script>
          (function() {{
            const access = "{access_token}";
            const csrf = "{csrf_token}";
            try {{
              window.opener.postMessage({{type: 'oauth', access_token: access, csrf}}, {json.dumps(FRONTEND_URL)});
            }} catch (e) {{ console.error(e); }}
            // fallback redirect
            window.location = {json.dumps(FRONTEND_URL)};
          }})();
        </script>
        Ок, можно закрыть это окно.
      </body>
    </html>
    """
    resp = HTMLResponse(content=html)
    # Set secure, HttpOnly refresh cookie for backend domain
    resp.set_cookie("pollpi_refresh", refresh_token, httponly=True, secure=True, samesite="Lax", max_age=REFRESH_EXP, path="/")
    return resp


# New endpoint: exchange code posted from frontend callback (so initial OAuth redirect does not need to hit bot-hosting.net directly)
@app.post('/auth/discord/exchange')
async def auth_exchange(item: Dict[str, Any], request: Request):
    code = item.get('code')
    state = item.get('state')
    if not code or not state:
        raise HTTPException(status_code=400, detail='missing code or state')

    # Security check: require HTTPS and validate Origin/Referer matches FRONTEND_URL when present
    _require_https_and_origin(request)

    # validate state exists and is recent
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute('SELECT created FROM oauth_state WHERE state = ?', (state,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=400, detail='invalid or unknown state')
    created = int(row[0])
    if time.time() - created > 300:
        cur.execute('DELETE FROM oauth_state WHERE state = ?', (state,))
        conn.commit()
        conn.close()
        raise HTTPException(status_code=400, detail='state expired')
    # state is good — delete it (single use)
    cur.execute('DELETE FROM oauth_state WHERE state = ?', (state,))
    conn.commit()
    conn.close()

    # log attempt
    import logging
    logger = logging.getLogger('discord_bot.web')
    ip = request.client.host if request.client else 'unknown'
    logger.info('auth_exchange attempt from %s for state=%s', ip, state)

    # exchange code for token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            'https://discord.com/api/oauth2/token',
            data={
                'client_id': CLIENT_ID,
                'client_secret': CLIENT_SECRET,
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': REDIRECT_URI,
            },
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=10,
        )
        if token_resp.status_code != 200:
            text = token_resp.text
            logger.warning('discord token exchange failed (%s): %s', token_resp.status_code, text[:1000])
            raise HTTPException(status_code=400, detail=f'discord token exchange failed: {token_resp.status_code}')
        tdata = token_resp.json()
        acc = tdata.get('access_token')
        if not acc:
            logger.warning('discord token exchange missing access token: %s', tdata)
            raise HTTPException(status_code=500, detail='no access token')

        user_r = await client.get('https://discord.com/api/users/@me', headers={'Authorization': f'Bearer {acc}'}, timeout=10)
        if user_r.status_code != 200:
            logger.warning('failed to fetch user: %s', user_r.text[:500])
            raise HTTPException(status_code=400, detail='Failed to fetch user')
        user_json = user_r.json()
        user_id = int(user_json.get('id'))

        guilds_r = await client.get('https://discord.com/api/users/@me/guilds', headers={'Authorization': f'Bearer {acc}'}, timeout=10)
        if guilds_r.status_code != 200:
            logger.warning('failed to fetch guilds: %s', guilds_r.text[:1000])
            raise HTTPException(status_code=400, detail='Failed to fetch guilds')
        guilds = guilds_r.json()

    # compute allowed guilds
    allowed = []
    from .services_folder import hlpr_perms_manager
    from .services_folder.hlpr_perms_manager import PermRole

    user_has_host = hlpr_perms_manager.has_perm(user_id, PermRole.HOST)
    bot_guild_ids = set(g.id for g in (BOT.guilds if BOT else []))

    for g in guilds:
        try:
            perms = int(g.get('permissions', 0))
        except Exception:
            perms = 0
        is_admin = bool(perms & 0x8) or bool(perms & 0x20)
        gid = int(g.get('id'))
        if gid in bot_guild_ids and (user_has_host or is_admin):
            allowed.append({'id': gid, 'name': g.get('name')})

    csrf = secrets.token_urlsafe(16)
    refresh_token = secrets.token_urlsafe(48)
    refresh_expires = int(time.time()) + REFRESH_EXP

    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO sessions(refresh_token, user_id, allowed_guilds, refresh_expires, csrf) VALUES (?, ?, ?, ?, ?)", (refresh_token, user_id, json.dumps([g['id'] for g in allowed]), refresh_expires, csrf))
    conn.commit()
    conn.close()

    access_jwt = create_jwt({'user_id': user_id, 'allowed_guilds': [g['id'] for g in allowed], 'csrf': csrf})
    response = JSONResponse({'access_token': access_jwt, 'csrf': csrf})
    response.set_cookie('pollpi_refresh', refresh_token, httponly=True, secure=True, samesite='Lax', max_age=REFRESH_EXP, path='/')
    return response

# Dependency
async def get_current_user(request: Request):
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = auth.split(" ", 1)[1]
    data = decode_jwt(token)
    return data


@app.get("/api/me")
async def api_me(user=Depends(get_current_user)):
    # return basic info
    return {"user_id": user.get("user_id"), "allowed_guilds": user.get("allowed_guilds", [])}


@app.get("/api/guilds")
async def api_guilds(user=Depends(get_current_user)):
    # Return allowed guilds and presence of bot
    allowed = user.get("allowed_guilds", [])
    res = []
    bot_guild_ids = set(g.id for g in (BOT.guilds if BOT else []))
    for gid in allowed:
        res.append({"id": gid, "bot_present": gid in bot_guild_ids})
    return res


@app.get("/api/guilds/{guild_id}/config")
async def get_guild_config(guild_id: int, user=Depends(get_current_user)):
    user_id = user.get("user_id")
    allowed = user.get("allowed_guilds", [])
    from .services_folder import hlpr_perms_manager
    from .services_folder.hlpr_perms_manager import PermRole

    is_host = hlpr_perms_manager.has_perm(user_id, PermRole.HOST)
    is_admin = guild_id in allowed
    if not (is_host or is_admin):
        raise HTTPException(status_code=403, detail="Forbidden")

    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS guild_configs (guild_id INTEGER PRIMARY KEY, cfg TEXT)")
    cur.execute("SELECT cfg FROM guild_configs WHERE guild_id = ?", (guild_id,))
    row = cur.fetchone()
    if not row:
        return {"guild_id": guild_id, "config": {}}
    return {"guild_id": guild_id, "config": json.loads(row[0])}


@app.post("/api/guilds/{guild_id}/config")
async def post_guild_config(guild_id: int, body: Dict[str, Any], request: Request, user=Depends(get_current_user)):
    # Security check: require HTTPS and validate Origin/Referer matches FRONTEND_URL when present
    _require_https_and_origin(request)

    # Rate limit per user
    uid = user.get("user_id")
    if not _rate_allow(f"savecfg:{uid}", limit=10, per=60):
        raise HTTPException(status_code=429, detail="Too many requests")

    user_id = user.get("user_id")
    allowed = user.get("allowed_guilds", [])
    from .services_folder import hlpr_perms_manager
    from .services_folder.hlpr_perms_manager import PermRole

    is_host = hlpr_perms_manager.has_perm(user_id, PermRole.HOST)
    is_admin = guild_id in allowed
    if not (is_host or is_admin):
        raise HTTPException(status_code=403, detail="Forbidden")

    # CSRF check (require X-CSRF-Token matching token from JWT payload)
    csrf_header = request.headers.get("X-CSRF-Token")
    if not csrf_header or csrf_header != user.get("csrf"):
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")

    # Save config
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS guild_configs (guild_id INTEGER PRIMARY KEY, cfg TEXT)")
    cur.execute("INSERT OR REPLACE INTO guild_configs(guild_id, cfg) VALUES (?, ?)", (guild_id, json.dumps(body)))
    conn.commit()
    conn.close()

    # Notify running bot (if in same process) so it can apply config immediately
    try:
        import logging
        logger = logging.getLogger('discord_bot.web')
        if BOT:
            # Prefer an explicit coroutine on BOT to apply configs
            if hasattr(BOT, 'apply_guild_config') and callable(getattr(BOT, 'apply_guild_config')):
                import asyncio
                asyncio.run_coroutine_threadsafe(BOT.apply_guild_config(guild_id, body), BOT.loop)
                logger.info('Notified bot to apply config for guild %s', guild_id)
            else:
                # fallback: dispatch event the bot can listen for
                try:
                    BOT.dispatch('guild_config_updated', guild_id, body)
                    logger.info('Dispatched guild_config_updated for guild %s', guild_id)
                except Exception:
                    logger.info('Bot present but no handler for applying config')
    except Exception:
        pass

    return {"status": "ok"}


# Admin health check
@app.get("/health")
async def health():
    return {"status": "ok"}


# Session helpers
def _get_session_by_refresh(refresh_token: str):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT refresh_token, user_id, allowed_guilds, refresh_expires, csrf FROM sessions WHERE refresh_token = ?", (refresh_token,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "refresh_token": row[0],
        "user_id": int(row[1]),
        "allowed_guilds": json.loads(row[2]) if row[2] else [],
        "refresh_expires": int(row[3]),
        "csrf": row[4]
    }


@app.post("/auth/refresh")
async def auth_refresh(request: Request):
    # Security check: require HTTPS and validate Origin/Referer matches FRONTEND_URL when present
    _require_https_and_origin(request)

    # Rate limit by IP
    ip = request.client.host if request.client else "unknown"
    if not _rate_allow(f"refresh:{ip}", limit=10, per=60):
        raise HTTPException(status_code=429, detail="Too many requests")

    refresh_token = request.cookies.get("pollpi_refresh")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh cookie")
    session = _get_session_by_refresh(refresh_token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    if session["refresh_expires"] < int(time.time()):
        # delete session
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE refresh_token = ?", (refresh_token,))
        conn.commit()
        conn.close()
        raise HTTPException(status_code=401, detail="Refresh token expired")

    # CSRF check
    csrf_header = request.headers.get("X-CSRF-Token")
    if not csrf_header or csrf_header != session.get("csrf"):
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")

    # rotate refresh token
    new_refresh = secrets.token_urlsafe(48)
    new_expires = int(time.time()) + REFRESH_EXP
    csrf = session.get("csrf")

    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM sessions WHERE refresh_token = ?", (refresh_token,))
    cur.execute("INSERT INTO sessions(refresh_token, user_id, allowed_guilds, refresh_expires, csrf) VALUES (?, ?, ?, ?, ?)", (new_refresh, session.get("user_id"), json.dumps(session.get("allowed_guilds")), new_expires, csrf))
    conn.commit()
    conn.close()

    jwt_payload = {"user_id": session.get("user_id"), "allowed_guilds": session.get("allowed_guilds"), "csrf": csrf}
    access_token = create_jwt(jwt_payload)

    resp = JSONResponse({"access_token": access_token, "csrf": csrf})
    resp.set_cookie("pollpi_refresh", new_refresh, httponly=True, secure=True, samesite="Lax", max_age=REFRESH_EXP, path="/")
    return resp


@app.post("/auth/logout")
async def auth_logout(request: Request):
    # Security check: require HTTPS and validate Origin/Referer matches FRONTEND_URL when present
    _require_https_and_origin(request)

    refresh_token = request.cookies.get("pollpi_refresh")
    if refresh_token:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE refresh_token = ?", (refresh_token,))
        conn.commit()
        conn.close()
    resp = JSONResponse({"status": "ok"})
    resp.delete_cookie("pollpi_refresh", path="/")
    return resp


# Server runner
def run_server(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn
    # Run using the app object directly so uvicorn does not try to import the package by name
    # (this prevents "No module named 'discord_bot'" when running as a script)
    uvicorn.run(app, host=host, port=port, log_level="info")


def start_server_in_thread(host: str = "0.0.0.0", port: int = 8000):
    t = threading.Thread(target=run_server, args=(host, port), daemon=True)
    t.start()
    return t
