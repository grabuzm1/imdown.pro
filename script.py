import json, os, re, time, hashlib, secrets, threading
from pathlib import Path
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles          # ← добавь этот импорт
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import uvicorn

app = FastAPI()
BASE = Path(__file__).parent          # ← BASE определяется ЗДЕСЬ
DB = BASE / "users.json"
TPL = BASE / "templates"
STATIC = BASE / "static"              # ← добавь эту строку
_lock = threading.Lock()
DAILY_COOLDOWN = 24 * 60 * 60
OFFLINE_CAP = 8 * 60 * 60

# ← ВОТ ЗДЕСЬ app.mount (после BASE, DB, TPL, STATIC)
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

REBIRTH_BASE = 1e15        # порог первого перерождения
REBIRTH_STEP = 5           # каждый следующий порог × 5

SECRET_KEY = "imdown_super_secret_change_me_2026"
SESSION_MAX_AGE = 60 * 60 * 24 * 30
COOKIE_NAME = "imdown_session"

_signer = URLSafeTimedSerializer(SECRET_KEY, salt="session")


def make_session(name: str, trusted=None) -> str:
    return _signer.dumps({"u": name, "t": trusted or []})


def read_session(token: str):
    try:
        return _signer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def current_user(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None, []
    data = read_session(token)
    if not data:
        return None, []
    return data.get("u"), data.get("t", [])


def hash_pass(password, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}${h.hex()}"


def verify_pass(password, stored):
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return hash_pass(password, salt) == stored


def load():
    if not DB.exists():
        return {}
    try:
        with open(DB, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save(data):
    with _lock:
        tmp = str(DB) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DB)


def read_tpl(name):
    with open(TPL / name, "r", encoding="utf-8") as f:
        return f.read()


def top_right_for(request):
    user, _ = current_user(request)
    if user:
        data = load()
        if user in data:
            return (
                '<button type="button" class="user-chip" id="openAccount">'
                + user + '</button>'
            )
    return '<a href="/login" class="nav-plain">Войти</a>'


THEMES = [
    {"id": "midnight", "name": "Midnight"},
    {"id": "sunset", "name": "Sunset"},
]

# ============ ЮНИТЫ ============
SHOP = [
    {"id": "clicker",  "icon": "👆", "name": "Палец-робот",       "desc": "+0.2/с",    "base": 15,                     "cps": 0.2,            "mult": 1.30},
    {"id": "farm",     "icon": "🌾", "name": "Ферма",             "desc": "+1.5/с",    "base": 100,                    "cps": 1.5,            "mult": 1.35},
    {"id": "rig",      "icon": "⛏️", "name": "Шахта",             "desc": "+8/с",      "base": 500,                    "cps": 8.0,            "mult": 1.40},
    {"id": "factory",  "icon": "🏭", "name": "Завод",             "desc": "+50/с",     "base": 3000,                   "cps": 50.0,           "mult": 1.45},
    {"id": "lab",      "icon": "🔬", "name": "Лаборатория",       "desc": "+300/с",    "base": 15000,                  "cps": 300.0,          "mult": 1.50},
    {"id": "reactor",  "icon": "☢️", "name": "Реактор",           "desc": "+2K/с",     "base": 90000,                  "cps": 2000.0,         "mult": 1.55},
    {"id": "station",  "icon": "🛰️", "name": "Космостанция",      "desc": "+12K/с",    "base": 500000,                 "cps": 12000.0,        "mult": 1.60},
    {"id": "colony",   "icon": "🌕", "name": "Лунная база",       "desc": "+80K/с",    "base": 3000000,                "cps": 80000.0,        "mult": 1.65},
    {"id": "shipyard", "icon": "🚀", "name": "Верфь",             "desc": "+500K/с",   "base": 20000000,               "cps": 500000.0,       "mult": 1.70},
    {"id": "dyson",    "icon": "🌐", "name": "Сфера Дайсона",     "desc": "+3M/с",     "base": 150000000,              "cps": 3000000.0,      "mult": 1.75},
    {"id": "galaxy",   "icon": "🌌", "name": "Галактика",         "desc": "+20M/с",    "base": 1000000000,             "cps": 20000000.0,     "mult": 1.80},
    {"id": "universe", "icon": "✨", "name": "Вселенная",         "desc": "+150M/с",   "base": 8000000000,             "cps": 150000000.0,    "mult": 1.85},
    {"id": "time",     "icon": "⏳", "name": "Машина времени",    "desc": "+1B/с",     "base": 60000000000,            "cps": 1000000000.0,   "mult": 1.90},
    {"id": "god",      "icon": "👁️", "name": "Око Бога",          "desc": "+8B/с",     "base": 500000000000,           "cps": 8000000000.0,   "mult": 1.95},
    {"id": "eternal",  "icon": "♾️", "name": "Вечность",          "desc": "+75B/с",    "base": 5000000000000,          "cps": 75000000000.0,  "mult": 2.00},
    {"id": "cosmos",   "icon": "🌠", "name": "Космическая сеть",  "desc": "+900B/с",   "base": 500000000000000,        "cps": 900000000000.0, "mult": 2.05},
    {"id": "multiv",   "icon": "🌀", "name": "Порталы",           "desc": "+15T/с",    "base": 60000000000000000,      "cps": 15000000000000.0,"mult": 2.10},
    {"id": "omni",     "icon": "🔮", "name": "Кристалл силы",     "desc": "+300T/с",   "base": 1e22,                   "cps": 3e14,           "mult": 2.15},
    {"id": "infinity", "icon": "💎", "name": "Ядро мира",         "desc": "+8Qa/с",    "base": 1e26,                   "cps": 8e15,           "mult": 2.20},
    {"id": "transc",   "icon": "👑", "name": "Трон творца",       "desc": "+250Qa/с",  "base": 1e30,                   "cps": 2.5e17,         "mult": 2.25},
]

# ============ КОЛЛЕКЦИЯ ============
COLLECTION = [
    {"id": "villa",     "icon": "🏠", "name": "Вилла",         "desc": "+5% к клику",  "base": 5000,              "bonus": 0.05, "cps_bonus": 0.0},
    {"id": "car",       "icon": "🚗", "name": "Машина",        "desc": "+8% к клику",  "base": 25000,             "bonus": 0.08, "cps_bonus": 0.0},
    {"id": "yacht",     "icon": "🛥️", "name": "Яхта",          "desc": "+12% к клику", "base": 150000,            "bonus": 0.12, "cps_bonus": 0.0},
    {"id": "jet",       "icon": "✈️", "name": "Джет",          "desc": "+20% к клику", "base": 1200000,           "bonus": 0.20, "cps_bonus": 0.02},
    {"id": "island",    "icon": "🏝️", "name": "Остров",        "desc": "+35% к клику", "base": 10000000,          "bonus": 0.35, "cps_bonus": 0.03},
    {"id": "rocket",    "icon": "🚀", "name": "Ракета",        "desc": "+60% к клику", "base": 150000000,         "bonus": 0.60, "cps_bonus": 0.05},
    {"id": "moonbase",  "icon": "🌕", "name": "Лунная база",   "desc": "+100% к клику","base": 2000000000,        "bonus": 1.00, "cps_bonus": 0.08},
    {"id": "dyson2",    "icon": "🌐", "name": "Сфера Дайсона", "desc": "+200% к клику","base": 50000000000,       "bonus": 2.00, "cps_bonus": 0.15},
    {"id": "galaxy2",   "icon": "🌌", "name": "Галактика",     "desc": "+500% к клику","base": 1e15,              "bonus": 5.00, "cps_bonus": 0.25},
    {"id": "crown",     "icon": "👑", "name": "Корона",        "desc": "+1000% к клику","base": 1e20,             "bonus": 10.0, "cps_bonus": 0.50},
]


# ============ ПЕРЕРОЖДЕНИЕ ============
def rebirth_threshold(rebirths):
    return REBIRTH_BASE * (REBIRTH_STEP ** rebirths)


def rebirth_bonus(rebirths):
    """Формула Б: квадрат."""
    return float(rebirths) * float(rebirths)


# ============ ЮЗЕР ============
def default_user(pw_hash):
    now = int(time.time())
    u = {
        "pass": pw_hash,
        "score": 0.0,
        "power": 1.0,
        "cps": 0.0,
        "lvl": 1,
        "next": 100,
        "total_earned": 0.0,
        "total_earned_all": 0.0,
        "best_score": 0.0,
        "rebirths": 0,
        "theme": "sunset",
        "last_seen": now,
        "game_session": "",
        "daily_last": 0,
        "daily_streak": 0,
        "daily_bonus": 0,
    }
    for i in SHOP:
        u[f"c_{i['id']}"] = i["base"]
        u[f"n_{i['id']}"] = 0
    for i in COLLECTION:
        u[f"o_{i['id']}"] = 0
    return u


def migrate(u):
    changed = False
    base_defaults = {
        "score": 0.0, "power": 1.0, "cps": 0.0,
        "lvl": 1, "next": 100, "total_earned": 0.0,
        "total_earned_all": 0.0, "best_score": 0.0, "rebirths": 0,
        "theme": "sunset",
        "last_seen": int(time.time()),
        "game_session": "",
        "daily_last": 0, "daily_streak": 0, "daily_bonus": 0,
    }
    for k, v in base_defaults.items():
        if k not in u:
            u[k] = v
            changed = True

    if u.get("total_earned_all", 0) == 0 and u.get("total_earned", 0) > 0:
        u["total_earned_all"] = u["total_earned"]
        changed = True

    for i in SHOP:
        ck = f"c_{i['id']}"
        nk = f"n_{i['id']}"
        if ck not in u:
            u[ck] = i["base"]
            changed = True
        if nk not in u:
            u[nk] = 0
            changed = True

    for i in COLLECTION:
        ok = f"o_{i['id']}"
        if ok not in u:
            u[ok] = 0
            changed = True

    return u


# ============ МНОЖИТЕЛИ ============
def click_mult(u):
    total = 0.0
    for i in COLLECTION:
        if u.get(f"o_{i['id']}"):
            total += i.get("bonus", 0.0)
    return total


def cps_mult(u):
    total = 0.0
    for i in COLLECTION:
        if u.get(f"o_{i['id']}"):
            total += i.get("cps_bonus", 0.0)
    return total


# ============ ОФФЛАЙН ============
def offline_gain(u):
    last = u.get("last_seen", 0)
    if not last:
        return 0.0
    elapsed = int(time.time()) - last
    if elapsed <= 0:
        return 0.0
    if elapsed > OFFLINE_CAP:
        elapsed = OFFLINE_CAP
    return u.get("cps", 0.0) * elapsed


# ============ ЕЖЕДНЕВКА ============
def daily_state(u):
    now = int(time.time())
    last = u.get("daily_last", 0)
    streak = u.get("daily_streak", 0)
    elapsed = now - last if last else DAILY_COOLDOWN
    left = max(0, DAILY_COOLDOWN - elapsed)
    can = (last == 0) or (elapsed >= DAILY_COOLDOWN)

    base_bonus = max(100.0, u.get("cps", 0.0) * 60.0 + u.get("score", 0.0) * 0.05)
    next_streak = streak + 1 if can else streak
    mult = 1.0 + min(next_streak, 7) * 0.1
    bonus = base_bonus * mult
    return can, left, streak, bonus


def claim_daily(u):
    now = int(time.time())
    last = u.get("daily_last", 0)
    elapsed = now - last if last else DAILY_COOLDOWN
    if last and elapsed < DAILY_COOLDOWN:
        return False, 0.0

    streak = u.get("daily_streak", 0)
    if last and elapsed < DAILY_COOLDOWN * 2:
        streak += 1
    else:
        streak = 1

    base_bonus = max(100.0, u.get("cps", 0.0) * 60.0 + u.get("score", 0.0) * 0.05)
    mult = 1.0 + min(streak, 7) * 0.1
    bonus = base_bonus * mult

    u["daily_last"] = now
    u["daily_streak"] = streak
    u["daily_bonus"] = bonus
    u["score"] = u.get("score", 0.0) + bonus
    u["total_earned"] = u.get("total_earned", 0.0) + bonus
    return True, bonus


# ============ ГЛАВНЫЙ САЙТ ============
@app.get("/", response_class=HTMLResponse)
async def site_index(request: Request):
    html = read_tpl("index.html")
    html = html.replace("__TOP_RIGHT__", top_right_for(request))
    return html


@app.get("/projects", response_class=HTMLResponse)
async def site_projects(request: Request):
    html = read_tpl("projects.html")
    html = html.replace("__TOP_RIGHT__", top_right_for(request))
    return html


@app.get("/contact", response_class=HTMLResponse)
async def site_contact(request: Request):
    html = read_tpl("contact.html")
    html = html.replace("__TOP_RIGHT__", top_right_for(request))
    return html


@app.get("/updates", response_class=HTMLResponse)
async def site_updates(request: Request):
    html = read_tpl("updates.html")
    html = html.replace("__TOP_RIGHT__", top_right_for(request))
    return html


@app.get("/preview", response_class=HTMLResponse)
async def game_preview():
    return read_tpl("game_preview.html")


# ============ РЕЙТИНГ ============
@app.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard_page(request: Request):
    data = load()
    players = []
    for name, u in data.items():
        if not isinstance(u, dict):
            continue
        players.append({
            "name": name,
            "rebirths": int(u.get("rebirths", 0)),
            "total_all": float(u.get("total_earned_all", 0.0)),
            "score": float(u.get("score", 0.0)),
            "cps": float(u.get("cps", 0.0)),
        })
    players.sort(key=lambda p: p["total_all"], reverse=True)
    for i, p in enumerate(players):
        p["rank"] = i + 1

    user, _ = current_user(request)
    my_rank = next((p["rank"] for p in players if p["name"] == user), None)

    html = read_tpl("leaderboard.html")
    html = html.replace("__TOP_RIGHT__", top_right_for(request))
    html = html.replace("/*__PLAYERS__*/", json.dumps(players[:100], ensure_ascii=False))
    html = html.replace("__ME__", user or "")
    html = html.replace("__MY_RANK__", str(my_rank) if my_rank else "—")
    return html


# ============ DOWN ID ============
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None, next: str = "/account"):
    user, _ = current_user(request)
    if user:
        data = load()
        if user in data:
            return RedirectResponse(next, status_code=303)
    html = read_tpl("login.html")
    html = html.replace("__ERROR__",
        f'<div class="err">{error}</div>' if error else "")
    html = html.replace("__NEXT__", next)
    return html


