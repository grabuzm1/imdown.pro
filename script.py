import json, os, re, time, hashlib, secrets, threading, shutil
from pathlib import Path
from fastapi import FastAPI, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import uvicorn
import resend

app = FastAPI()
BASE = Path(__file__).parent
DB = BASE / "users.json"
TPL = BASE / "templates"
STATIC = BASE / "static"
AVATARS_DIR = STATIC / "avatars"
AVATARS_DIR.mkdir(parents=True, exist_ok=True) # Создаст папку если нет
FILES_DIR = BASE / "walldown_files"
_lock = threading.Lock()
DAILY_COOLDOWN = 24 * 60 * 60
OFFLINE_CAP = 8 * 60 * 60

# Лимиты для синхронизации обоев
SYNC_QUOTA_PER_USER = 500 * 1024 * 1024      # 500 МБ на юзера
SYNC_MAX_FILE_SIZE = 150 * 1024 * 1024       # 150 МБ на файл

REBIRTH_BASE = 1e15
REBIRTH_STEP = 5

SECRET_KEY = "imdown_super_secret_change_me_2026"
SESSION_MAX_AGE = 60 * 60 * 24 * 30
COOKIE_NAME = "imdown_session"

AVATARS_DIR = BASE / "static" / "avatars"
AVATARS_DIR.mkdir(parents=True, exist_ok=True)

WALLDOWN_CALLBACK = "http://localhost:8080/callback"

RESEND_API_KEY = "re_P55JHmqH_HaJ37ubFYxCturT1j2V9FEDM"
RESEND_FROM = "imdown.pro <noreply@imdown.pro>"
resend.api_key = RESEND_API_KEY

_signer = URLSafeTimedSerializer(SECRET_KEY, salt="session")

app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
FILES_DIR.mkdir(exist_ok=True)


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

SHOP = [
    {"id": "clicker", "icon": "👆", "name": "Палец-робот", "desc": "+0.2/с", "base": 15, "cps": 0.2, "mult": 1.30},
    {"id": "farm", "icon": "🌾", "name": "Ферма", "desc": "+1.5/с", "base": 100, "cps": 1.5, "mult": 1.35},
    {"id": "rig", "icon": "⛏️", "name": "Шахта", "desc": "+8/с", "base": 500, "cps": 8.0, "mult": 1.40},
    {"id": "factory", "icon": "🏭", "name": "Завод", "desc": "+50/с", "base": 3000, "cps": 50.0, "mult": 1.45},
    {"id": "lab", "icon": "🔬", "name": "Лаборатория", "desc": "+300/с", "base": 15000, "cps": 300.0, "mult": 1.50},
    {"id": "reactor", "icon": "☢️", "name": "Реактор", "desc": "+2K/с", "base": 90000, "cps": 2000.0, "mult": 1.55},
    {"id": "station", "icon": "🛰️", "name": "Космостанция", "desc": "+12K/с", "base": 500000, "cps": 12000.0,
     "mult": 1.60},
    {"id": "colony", "icon": "🌕", "name": "Лунная база", "desc": "+80K/с", "base": 3000000, "cps": 80000.0,
     "mult": 1.65},
    {"id": "shipyard", "icon": "🚀", "name": "Верфь", "desc": "+500K/с", "base": 20000000, "cps": 500000.0,
     "mult": 1.70},
    {"id": "dyson", "icon": "🌐", "name": "Сфера Дайсона", "desc": "+3M/с", "base": 150000000, "cps": 3000000.0,
     "mult": 1.75},
    {"id": "galaxy", "icon": "🌌", "name": "Галактика", "desc": "+20M/с", "base": 1000000000, "cps": 20000000.0,
     "mult": 1.80},
    {"id": "universe", "icon": "✨", "name": "Вселенная", "desc": "+150M/с", "base": 8000000000, "cps": 150000000.0,
     "mult": 1.85},
    {"id": "time", "icon": "⏳", "name": "Машина времени", "desc": "+1B/с", "base": 60000000000, "cps": 1000000000.0,
     "mult": 1.90},
    {"id": "god", "icon": "👁️", "name": "Око Бога", "desc": "+8B/с", "base": 500000000000, "cps": 8000000000.0,
     "mult": 1.95},
    {"id": "eternal", "icon": "♾️", "name": "Вечность", "desc": "+75B/с", "base": 5000000000000, "cps": 75000000000.0,
     "mult": 2.00},
    {"id": "cosmos", "icon": "🌠", "name": "Космическая сеть", "desc": "+900B/с", "base": 500000000000000,
     "cps": 900000000000.0, "mult": 2.05},
    {"id": "multiv", "icon": "🌀", "name": "Порталы", "desc": "+15T/с", "base": 60000000000000000,
     "cps": 15000000000000.0, "mult": 2.10},
    {"id": "omni", "icon": "🔮", "name": "Кристалл силы", "desc": "+300T/с", "base": 1e22, "cps": 3e14, "mult": 2.15},
    {"id": "infinity", "icon": "💎", "name": "Ядро мира", "desc": "+8Qa/с", "base": 1e26, "cps": 8e15, "mult": 2.20},
    {"id": "transc", "icon": "👑", "name": "Трон творца", "desc": "+250Qa/с", "base": 1e30, "cps": 2.5e17, "mult": 2.25},
]