@app.post("/login_user")
async def login_user(
    u_login: str = Form(...),
    u_pass: str = Form(...),
    next: str = Form("/account"),
):
    u_login = u_login.strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", u_login):
        return RedirectResponse(
            f"/login?error=Логин:+3-20+символов&next={next}",
            status_code=303)
    if len(u_pass) < 4:
        return RedirectResponse(
            f"/login?error=Пароль+мин.+4+символа&next={next}",
            status_code=303)
    data = load()
    if u_login not in data:
        return RedirectResponse(
            f"/login?error=Аккаунт+не+найден&next={next}",
            status_code=303)
    if not verify_pass(u_pass, data[u_login]["pass"]):
        return RedirectResponse(
            f"/login?error=Неверный+пароль&next={next}",
            status_code=303)
    resp = RedirectResponse(next, status_code=303)
    resp.set_cookie(COOKIE_NAME, make_session(u_login, []),
                    max_age=SESSION_MAX_AGE, httponly=True, samesite="lax")
    return resp


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, error: str = None, next: str = "/account"):
    user, _ = current_user(request)
    if user:
        data = load()
        if user in data:
            return RedirectResponse(next, status_code=303)
    html = read_tpl("register.html")
    html = html.replace("__ERROR__",
        f'<div class="err">{error}</div>' if error else "")
    html = html.replace("__NEXT__", next)
    return html