COLLECTION = [
    {"id": "villa", "icon": "🏠", "name": "Вилла", "desc": "+5% к клику", "base": 5000, "bonus": 0.05, "cps_bonus": 0.0},
    {"id": "car", "icon": "🚗", "name": "Машина", "desc": "+8% к клику", "base": 25000, "bonus": 0.08, "cps_bonus": 0.0},
    {"id": "yacht", "icon": "🛥️", "name": "Яхта", "desc": "+12% к клику", "base": 150000, "bonus": 0.12,
     "cps_bonus": 0.0},
    {"id": "jet", "icon": "✈️", "name": "Джет", "desc": "+20% к клику", "base": 1200000, "bonus": 0.20,
     "cps_bonus": 0.02},
    {"id": "island", "icon": "🏝️", "name": "Остров", "desc": "+35% к клику", "base": 10000000, "bonus": 0.35,
     "cps_bonus": 0.03},
    {"id": "rocket", "icon": "🚀", "name": "Ракета", "desc": "+60% к клику", "base": 150000000, "bonus": 0.60,
     "cps_bonus": 0.05},
    {"id": "moonbase", "icon": "🌕", "name": "Лунная база", "desc": "+100% к клику", "base": 2000000000, "bonus": 1.00,
     "cps_bonus": 0.08},
    {"id": "dyson2", "icon": "🌐", "name": "Сфера Дайсона", "desc": "+200% к клику", "base": 50000000000, "bonus": 2.00,
     "cps_bonus": 0.15},
    {"id": "galaxy2", "icon": "🌌", "name": "Галактика", "desc": "+500% к клику", "base": 1e15, "bonus": 5.00,
     "cps_bonus": 0.25},
    {"id": "crown", "icon": "👑", "name": "Корона", "desc": "+1000% к клику", "base": 1e20, "bonus": 10.0,
     "cps_bonus": 0.50},
]


# ============ EMAIL ФУНКЦИИ ============
def send_email(to_email: str, subject: str, html_body: str) -> bool:
    if not to_email or "@" not in to_email:
        return False
    try:
        resend.Emails.send({
            "from": RESEND_FROM,
            "to": to_email,
            "subject": subject,
            "html": html_body,
        })
        return True
    except Exception as e:
        print(f"[email] ошибка: {e}")
        return False


def email_wrapper(title: str, body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0a0a0a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0a0a;padding:60px 20px;">
    <tr><td align="center">
      <table width="100%" cellpadding="0" cellspacing="0" style="max-width:500px;background:#111317;border-radius:16px;border:1px solid rgba(255,255,255,0.06);padding:48px 40px;box-shadow:0 20px 60px rgba(0,0,0,0.5);">

        <tr><td style="padding-bottom:40px;text-align:center;">
          <span style="font-size:20px;font-weight:800;color:#fff;letter-spacing:-0.5px;">
            imdown<span style="color:#ff7a4a;">.pro</span>
          </span>
        </td></tr>

        <tr><td style="text-align:center;">
          <h1 style="margin:0 0 20px;font-size:26px;font-weight:800;color:#fff;letter-spacing:-0.5px;">{title}</h1>
          <div style="font-size:15px;line-height:1.7;color:#8a93a6;">{body_html}</div>
        </td></tr>

        <tr><td style="padding-top:48px;text-align:center;">
          <div style="font-size:12px;color:#444;border-top:1px solid rgba(255,255,255,0.06);padding-top:24px;">
            © 2026 imdown.pro
          </div>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body></html>"""


def send_welcome_email(to_email: str, name: str):
    subject = "Добро пожаловать в imdown.pro"
    body = f"""
      <p style="margin-bottom:16px;">Привет, <b style="color:#fff;">{name}</b>!</p>
      <p style="margin-bottom:32px;">Твой Down ID успешно создан. Теперь тебе доступны все проекты и функции платформы.</p>
      <a href="https://imdown.pro" style="display:inline-block;padding:14px 32px;background:#fff;color:#000;text-decoration:none;border-radius:10px;font-weight:700;font-size:14px;">Перейти на сайт</a>
    """
    return send_email(to_email, subject, email_wrapper("Добро пожаловать", body))


def send_password_changed_email(to_email: str, name: str):
    subject = "Пароль изменён · imdown.pro"
    body = f"""
      <p style="margin-bottom:16px;">Привет, <b style="color:#fff;">{name}</b>!</p>
      <p style="margin-bottom:24px;">Твой пароль от Down ID был успешно изменён.</p>
      <div style="padding:16px;background:rgba(255,122,74,.1);border-left:3px solid #ff7a4a;border-radius:6px;text-align:left;">
        <span style="font-size:13px;color:#b09a9a;">Если это был <b>не ты</b>, срочно свяжись со мной через <a href="https://imdown.pro/contact" style="color:#ff7a4a;">контакты</a>.</span>
      </div>
    """
    return send_email(to_email, subject, email_wrapper("Пароль изменён", body))


def send_email_verification(to_email: str, name: str, code: str):
    subject = "Код подтверждения · imdown.pro"
    body = f"""
      <p style="margin-bottom:16px;">Привет, <b style="color:#fff;">{name}</b>!</p>
      <p style="margin-bottom:24px;">Ты запросил привязку email к Down ID. Твой код подтверждения:</p>
      <div style="text-align:center; margin:32px 0;">
        <span style="display:inline-block; padding:16px 32px; background:rgba(255,122,74,0.1); border:1px dashed #ff7a4a; border-radius:12px; font-size:32px; font-weight:900; letter-spacing:6px; color:#ff7a4a;">{code}</span>
      </div>
      <p style="font-size:13px; color:#8a93a6;">Код действителен в течение 15 минут. Если ты этого не делал — просто проигнорируй письмо.</p>
    """
    return send_email(to_email, subject, email_wrapper("Подтверждение Email", body))


def rebirth_threshold(rebirths):
    return REBIRTH_BASE * (REBIRTH_STEP ** rebirths)


def rebirth_bonus(rebirths):
    return float(rebirths) * float(rebirths)


def default_user(pw_hash):
    now = int(time.time())
    u = {
        "pass": pw_hash,
        "email": "",
        "score": 0.0,
        "power": 1000.0,
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
        "walldown_tokens": [],
        "walldown_sync_enabled": False,
        "walldown_sync_files": [],
        "walldown_storage_used": 0,
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
        "email": "",
        "score": 0.0, "power": 1000.0, "cps": 0.0,
        "lvl": 1, "next": 100, "total_earned": 0.0,
        "total_earned_all": 0.0, "best_score": 0.0, "rebirths": 0,
        "theme": "sunset",
        "last_seen": int(time.time()),
        "game_session": "",
        "daily_last": 0, "daily_streak": 0, "daily_bonus": 0,
        "walldown_tokens": [],
        "walldown_sync_enabled": False,
        "walldown_sync_files": [],
        "walldown_storage_used": 0,
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
    u = migrate(data[user])
    save(data)

    used_mb = round(u.get("walldown_storage_used", 0) / (1024 * 1024), 1)
    quota_mb = round(SYNC_QUOTA_PER_USER / (1024 * 1024), 0)
    sync_on = "включена" if u.get("walldown_sync_enabled") else "выключена"
    files_count = len(u.get("walldown_sync_files", []))

    # Ссылка на аву
    avatar_url = ""
    if u.get("avatar_ext"):
        # Добавляем случайное число, чтобы браузер не кешировал старую аву
        avatar_url = f"/static/avatars/{user}{u['avatar_ext']}?v={int(time.time())}"
        print(f"[DEBUG] Аватар найден: {avatar_url}")  # Выведет в консоль сервера
    else:
        print(f"[DEBUG] У пользователя {user} нет avatar_ext")

    # Буква для заглушки, если нет авы
    letter = user[0].upper() if user else "U"
    html = read_tpl("account.html")
    html = html.replace("__NAME__", user)
    html = html.replace("__EMAIL__", u.get("email", "") or "—")
    html = html.replace("__SYNC_STATE__", sync_on)
    html = html.replace("__SYNC_USED__", f"{used_mb} / {quota_mb:.0f} МБ")
    html = html.replace("__SYNC_FILES__", str(files_count))
    html = html.replace("__SYNC_CHECKED__", "checked" if u.get("walldown_sync_enabled") else "")

    # ЗАМЕНА АВАТАРКИ
    html = html.replace("__AVATAR_URL__", avatar_url)

    msg = ""
    if error:
        msg = f'<div class="msg err">{error}</div>'
    elif ok:
        msg = f'<div class="msg ok">{ok}</div>'
    html = html.replace("__MSG__", msg)
    html = html.replace("__LETTER__", letter)
    return html


@app.post("/api/user/upload_avatar")
async def upload_avatar(request: Request, file: UploadFile = File(...)):
    user, _ = current_user(request)
    if not user: return {"ok": False, "error": "Не авторизован"}

    ext = Path(file.filename).suffix.lower()
    if ext not in [".png", ".jpg", ".jpeg", ".webp", ".gif"]:
        return {"ok": False, "error": "Разрешены только картинки"}

    file_path = AVATARS_DIR / f"{user}{ext}"

    # Удаляем старый аватар, если был
    for old in AVATARS_DIR.glob(f"{user}.*"):
        try:
            old.unlink()
        except:
            pass

    with open(file_path, "wb") as f:
        f.write(await file.read())

    data = load()
    if user in data:
        data[user]["avatar_ext"] = ext
        save(data)
        return {"ok": True, "message": "Аватар обновлен"}
    return {"ok": False, "error": "Пользователь не найден"}


@app.post("/toggle_sync")
async def toggle_sync(request: Request):
    user, _ = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    data = load()
    if user not in data:
        return RedirectResponse("/login", status_code=303)

    u = migrate(data[user])
    u["walldown_sync_enabled"] = not u.get("walldown_sync_enabled", False)
    data[user] = u
    save(data)

    # Просто возвращаемся на страницу без всяких ?ok=
    return RedirectResponse("/account", status_code=303)


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
    if u.get("email"):
        try:
            send_password_changed_email(u["email"], user)
        except Exception as e:
            print(f"[password] письмо: {e}")
    return RedirectResponse("/account?ok=Пароль+изменён", status_code=303)


@app.post("/change_email")
async def request_email_change(
        request: Request,
        current_pass: str = Form(...),
        new_email: str = Form(...),
):
    user, _ = current_user(request)
    if not user:
        return {"ok": False, "error": "Не авторизован"}

    new_email = (new_email or "").strip().lower()
    if "@" not in new_email or len(new_email) > 100:
        return {"ok": False, "error": "Некорректный email"}

    data = load()
    u = data.get(user)
    if not u:
        return {"ok": False, "error": "Пользователь не найден"}

    if not verify_pass(current_pass, u["pass"]):
        return {"ok": False, "error": "Неверный пароль"}

    for other_user, other_data in data.items():
        if other_user != user and other_data.get("email", "").lower() == new_email:
            return {"ok": False, "error": "Этот email уже привязан к другому аккаунту"}

    now = int(time.time())
    last_sent = u.get("email_code_sent_at", 0)
    if now - last_sent < 60:
        left = 60 - (now - last_sent)
        return {"ok": False, "error": f"Подожди {left} сек перед повторной отправкой"}

    code = str(secrets.randbelow(900000) + 100000)
    u["email_pending"] = new_email
    u["email_code"] = code
    u["email_code_sent_at"] = now
    u["email_code_attempts"] = 0
    data[user] = u
    save(data)

    try:
        send_email_verification(new_email, user, code)
    except Exception as e:
        print(f"[email_verify] письмо: {e}")
        return {"ok": False, "error": "Ошибка отправки письма"}

    return {"ok": True, "message": "Код отправлен на почту"}


@app.post("/verify_email_code")
async def verify_email_code(
        request: Request,
        code: str = Form(...),
):
    user, _ = current_user(request)
    if not user:
        return {"ok": False, "error": "Не авторизован"}

    data = load()
    u = data.get(user)
    if not u:
        return {"ok": False, "error": "Пользователь не найден"}

    pending = u.get("email_pending")
    expected = u.get("email_code")

    if not pending or not expected:
        return {"ok": False, "error": "Нет активного запроса"}

    attempts = u.get("email_code_attempts", 0)
    if attempts >= 5:
        u["email_pending"] = None
        u["email_code"] = None
        save(data)
        return {"ok": False, "error": "Слишком много попыток, запроси заново"}

    if code.strip() != expected:
        u["email_code_attempts"] = attempts + 1
        save(data)
        return {"ok": False, "error": "Неверный код"}

    u["email"] = pending
    u["email_pending"] = None
    u["email_code"] = None
    u["email_code_attempts"] = 0
    save(data)

    return {"ok": True, "message": "Почта успешно привязана"}


@app.post("/api/user/upload_avatar")
async def upload_avatar(request: Request, file: UploadFile = File(...)):
    user, _ = current_user(request)
    if not user: return {"ok": False, "error": "Не авторизован"}

    # Сохраняем файл
    ext = Path(file.filename).suffix.lower()
    if ext not in [".png", ".jpg", ".jpeg", ".webp"]:
        return {"ok": False, "error": "Только картинки"}

    file_path = AVATARS_DIR / f"{user}{ext}"

    # Удаляем старую аву, если была
    for old in AVATARS_DIR.glob(f"{user}.*"):
        old.unlink()

    with open(file_path, "wb") as f:
        f.write(await file.read())

    data = load()
    data[user]["avatar_ext"] = ext
    save(data)

    return {"ok": True, "message": "Аватар обновлен"}

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


SERVICES = {
    "downgames": {
        "title": "DownGames",
        "icon": "🎮",
        "desc": "Игровая платформа imdown.pro",
        "scopes": [
            ("👤", "Имя пользователя", "Твой ник в системе"),
            ("🎯", "Игровой прогресс", "Сохранение результатов в играх"),
        ],
        "issue_token": False,
        "redirect": "/downgames",
    },
    "walldown": {
        "title": "WallDown",
        "icon": "🖥",
        "desc": "Приложение для живых обоев",
        "scopes": [
            ("👤", "Имя пользователя", "Твой ник для отображения в приложении"),
            ("🎨", "Настройки оформления", "Выбранная тема (Sunset/Midnight)"),
            ("🚀", "Игровой прогресс", "Очки и достижения (для синхронизации)"),
        ],
        "issue_token": True,
        "redirect": WALLDOWN_CALLBACK,
    },
}


@app.get("/consent", response_class=HTMLResponse)
async def consent_page(request: Request, service: str = None):
    user, trusted = current_user(request)
    if not user:
        return RedirectResponse(f"/login?next=/consent?service={service or ''}", status_code=303)
    data = load()
    if user not in data:
        return RedirectResponse("/login", status_code=303)

    if not service or service not in SERVICES:
        return RedirectResponse("/", status_code=303)

    s = SERVICES[service]

    scopes_html = ""
    for ico, title, desc in s["scopes"]:
        scopes_html += f'''
        <div class="scope-row">
            <span class="ico">{ico}</span>
            <div class="txt">
                <b>{title}</b>
                <span>{desc}</span>
            </div>
        </div>
        '''

    html = read_tpl("consent.html")
    html = html.replace("__NAME__", user)
    html = html.replace("__SERVICE_TITLE__", s["title"])
    html = html.replace("__SERVICE_ICON__", s["icon"])
    html = html.replace("__SERVICE_DESC__", s["desc"])
    html = html.replace("__SCOPES__", scopes_html)
    html = html.replace("__SERVICE_KEY__", service)
    return html


@app.get("/walldown", response_class=HTMLResponse)
async def walldown_page(request: Request):
    user, trusted = current_user(request)
    if not user:
        return RedirectResponse("/login?next=/walldown", status_code=303)
    data = load()
    if user not in data:
        return RedirectResponse("/login", status_code=303)

    if "walldown" not in trusted:
        return RedirectResponse("/consent?service=walldown", status_code=303)

    html = read_tpl("walldown.html")
    html = html.replace("__NAME__", user)
    return html


@app.post("/consent_allow")
async def consent_allow(request: Request, service: str = Form(...)):
    user, trusted = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    data = load()
    if user not in data:
        return RedirectResponse("/login", status_code=303)

    if service not in SERVICES:
        return RedirectResponse("/", status_code=303)

    if service not in trusted:
        trusted.append(service)

    svc = SERVICES[service]

    if svc.get("issue_token"):
        token = secrets.token_urlsafe(32)
        u = data[user]
        tokens = u.get("walldown_tokens", [])
        tokens.append({
            "token": token,
            "created": int(time.time()),
        })
        u["walldown_tokens"] = tokens[-5:]
        data[user] = u
        save(data)

        resp = RedirectResponse(
            f"{svc['redirect']}?token={token}",
            status_code=303,
        )
        resp.set_cookie(COOKIE_NAME, make_session(user, trusted),
                        max_age=SESSION_MAX_AGE, httponly=True, samesite="lax")
        return resp

    resp = RedirectResponse(svc["redirect"], status_code=303)
    resp.set_cookie(COOKIE_NAME, make_session(user, trusted),
                    max_age=SESSION_MAX_AGE, httponly=True, samesite="lax")
    return resp


@app.post("/consent_deny")
async def consent_deny(request: Request, service: str = Form(...)):
    user, _ = current_user(request)
    if service == "walldown":
        return RedirectResponse("/walldown?denied=1", status_code=303)
    return RedirectResponse("/", status_code=303)


# ============ API ДЛЯ ПРИЛОЖЕНИЯ WALLDOWN ============
def _find_user_by_token(token):
    data = load()
    for name, u in data.items():
        if not isinstance(u, dict):
            continue
        for t in u.get("walldown_tokens", []):
            if t.get("token") == token:
                return name, u, data
    return None, None, None


@app.get("/api/walldown/me")
async def walldown_me(request: Request):
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "): return {"ok": False, "error": "no_token"}
    token = auth[7:].strip()
    name, u, _ = _find_user_by_token(token)
    if not u: return {"ok": False, "error": "invalid_token"}

    u = migrate(u)

    # Формируем ссылку на аватарку, если она есть
    avatar_url = ""
    if u.get("avatar_ext"):
        avatar_url = f"https://imdown.pro/static/avatars/{name}{u['avatar_ext']}?t={int(time.time())}"

    return {
        "ok": True,
        "name": name,
        "email": u.get("email", ""),
        "theme": u.get("theme", "sunset"),
        "sync_enabled": bool(u.get("walldown_sync_enabled", False)),
        "avatar_url": avatar_url,  # <--- Вот это нужно
        "storage_used": int(u.get("walldown_storage_used", 0)),
        "quota": SYNC_QUOTA_PER_USER,
        "max_file_size": SYNC_MAX_FILE_SIZE
    }


@app.post("/api/walldown/revoke")
async def walldown_revoke(request: Request):
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return {"ok": False, "error": "no_token"}
    token = auth[7:].strip()
    name, u, data = _find_user_by_token(token)
    if not u:
        return {"ok": False, "error": "invalid_token"}
    u["walldown_tokens"] = [t for t in u.get("walldown_tokens", []) if t.get("token") != token]
    data[name] = u
    save(data)
    return {"ok": True}


@app.get("/api/walldown/sync")
async def walldown_sync_get(request: Request):
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return {"ok": False, "error": "no_token"}
    token = auth[7:].strip()
    name, u, _ = _find_user_by_token(token)
    if not u:
        return {"ok": False, "error": "invalid_token"}
    if not u.get("walldown_sync_enabled"):
        return {"ok": False, "error": "sync_disabled"}
    return {
        "ok": True,
        "files": u.get("walldown_sync_files", []),
        "storage_used": int(u.get("walldown_storage_used", 0)),
        "quota": SYNC_QUOTA_PER_USER,
    }


@app.post("/api/walldown/upload")
async def walldown_upload(request: Request, file: UploadFile = File(...)):
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return {"ok": False, "error": "no_token"}
    token = auth[7:].strip()
    name, u, data = _find_user_by_token(token)
    if not u:
        return {"ok": False, "error": "invalid_token"}
    if not u.get("walldown_sync_enabled"):
        return {"ok": False, "error": "sync_disabled"}

    # Проверка размера
    contents = await file.read()
    size = len(contents)
    if size > SYNC_MAX_FILE_SIZE:
        return {"ok": False, "error": "too_big", "max_size": SYNC_MAX_FILE_SIZE}

    used = int(u.get("walldown_storage_used", 0))
    if used + size > SYNC_QUOTA_PER_USER:
        return {"ok": False, "error": "quota_exceeded",
                "used": used, "quota": SYNC_QUOTA_PER_USER, "file_size": size}

    # Сохраняем файл
    file_id = secrets.token_hex(16)
    user_dir = FILES_DIR / name
    user_dir.mkdir(exist_ok=True)
    # Сохраняем с оригинальным расширением
    ext = Path(file.filename).suffix.lower() or ".mp4"
    file_path = user_dir / f"{file_id}{ext}"
    with open(file_path, "wb") as f:
        f.write(contents)

    record = {
        "id": file_id,
        "name": file.filename,
        "size": size,
        "ext": ext,
        "added_at": int(time.time()),
    }
    files = u.get("walldown_sync_files", [])
    files.append(record)
    u["walldown_sync_files"] = files
    u["walldown_storage_used"] = used + size
    data[name] = u
    save(data)

    return {"ok": True, "file": record, "storage_used": u["walldown_storage_used"]}


@app.get("/api/walldown/file/{file_id}")
async def walldown_download_file(file_id: str, request: Request):
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return {"ok": False, "error": "no_token"}
    token = auth[7:].strip()
    name, u, _ = _find_user_by_token(token)
    if not u:
        return {"ok": False, "error": "invalid_token"}

    record = next((f for f in u.get("walldown_sync_files", []) if f["id"] == file_id), None)
    if not record:
        return {"ok": False, "error": "not_found"}

    file_path = FILES_DIR / name / f"{file_id}{record['ext']}"
    if not file_path.exists():
        return {"ok": False, "error": "file_missing"}

    return FileResponse(
        path=str(file_path),
        filename=record["name"],
        media_type="application/octet-stream",
    )


@app.delete("/api/walldown/file/{file_id}")
async def walldown_delete_file(file_id: str, request: Request):
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return {"ok": False, "error": "no_token"}
    token = auth[7:].strip()
    name, u, data = _find_user_by_token(token)
    if not u:
        return {"ok": False, "error": "invalid_token"}

    record = next((f for f in u.get("walldown_sync_files", []) if f["id"] == file_id), None)
    if not record:
        return {"ok": False, "error": "not_found"}

    file_path = FILES_DIR / name / f"{file_id}{record['ext']}"
    if file_path.exists():
        try:
            file_path.unlink()
        except Exception as e:
            print(f"[delete] {e}")

    u["walldown_sync_files"] = [f for f in u["walldown_sync_files"] if f["id"] != file_id]
    u["walldown_storage_used"] = max(0, u.get("walldown_storage_used", 0) - record["size"])
    data[name] = u
    save(data)

    return {"ok": True, "storage_used": u["walldown_storage_used"]}


# ============ DOWN GAMES (остальное без изменений) ============
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
        "owned": {i["id"]: u[f"o_{i['id']}"] for i in COLLECTION},
        "daily": {"can": can_claim, "seconds_left": left,
                  "streak": streak, "bonus": bonus},
    }
    html = read_tpl("clickerdown.html")
    html = html.replace("/*__SHOP__*/", json.dumps(SHOP, ensure_ascii=False))
    html = html.replace("/*__COLLECTION__*/", json.dumps(COLLECTION, ensure_ascii=False))
    html = html.replace("/*__THEMES__*/", json.dumps(THEMES, ensure_ascii=False))
    html = html.replace("/*__STATE__*/", json.dumps(state, ensure_ascii=False))
    return html


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

    u["rebirths"] = rb + 1
    u["score"] = 0.0
    u["power"] = 1000.0
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