@app.post("/register_user")
async def register_user(
    u_login: str = Form(...),
    u_pass: str = Form(...),
    u_pass2: str = Form(...),
    next: str = Form("/account"),
):
    u_login = u_login.strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", u_login):
        return RedirectResponse(
            f"/register?error=Логин:+3-20+символов&next={next}",
            status_code=303)
    if len(u_pass) < 4:
        return RedirectResponse(
            f"/register?error=Пароль+мин.+4+символа&next={next}",
            status_code=303)
    if u_pass != u_pass2:
        return RedirectResponse(
            f"/register?error=Пароли+не+совпадают&next={next}",
            status_code=303)
    data = load()
    if u_login in data:
        return RedirectResponse(
            f"/register?error=Логин+уже+занят&next={next}",
            status_code=303)
    data[u_login] = default_user(hash_pass(u_pass))
    save(data)
    resp = RedirectResponse(next, status_code=303)
    resp.set_cookie(COOKIE_NAME, make_session(u_login, []),
                    max_age=SESSION_MAX_AGE, httponly=True, samesite="lax")
    return resp


@app.get("/logout")
async def logout(next: str = "/"):
    resp = RedirectResponse(next, status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp


@app.get("/account", response_class=HTMLResponse)
async def account_page(request: Request, error: str = None, ok: str = None):
    user, _ = current_user(request)
    if not user:
        return RedirectResponse("/login?next=/account", status_code=303)
    data = load()
    if user not in data:
        return RedirectResponse("/login", status_code=303)
    html = read_tpl("account.html")
    html = html.replace("__NAME__", user)
    msg = ""
    if error:
        msg = f'<div class="msg err">{error}</div>'
    elif ok:
        msg = f'<div class="msg ok">{ok}</div>'
    html = html.replace("__MSG__", msg)
    return html


@app.post("/change_login")
async def change_login(
    request: Request,
    current_pass: str = Form(...),
    new_login: str = Form(...),
):
    user, trusted = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    new_login = new_login.strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", new_login):
        return RedirectResponse(
            "/account?error=Новый+логин:+3-20+символов", status_code=303)
    data = load()
    u = data.get(user)
    if not u:
        return RedirectResponse("/login", status_code=303)
    if not verify_pass(current_pass, u["pass"]):
        return RedirectResponse(
            "/account?error=Неверный+текущий+пароль", status_code=303)
    if new_login in data:
        return RedirectResponse(
            "/account?error=Логин+уже+занят", status_code=303)
    data[new_login] = data.pop(user)
    save(data)
    resp = RedirectResponse("/account?ok=Логин+изменён", status_code=303)
    resp.set_cookie(COOKIE_NAME, make_session(new_login, trusted),
                    max_age=SESSION_MAX_AGE, httponly=True, samesite="lax")
    return resp


@app.post("/change_password")
async def change_password(
    request: Request,
    current_pass: str = Form(...),
    new_pass: str = Form(...),
    new_pass2: str = Form(...),
):
    user, _ = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if len(new_pass) < 4:
        return RedirectResponse(
            "/account?error=Новый+пароль+мин.+4", status_code=303)
    if new_pass != new_pass2:
        return RedirectResponse(
            "/account?error=Пароли+не+совпадают", status_code=303)
    data = load()
    u = data.get(user)
    if not u:
        return RedirectResponse("/login", status_code=303)
    if not verify_pass(current_pass, u["pass"]):
        return RedirectResponse(
            "/account?error=Неверный+текущий+пароль", status_code=303)
    u["pass"] = hash_pass(new_pass)
    save(data)
    return RedirectResponse("/account?ok=Пароль+изменён", status_code=303)


# ============ DOWN GAMES ============
@app.get("/games", response_class=HTMLResponse)
async def games_landing(request: Request):
    user, trusted = current_user(request)
    if user:
        data = load()
        if user in data:
            if "downgames" in trusted:
                return RedirectResponse("/downgames", status_code=303)
            return RedirectResponse("/consent?service=downgames", status_code=303)
    return read_tpl("games_landing.html")


@app.get("/consent", response_class=HTMLResponse)
async def consent_page(request: Request, service: str = "downgames"):
    user, trusted = current_user(request)
    if not user:
        return RedirectResponse(f"/login?next=/games", status_code=303)
    data = load()
    if user not in data:
        return RedirectResponse("/login", status_code=303)
    if service in trusted:
        return RedirectResponse("/downgames", status_code=303)
    html = read_tpl("consent.html")
    html = html.replace("__NAME__", user)
    html = html.replace("__SERVICE__", service)
    return html


@app.post("/consent_allow")
async def consent_allow(request: Request, service: str = Form(...)):
    user, trusted = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if service not in trusted:
        trusted.append(service)
    resp = RedirectResponse("/downgames", status_code=303)
    resp.set_cookie(COOKIE_NAME, make_session(user, trusted),
                    max_age=SESSION_MAX_AGE, httponly=True, samesite="lax")
    return resp


@app.post("/consent_deny")
async def consent_deny(request: Request, service: str = Form(...)):
    return RedirectResponse("/", status_code=303)


@app.get("/downgames", response_class=HTMLResponse)
async def downgames(request: Request):
    user, trusted = current_user(request)
    if not user:
        return RedirectResponse("/login?next=/games", status_code=303)
    data = load()
    if user not in data:
        return RedirectResponse("/login?next=/games", status_code=303)
    if "downgames" not in trusted:
        return RedirectResponse("/consent?service=downgames", status_code=303)
    return read_tpl("downgames.html").replace("__NAME__", user)


@app.get("/clickerdown", response_class=HTMLResponse)
async def clickerdown(request: Request):
    user, trusted = current_user(request)
    if not user:
        return RedirectResponse("/login?next=/clickerdown", status_code=303)
    data = load()
    if user not in data:
        return RedirectResponse("/login", status_code=303)
    if "downgames" not in trusted:
        return RedirectResponse("/consent?service=downgames", status_code=303)

    u = migrate(data[user])
    off = offline_gain(u)
    if off > 0:
        u["score"] += off
        u["total_earned"] = u.get("total_earned", 0) + off
        u["total_earned_all"] = u.get("total_earned_all", 0) + off
    u["last_seen"] = int(time.time())
    u["game_session"] = ""
    data[user] = u
    save(data)

    session_id = secrets.token_hex(8)
    rb = int(u.get("rebirths", 0))

    can_claim, left, streak, bonus = daily_state(u)
    state = {
        "name": user, "score": u["score"], "power": u["power"], "cps": u["cps"],
        "lvl": u["lvl"], "next": u["next"],
        "total_earned": u.get("total_earned", u["score"]),
        "total_earned_all": u.get("total_earned_all", 0.0),
        "theme": u["theme"],
        "session_id": session_id,
        "clickMult": click_mult(u),
        "cpsMult": cps_mult(u),
        "offline_gain": off,
        "rebirths": rb,
        "rebirthBonus": rebirth_bonus(rb),
        "rebirthThreshold": rebirth_threshold(rb),
        "prices": {i["id"]: u[f"c_{i['id']}"] for i in SHOP},
        "counts": {i["id"]: u[f"n_{i['id']}"] for i in SHOP},
        "owned":  {i["id"]: u[f"o_{i['id']}"] for i in COLLECTION},
        "daily": {"can": can_claim, "seconds_left": left,
                  "streak": streak, "bonus": bonus},
    }
    html = read_tpl("clickerdown.html")
    html = html.replace("/*__SHOP__*/",       json.dumps(SHOP, ensure_ascii=False))
    html = html.replace("/*__COLLECTION__*/", json.dumps(COLLECTION, ensure_ascii=False))
    html = html.replace("/*__THEMES__*/",     json.dumps(THEMES, ensure_ascii=False))
    html = html.replace("/*__STATE__*/",      json.dumps(state, ensure_ascii=False))
    return html


# ============ ПЕРЕРОЖДЕНИЕ ============
@app.post("/rebirth")
async def do_rebirth(request: Request):
    user, _ = current_user(request)
    if not user:
        return {"ok": False, "reason": "no_user"}
    data = load()
    if user not in data:
        return {"ok": False, "reason": "no_user"}
    u = migrate(data[user])

    rb = int(u.get("rebirths", 0))
    threshold = rebirth_threshold(rb)
    total = float(u.get("total_earned", 0.0))

    if total < threshold:
        return {"ok": False, "reason": "not_enough",
                "threshold": threshold, "have": total}

    # Сброс текущего забега
    u["rebirths"] = rb + 1
    u["score"] = 0.0
    u["power"] = 1.0
    u["cps"] = 0.0
    u["lvl"] = 1
    u["next"] = 100
    u["total_earned"] = 0.0
    u["daily_last"] = 0
    u["daily_streak"] = 0
    u["daily_bonus"] = 0
    for i in SHOP:
        u[f"c_{i['id']}"] = i["base"]
        u[f"n_{i['id']}"] = 0
    for i in COLLECTION:
        u[f"o_{i['id']}"] = 0

    data[user] = u
    save(data)

    new_rb = u["rebirths"]
    return {
        "ok": True,
        "rebirths": new_rb,
        "rebirthBonus": rebirth_bonus(new_rb),
        "rebirthThreshold": rebirth_threshold(new_rb),
    }


@app.post("/daily")
async def claim_daily_route(request: Request):
    user, _ = current_user(request)
    if not user:
        return {"ok": False}
    data = load()
    if user not in data:
        return {"ok": False}
    u = data[user]
    ok, bonus = claim_daily(u)
    if ok:
        u["total_earned_all"] = u.get("total_earned_all", 0) + bonus
        save(data)
        can, left, streak, next_bonus = daily_state(u)
        return {"ok": True, "bonus": bonus, "streak": u["daily_streak"],
                "can": can, "seconds_left": left, "next_bonus": next_bonus,
                "score": u["score"], "total_earned": u.get("total_earned", 0)}
    can, left, streak, next_bonus = daily_state(u)
    return {"ok": False, "can": can, "seconds_left": left,
            "streak": streak, "next_bonus": next_bonus}


@app.post("/save")
async def save_progress(
    request: Request,
    payload: str = Form(...),
    client_time: int = Form(0),
    session_id: str = Form(""),
):
    user, _ = current_user(request)
    if not user:
        return {"ok": False}
    data = load()
    if user not in data:
        return {"ok": False}
    u = data[user]

    saved_session = u.get("game_session", "")
    if session_id:
        if saved_session and saved_session != session_id:
            return {"ok": False, "reason": "other_session"}
        u["game_session"] = session_id

    try:
        s = json.loads(payload)
    except json.JSONDecodeError:
        return {"ok": False}

    old_total = float(u.get("total_earned", 0.0))

    for k in ("score", "power", "cps", "lvl", "next", "total_earned"):
        if k in s and isinstance(s[k], (int, float)):
            u[k] = max(0, s[k])

    new_total = float(u.get("total_earned", 0.0))
    delta = new_total - old_total
    if delta > 0:
        u["total_earned_all"] = u.get("total_earned_all", 0.0) + delta

    if float(u.get("score", 0.0)) > float(u.get("best_score", 0.0)):
        u["best_score"] = float(u["score"])

    if isinstance(s.get("theme"), str) and any(t["id"] == s["theme"] for t in THEMES):
        u["theme"] = s["theme"]

    for i in SHOP:
        ck, nk = f"c_{i['id']}", f"n_{i['id']}"
        if ck in s and isinstance(s[ck], (int, float)):
            u[ck] = max(i["base"], int(s[ck]))
        if nk in s and isinstance(s[nk], (int, float)):
            u[nk] = max(0, int(s[nk]))

    for i in COLLECTION:
        ok = f"o_{i['id']}"
        if ok in s:
            u[ok] = 1 if s[ok] else 0

    u["last_seen"] = int(time.time())
    save(data)
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)