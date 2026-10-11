"""
اتزان (Itizan) — منصة عربية لمساعدة اليافعين والأطفال على التوازن الرقمي.
Flask + SQLite. لكل مستخدم حساب خاص تُحفظ فيه أهدافه وإنجازاته.
كل البيانات يدخلها المستخدم بنفسه، ولا يجمع التطبيق أي بيانات أخرى.
"""
import os
import re
import secrets
import sqlite3
import time
from datetime import date, timedelta
from functools import wraps

from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
DB_PATH = os.environ.get("ITIZAN_DB", os.path.join(INSTANCE_DIR, "itizan.db"))
POINTS_PER_CHALLENGE = 10
MAX_GOALS = 3  # أقصى عدد للأهداف المتزامنة: القلة تحفظ التركيز ولا تثقل المستخدم
HASH_METHOD = "pbkdf2:sha256"


def load_secret_key():
    """مفتاح توقيع الجلسات: من متغير بيئة، أو يُنشأ مرة واحدة ويُحفظ في مجلد instance."""
    env = os.environ.get("ITIZAN_SECRET_KEY")
    if env:
        return env
    os.makedirs(INSTANCE_DIR, exist_ok=True)
    path = os.path.join(INSTANCE_DIR, "secret_key")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(path, "w", encoding="utf-8") as f:
        f.write(key)
    return key


app = Flask(__name__)
app.config.update(
    SECRET_KEY=load_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("ITIZAN_HTTPS") == "1",  # فعّله عند النشر خلف HTTPS
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    MAX_CONTENT_LENGTH=16 * 1024,
)

app.json.ensure_ascii = False  # يبقى العربي مقروءاً في ردود الـ API

# ----------------------------------------------------------------------------
# البيانات الأولية
# ----------------------------------------------------------------------------
GOALS = [
    ("screen_time", "تقليل وقت استخدام الهاتف", "phone"),
    ("sleep", "تحسين روتين النوم", "moon"),
    ("study", "الالتزام بالمهام الدراسية", "book"),
    ("hobbies", "زيادة الأنشطة الواقعية", "leaf"),
    ("family", "قضاء وقت مع العائلة", "users"),
]

# (slug, goal_key, title, description, minutes, icon)
CHALLENGES = [
    ("st-before-bed", "screen_time", "ابتعد عن الهاتف قبل النوم", "ابتعد عن الهاتف ساعةً كاملة قبل موعد نومك، واستبدل به قراءة كتاب أو الاستماع إلى موسيقى هادئة.", 60, "book"),
    ("st-meal", "screen_time", "وجبة بلا شاشة", "تناول وجبة كاملة دون هاتف أو تلفاز، وركّز على الطعام وعلى من حولك.", 30, "users"),
    ("st-two-hours", "screen_time", "أقل من ساعتين على الهاتف", "اجعل استخدامك للهاتف اليوم أقل من ساعتين، ودوّن شعورك في المساء.", 120, "phone"),
    ("st-other-room", "screen_time", "الهاتف في غرفة أخرى", "ضع هاتفك في غرفة أخرى أثناء المذاكرة أو اللعب مدة 45 دقيقة.", 45, "phone"),
    ("sl-on-time", "sleep", "نم في موعدك", "حدّد موعداً ثابتاً للنوم الليلة والتزم به دون تأجيل.", 0, "moon"),
    ("sl-calm", "sleep", "نصف ساعة من الهدوء", "قبل النوم بنصف ساعة، أطفئ الشاشات وخفّف الإضاءة في غرفتك.", 30, "moon"),
    ("sl-stretch", "sleep", "تمدّد خفيف قبل النوم", "مارس تمارين التمدد خمس دقائق قبل النوم بدلاً من تصفّح الهاتف.", 5, "leaf"),
    ("su-focus", "study", "جلسة تركيز 25 دقيقة", "ذاكر 25 دقيقة متواصلة دون إشعارات، ثم خذ استراحة قصيرة.", 25, "book"),
    ("su-plan", "study", "رتّب مهام الغد", "اكتب على ورقة ثلاث مهام دراسية لليوم التالي قبل أن تنام.", 10, "target"),
    ("su-hardest", "study", "ابدأ بالأصعب", "ابدأ بالمهمة الأصعب قبل أي ترفيه رقمي.", 40, "target"),
    ("ho-read", "hobbies", "اقرأ 30 دقيقة", "اختر كتاباً تحبّه واقرأ منه نصف ساعة.", 30, "book"),
    ("ho-outdoor", "hobbies", "اخرج إلى الهواء الطلق", "امشِ أو العب في الخارج ثلاثين دقيقة دون هاتف.", 30, "leaf"),
    ("ho-craft", "hobbies", "ارسم أو اصنع شيئاً", "جرّب الرسم أو التلوين أو الأشغال اليدوية مدة 20 دقيقة.", 20, "leaf"),
    ("fa-talk", "family", "حديث مع الأسرة", "اجلس مع أحد أفراد أسرتك عشرين دقيقة دون شاشات.", 20, "users"),
    ("fa-game", "family", "لعبة جماعية", "العب لعبة ورقية أو لوحية مع أفراد الأسرة.", 30, "users"),
    ("fa-help", "family", "ساعد في شأن منزلي", "اعرض مساعدتك في إعداد الوجبة أو ترتيب البيت.", 20, "users"),
]


# ----------------------------------------------------------------------------
# قاعدة البيانات
# ----------------------------------------------------------------------------
def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = connect()
    # ترقية من نسخ تجريبية أقدم (بيانات اختبار فقط)
    ch_cols = [r[1] for r in db.execute("PRAGMA table_info(challenges)")]
    ug_cols = [r[1] for r in db.execute("PRAGMA table_info(user_goal)")]
    if (ch_cols and "slug" not in ch_cols) or (ug_cols and "user_id" not in ug_cols):
        db.executescript("DROP TABLE IF EXISTS usage_log; DROP TABLE IF EXISTS daily_log; "
                         "DROP TABLE IF EXISTS user_goal; DROP TABLE IF EXISTS challenges;")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT NOT NULL UNIQUE,
            display_name  TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS goals (
            key   TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            icon  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS challenges (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            slug        TEXT NOT NULL UNIQUE,
            goal_key    TEXT NOT NULL REFERENCES goals(key),
            title       TEXT NOT NULL,
            description TEXT NOT NULL,
            minutes     INTEGER NOT NULL DEFAULT 0,
            icon        TEXT NOT NULL
        );
        -- (قديم) كان يحفظ هدفاً واحداً لكل مستخدم؛ يُستخدم الآن للترحيل فقط إلى user_goals
        CREATE TABLE IF NOT EXISTS user_goal (
            user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            goal_key   TEXT NOT NULL REFERENCES goals(key),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        -- سجل الإنجاز اليومي: تحدٍّ واحد لكل مستخدم في كل يوم
        CREATE TABLE IF NOT EXISTS daily_log (
            user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            day          TEXT NOT NULL,
            goal_key     TEXT NOT NULL,
            challenge_id INTEGER NOT NULL REFERENCES challenges(id),
            completed    INTEGER NOT NULL DEFAULT 0,
            completed_at TEXT,
            points       INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, day)
        );
        -- ساعات استخدام الهاتف التي يدخلها المستخدم بنفسه (مؤشر لقياس الأثر)
        CREATE TABLE IF NOT EXISTS usage_log (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            day     TEXT NOT NULL,
            hours   REAL NOT NULL,
            quality TEXT,
            PRIMARY KEY (user_id, day)
        );
        -- أهداف المستخدم (من 1 إلى MAX_GOALS)
        CREATE TABLE IF NOT EXISTS user_goals (
            user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            goal_key TEXT NOT NULL REFERENCES goals(key),
            PRIMARY KEY (user_id, goal_key)
        );
        -- تحدي كل هدف في كل يوم، واحد لكل هدف
        CREATE TABLE IF NOT EXISTS daily_picks (
            user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            day          TEXT NOT NULL,
            goal_key     TEXT NOT NULL REFERENCES goals(key),
            challenge_id INTEGER NOT NULL REFERENCES challenges(id),
            completed    INTEGER NOT NULL DEFAULT 0,
            completed_at TEXT,
            points       INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, day, goal_key)
        );
        -- أعلى مرحلة بلغتها شجرة المستخدم (لا تنقص أبداً)
        CREATE TABLE IF NOT EXISTS tree_state (
            user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            max_stage  INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    if "quality" not in [r[1] for r in db.execute("PRAGMA table_info(usage_log)")]:
        db.execute("ALTER TABLE usage_log ADD COLUMN quality TEXT")
    db.executemany(
        "INSERT INTO goals(key,title,icon) VALUES (?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET title=excluded.title, icon=excluded.icon",
        GOALS,
    )
    db.executemany(
        "INSERT INTO challenges(slug,goal_key,title,description,minutes,icon) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(slug) DO UPDATE SET goal_key=excluded.goal_key, title=excluded.title, "
        "description=excluded.description, minutes=excluded.minutes, icon=excluded.icon",
        CHALLENGES,
    )
    # ترحيل بيانات النسخ السابقة (آمن ومتكرر): لا يمسّ من لديه أهداف محفوظة بالصيغة الجديدة
    db.execute(
        "INSERT OR IGNORE INTO user_goals(user_id, goal_key) "
        "SELECT ug.user_id, ug.goal_key FROM user_goal ug WHERE ug.user_id NOT IN (SELECT user_id FROM user_goals)"
    )
    db.execute(
        "INSERT OR IGNORE INTO user_goals(user_id, goal_key) "
        "SELECT id, ? FROM users WHERE id NOT IN (SELECT user_id FROM user_goals)", (DEFAULT_GOAL,)
    )
    db.execute(
        "INSERT OR IGNORE INTO daily_picks(user_id, day, goal_key, challenge_id, completed, completed_at, points) "
        "SELECT l.user_id, l.day, l.goal_key, l.challenge_id, l.completed, l.completed_at, l.points FROM daily_log l "
        "WHERE l.completed = 1 AND NOT EXISTS (SELECT 1 FROM daily_picks p WHERE p.user_id = l.user_id AND p.day = l.day)"
    )
    db.execute("DELETE FROM daily_log WHERE completed = 0")  # كانت تحفظ اختيار اليوم، وهو الآن في daily_picks
    db.commit()
    db.close()


# ----------------------------------------------------------------------------
# الأمان: ترويسات، حماية الطلبات، تحديد المحاولات
# ----------------------------------------------------------------------------
@app.context_processor
def inject_asset_version():
    """يضيف رقم إصدار (وقت تعديل الملف) لروابط الملفات الثابتة، فلا يعرض المتصفح نسخة قديمة منها."""
    def asset(filename):
        try:
            v = int(os.path.getmtime(os.path.join(app.static_folder, filename)))
        except OSError:
            v = 0
        return url_for("static", filename=filename, v=v)
    return {"asset": asset}


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.before_request
def require_custom_header():
    """حماية من تزوير الطلبات (CSRF): الطلبات المغيّرة للبيانات تتطلب ترويسة لا يستطيع موقع آخر إرسالها."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.path.startswith("/api/"):
        if request.headers.get("X-Requested-With") != "itizan":
            return jsonify({"error": "طلب غير مسموح به."}), 403


_ATTEMPTS = {}  # key -> [timestamps]


def too_many(key, limit, window):
    now = time.time()
    hits = [t for t in _ATTEMPTS.get(key, []) if now - t < window]
    _ATTEMPTS[key] = hits
    return len(hits) >= limit


def record_attempt(key):
    _ATTEMPTS.setdefault(key, []).append(time.time())


# ----------------------------------------------------------------------------
# الحسابات
# ----------------------------------------------------------------------------
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")
DUMMY_HASH = generate_password_hash("itizan-dummy-password", method=HASH_METHOD)
DEFAULT_GOAL = "screen_time"
QUALITIES = {"purposeful", "balanced", "aimless"}  # هادف ومفيد / متوازن / تصفّح بلا هدف


def current_user():
    if "user" in g:
        return g.user
    g.user = None
    uid = session.get("uid")
    if uid:
        g.user = get_db().execute(
            "SELECT id, username, display_name, created_at FROM users WHERE id = ?", (uid,)
        ).fetchone()
    return g.user


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            session.clear()
            return jsonify({"error": "يلزم تسجيل الدخول أولاً."}), 401
        return fn(*args, **kwargs)
    return wrapper


def user_dict(u):
    return {"username": u["username"], "display_name": u["display_name"]}


def start_session(user_id):
    session.clear()
    session["uid"] = user_id
    session.permanent = True


def validate_registration(username, display, password):
    if len(display) < 2 or len(display) > 40:
        return "الاسم يجب أن يتكوّن من حرفين على الأقل وبحد أقصى 40 حرفاً."
    if not USERNAME_RE.match(username):
        return "اسم المستخدم يتكوّن من 3 إلى 30 خانة، من أحرف إنجليزية أو أرقام أو الشرطة السفلية (_)."
    if len(password) < 8 or len(password) > 128:
        return "كلمة المرور يجب ألا تقل عن 8 أحرف."
    if password.lower() == username:
        return "لا يجوز أن تطابق كلمة المرور اسم المستخدم."
    return None


@app.post("/api/register")
def api_register():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip().lower()
    display = " ".join(str(data.get("display_name", "")).split())
    password = str(data.get("password", ""))
    ip_key = ("register", request.remote_addr)
    if too_many(ip_key, 10, 3600):
        return jsonify({"error": "تكرر إنشاء الحسابات من هذا الجهاز، يُرجى المحاولة لاحقاً."}), 429
    error = validate_registration(username, display, password)
    if error:
        return jsonify({"error": error}), 400
    db = get_db()
    if db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        return jsonify({"error": "اسم المستخدم مستخدم من قبل، اختر اسماً آخر."}), 409
    cur = db.execute(
        "INSERT INTO users(username, display_name, password_hash) VALUES (?,?,?)",
        (username, display, generate_password_hash(password, method=HASH_METHOD)),
    )
    db.execute("INSERT INTO user_goals(user_id, goal_key) VALUES (?, ?)", (cur.lastrowid, DEFAULT_GOAL))
    db.commit()
    record_attempt(ip_key)
    start_session(cur.lastrowid)
    return jsonify({"user": {"username": username, "display_name": display}}), 201


@app.post("/api/login")
def api_login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip().lower()
    password = str(data.get("password", ""))
    key = ("login", request.remote_addr, username)
    if too_many(key, 8, 600):
        return jsonify({"error": "تكررت المحاولات الخاطئة، يُرجى المحاولة بعد عدة دقائق."}), 429
    user = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    # نفحص دائماً تجزئة واحدة حتى لا يُكشف وجود الاسم من زمن الاستجابة
    ok = check_password_hash(user["password_hash"] if user else DUMMY_HASH, password)
    if not user or not ok:
        record_attempt(key)
        return jsonify({"error": "اسم المستخدم أو كلمة المرور غير صحيحة."}), 401
    _ATTEMPTS.pop(key, None)
    start_session(user["id"])
    return jsonify({"user": user_dict(user)})


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/me")
@login_required
def api_me():
    u = current_user()
    return jsonify({**user_dict(u), "created_at": u["created_at"]})


@app.post("/api/account/delete")
@login_required
def api_delete_account():
    """حذف الحساب وجميع بياناته نهائياً (يتطلب كلمة المرور)."""
    data = request.get_json(silent=True) or {}
    db = get_db()
    u = current_user()
    row = db.execute("SELECT password_hash FROM users WHERE id = ?", (u["id"],)).fetchone()
    if not check_password_hash(row["password_hash"], str(data.get("password", ""))):
        return jsonify({"error": "كلمة المرور غير صحيحة."}), 401
    db.execute("DELETE FROM users WHERE id = ?", (u["id"],))  # الحذف يشمل بقية الجداول (ON DELETE CASCADE)
    db.commit()
    session.clear()
    return jsonify({"ok": True})


# ----------------------------------------------------------------------------
# دوال مساعدة للتحديات والتقدم
# ----------------------------------------------------------------------------
def today_str():
    return date.today().isoformat()


def selected_goals(db, uid):
    """أهداف المستخدم بترتيب اختياره (هدف واحد على الأقل)."""
    sql = ("SELECT g.key, g.title, g.icon FROM user_goals u JOIN goals g ON g.key = u.goal_key "
           "WHERE u.user_id = ? ORDER BY u.rowid")
    rows = db.execute(sql, (uid,)).fetchall()
    if not rows:
        db.execute("INSERT OR IGNORE INTO user_goals(user_id, goal_key) VALUES (?, ?)", (uid, DEFAULT_GOAL))
        db.commit()
        rows = db.execute(sql, (uid,)).fetchall()
    return rows


def set_selected_goals(db, uid, keys):
    db.execute("DELETE FROM user_goals WHERE user_id = ?", (uid,))
    db.executemany("INSERT INTO user_goals(user_id, goal_key) VALUES (?, ?)", [(uid, k) for k in keys])
    # تحديات اليوم غير المنجزة للأهداف التي أُزيلت لا معنى لها
    marks = ",".join("?" * len(keys))
    db.execute(
        f"DELETE FROM daily_picks WHERE user_id = ? AND day = ? AND completed = 0 AND goal_key NOT IN ({marks})",
        (uid, today_str(), *keys),
    )


def challenge_dict(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "minutes": row["minutes"],
        "icon": row["icon"],
    }


def default_challenge_for_today(db, goal_key):
    """اختيار تحدٍّ ثابت لليوم (تدوير بسيط حسب التاريخ)."""
    rows = db.execute("SELECT * FROM challenges WHERE goal_key = ? ORDER BY id", (goal_key,)).fetchall()
    return rows[date.today().toordinal() % len(rows)]


def pick_for(db, uid, goal_key):
    """(تحدي اليوم لهذا الهدف, سطر الإنجاز أو None)."""
    row = db.execute(
        "SELECT * FROM daily_picks WHERE user_id = ? AND day = ? AND goal_key = ?", (uid, today_str(), goal_key)
    ).fetchone()
    if row:
        return db.execute("SELECT * FROM challenges WHERE id = ?", (row["challenge_id"],)).fetchone(), row
    return default_challenge_for_today(db, goal_key), None


def today_items(db, uid):
    items = []
    for g in selected_goals(db, uid):
        ch, row = pick_for(db, uid, g["key"])
        items.append({
            "goal": dict(g),
            "challenge": challenge_dict(ch),
            "completed": bool(row and row["completed"]),
            "points": row["points"] if row else 0,
        })
    return items


def sync_day(db, uid, day):
    """يُبقي daily_log سجلاً مجمَّعاً: يوم الإنجاز هو اليوم الذي أُنجز فيه تحدٍّ واحد على الأقل."""
    rows = db.execute(
        "SELECT goal_key, challenge_id, completed_at, points FROM daily_picks "
        "WHERE user_id = ? AND day = ? AND completed = 1 ORDER BY completed_at, goal_key", (uid, day)
    ).fetchall()
    if rows:
        db.execute(
            """INSERT INTO daily_log(user_id, day, goal_key, challenge_id, completed, completed_at, points)
               VALUES (?, ?, ?, ?, 1, ?, ?)
               ON CONFLICT(user_id, day) DO UPDATE SET goal_key = excluded.goal_key,
                   challenge_id = excluded.challenge_id, completed = 1,
                   completed_at = excluded.completed_at, points = excluded.points""",
            (uid, day, rows[0]["goal_key"], rows[0]["challenge_id"], rows[0]["completed_at"],
             sum(r["points"] for r in rows)),
        )
    else:
        db.execute("DELETE FROM daily_log WHERE user_id = ? AND day = ?", (uid, day))


def resolve_goal(db, uid, goal_key):
    """يحدّد الهدف المقصود في الطلب: اختياري إن كان للمستخدم هدف واحد فقط."""
    goals = selected_goals(db, uid)
    if goal_key is None:
        if len(goals) == 1:
            return goals[0], None
        return None, (jsonify({"error": "حدّد الهدف المقصود."}), 400)
    for g in goals:
        if g["key"] == goal_key:
            return g, None
    return None, (jsonify({"error": "هذا الهدف ليس ضمن أهدافك."}), 400)


def week_days(db, uid):
    """آخر 7 أيام (من الأقدم إلى اليوم) مع حالة الإنجاز."""
    start = date.today() - timedelta(days=6)
    rows = db.execute(
        "SELECT day, completed FROM daily_log WHERE user_id = ? AND day >= ?", (uid, start.isoformat())
    ).fetchall()
    done = {r["day"] for r in rows if r["completed"]}
    out = []
    for i in range(7):
        d = start + timedelta(days=i)
        out.append({
            "date": d.isoformat(),
            "weekday": d.weekday(),  # الاثنين=0 ... الأحد=6
            "completed": d.isoformat() in done,
            "is_today": d == date.today(),
        })
    return out


def streak(db, uid):
    rows = db.execute("SELECT day FROM daily_log WHERE user_id = ? AND completed = 1", (uid,)).fetchall()
    done = {r["day"] for r in rows}
    d = date.today()
    if d.isoformat() not in done:
        d -= timedelta(days=1)  # اليوم لم ينتهِ بعد، فلا نكسر السلسلة
    count = 0
    while d.isoformat() in done:
        count += 1
        d -= timedelta(days=1)
    return count


def usage_summary(db, uid):
    """ساعات الاستخدام وجودته كما سجّلها المستخدم: آخر 7 أيام ومتوسطها مقابل الأسبوع الذي قبله."""
    today = date.today()
    start = today - timedelta(days=13)
    rows = db.execute(
        "SELECT day, hours, quality FROM usage_log WHERE user_id = ? AND day >= ?", (uid, start.isoformat())
    ).fetchall()
    by_day = {r["day"]: (r["hours"], r["quality"]) for r in rows}
    week = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        hours, quality = by_day.get(d.isoformat(), (None, None))
        week.append({"date": d.isoformat(), "weekday": d.weekday(), "hours": hours, "quality": quality})
    prev = [by_day.get((today - timedelta(days=i)).isoformat(), (None, None))[0] for i in range(7, 14)]

    def avg(values):
        vals = [v for v in values if v is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    rated = [w for w in week if w["quality"]]
    return {
        "week": week,
        "avg_week": avg([w["hours"] for w in week]),
        "avg_prev": avg(prev),
        "today": by_day.get(today.isoformat(), (None, None))[0],
        "today_quality": by_day.get(today.isoformat(), (None, None))[1],
        "rated_days": len(rated),
        "aimless_days": sum(1 for w in rated if w["quality"] == "aimless"),
    }


# ----------------------------------------------------------------------------
# الشجرة الافتراضية: تنمو بعدد أيام الإنجاز، ولا تموت ولا تفقد أعلى مرحلة بلغتها
# ----------------------------------------------------------------------------
TREE_STAGES = [  # (عدد أيام الإنجاز اللازمة لبلوغ المرحلة, اسمها)
    (0, "بذرة"),
    (1, "نبتة"),
    (3, "شتلة"),
    (7, "شجيرة"),
    (14, "شجرة فتية"),
    (30, "شجرة مثمرة"),
]


def days_ar(n):
    """عدد الأيام بصياغة عربية سليمة: يوم واحد، يومان، 3 أيام، 11 يوماً."""
    if n == 1:
        return "يوم واحد"
    if n == 2:
        return "يومان"
    return f"{n} أيام" if 3 <= n <= 10 else f"{n} يوماً"


def tree_info(db, uid):
    """حالة شجرة المستخدم. أعلى مرحلة تُحفظ في القاعدة، فلا يُنقصها التراجع عن إنجاز ولا الانقطاع."""
    completed = db.execute(
        "SELECT COUNT(*) FROM daily_log WHERE user_id = ? AND completed = 1", (uid,)
    ).fetchone()[0]
    stage_now = max(i for i, (need, _) in enumerate(TREE_STAGES) if completed >= need)
    row = db.execute("SELECT max_stage FROM tree_state WHERE user_id = ?", (uid,)).fetchone()
    saved = row["max_stage"] if row else 0
    stage = max(saved, stage_now)
    if row is None or stage > saved:
        db.execute(
            "INSERT INTO tree_state(user_id, max_stage) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET max_stage = excluded.max_stage, updated_at = CURRENT_TIMESTAMP",
            (uid, stage),
        )
        db.commit()

    last = db.execute(
        "SELECT MAX(day) FROM daily_log WHERE user_id = ? AND completed = 1", (uid,)
    ).fetchone()[0]
    days_since = (date.today() - date.fromisoformat(last)).days if last else None
    if last is None:
        status = "resting" if stage > 0 else "new"
    else:
        status = "thriving" if days_since <= 1 else "resting"
    status_text = {
        "new": "بذرتك تنتظر أول مهمة تُكملها لتبدأ بالنمو.",
        "thriving": "شجرتك في أفضل حالاتها، واصل إكمال مهامك اليومية.",
        "resting": "شجرتك تستريح في انتظارك، ولن تفقد ما بلغته. عد بمهمة صغيرة لتواصل النمو.",
    }[status]

    if stage < len(TREE_STAGES) - 1:
        base = TREE_STAGES[stage][0]
        need_next = TREE_STAGES[stage + 1][0]
        remaining = max(0, need_next - completed)
        percent = max(0, min(100, round((completed - base) / (need_next - base) * 100)))
        hint = f"يتبقى {days_ar(remaining)} من أيام الإنجاز لتصبح {TREE_STAGES[stage + 1][1]}."
        next_name = TREE_STAGES[stage + 1][1]
    else:
        remaining, percent, next_name = None, 100, None
        hint = "بلغت شجرتك أعلى مراحل النمو، حافظ على عاداتك الطيبة."

    return {
        "stage": stage,
        "stage_name": TREE_STAGES[stage][1],
        "max_stage": len(TREE_STAGES) - 1,
        "completed_days": completed,
        "next_stage_name": next_name,
        "remaining_days": remaining,
        "progress_percent": percent,
        "status": status,
        "status_text": status_text,
        "days_since_last": days_since,
        "kept_stage": stage > stage_now,
        "hint": hint,
        "stages": [
            {"stage": i, "name": name, "need": need, "reached": i <= stage}
            for i, (need, name) in enumerate(TREE_STAGES)
        ],
    }


# ----------------------------------------------------------------------------
# الصفحات
# ----------------------------------------------------------------------------
@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/login")
def login_page():
    if current_user():
        return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="login")


@app.route("/register")
def register_page():
    if current_user():
        return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="register")


@app.route("/app")
def dashboard():
    if current_user() is None:
        return redirect(url_for("login_page"))
    return render_template("app.html")


# ----------------------------------------------------------------------------
# واجهة البرمجة (API) — كلها تتطلب تسجيل الدخول وتعمل على بيانات المستخدم الحالي فقط
# ----------------------------------------------------------------------------
@app.get("/api/goals")
@login_required
def api_goals():
    db = get_db()
    goals = [dict(r) for r in db.execute("SELECT key, title, icon FROM goals").fetchall()]
    selected = [g["key"] for g in selected_goals(db, current_user()["id"])]
    return jsonify({"goals": goals, "selected": selected, "current": selected[0], "max": MAX_GOALS})


@app.post("/api/goals")
@login_required
def api_set_goals():
    """حفظ أهداف المستخدم. الجسم: {"goal_keys": ["sleep", "study"]} (من 1 إلى 3 أهداف)."""
    data = request.get_json(silent=True) or {}
    keys = data.get("goal_keys")
    if not isinstance(keys, list):
        return jsonify({"error": "صيغة الأهداف غير صحيحة."}), 400
    clean = []
    for k in keys:
        if isinstance(k, str) and k not in clean:
            clean.append(k)
    if not clean:
        return jsonify({"error": "اختر هدفاً واحداً على الأقل."}), 400
    if len(clean) > MAX_GOALS:
        return jsonify({"error": f"يمكنك اختيار حتى {MAX_GOALS} أهداف."}), 400
    db = get_db()
    valid = {r["key"] for r in db.execute("SELECT key FROM goals").fetchall()}
    if any(k not in valid for k in clean):
        return jsonify({"error": "هدف غير معروف."}), 400
    set_selected_goals(db, current_user()["id"], clean)
    db.commit()
    return jsonify({"selected": clean})


@app.get("/api/today")
@login_required
def api_today():
    db = get_db()
    uid = current_user()["id"]
    items = today_items(db, uid)
    done = sum(1 for i in items if i["completed"])
    usage = usage_summary(db, uid)
    return jsonify({
        "items": items,
        "goals": [i["goal"] for i in items],
        "completed_count": done,
        "total": len(items),
        "completed": done == len(items),
        "goal": items[0]["goal"],            # للتوافق: أول هدف وتحديه
        "challenge": items[0]["challenge"],
        "week": week_days(db, uid),
        "usage_today": usage["today"],
        "usage_quality_today": usage["today_quality"],
    })


@app.post("/api/today/complete")
@login_required
def api_complete_today():
    """تسجيل إتمام تحدي اليوم لهدفٍ ما (زر «أكملتُ المهمة»). الجسم: {"goal_key": "sleep"} (اختياري لهدف واحد)."""
    db = get_db()
    uid = current_user()["id"]
    goal, err = resolve_goal(db, uid, (request.get_json(silent=True) or {}).get("goal_key"))
    if err:
        return err
    ch, row = pick_for(db, uid, goal["key"])
    if row and row["completed"]:
        return jsonify({"completed": True, "points": row["points"], "already": True, "goal_key": goal["key"],
                        "tree": tree_info(db, uid), "tree_grew": False})
    before = tree_info(db, uid)["stage"]
    db.execute(
        """INSERT INTO daily_picks(user_id, day, goal_key, challenge_id, completed, completed_at, points)
           VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP, ?)
           ON CONFLICT(user_id, day, goal_key) DO UPDATE SET completed = 1, completed_at = CURRENT_TIMESTAMP,
                                                              points = excluded.points""",
        (uid, today_str(), goal["key"], ch["id"], POINTS_PER_CHALLENGE),
    )
    sync_day(db, uid, today_str())
    db.commit()
    tree = tree_info(db, uid)
    return jsonify({"completed": True, "points": POINTS_PER_CHALLENGE, "already": False, "goal_key": goal["key"],
                    "tree": tree, "tree_grew": tree["stage"] > before})


@app.post("/api/today/undo")
@login_required
def api_undo_today():
    """التراجع عن إنجاز اليوم (لهدف محدد، أو لكل أهداف اليوم إن لم يُحدَّد). لا تفقد الشجرة أعلى مرحلة بلغتها."""
    db = get_db()
    uid = current_user()["id"]
    tree_info(db, uid)  # يثبّت أعلى مرحلة قبل التراجع
    key = (request.get_json(silent=True) or {}).get("goal_key")
    if key is not None:
        goal, err = resolve_goal(db, uid, key)
        if err:
            return err
        db.execute(
            "UPDATE daily_picks SET completed = 0, completed_at = NULL, points = 0 "
            "WHERE user_id = ? AND day = ? AND goal_key = ?", (uid, today_str(), goal["key"]))
    else:
        db.execute(
            "UPDATE daily_picks SET completed = 0, completed_at = NULL, points = 0 WHERE user_id = ? AND day = ?",
            (uid, today_str()))
    sync_day(db, uid, today_str())
    db.commit()
    return jsonify({"completed": False, "tree": tree_info(db, uid)})


@app.get("/api/tree")
@login_required
def api_tree():
    return jsonify(tree_info(get_db(), current_user()["id"]))


@app.get("/api/challenges")
@login_required
def api_challenges():
    """تحديات كل هدف من أهداف المستخدم، مع تمييز تحدي اليوم لكل هدف."""
    db = get_db()
    uid = current_user()["id"]
    groups = []
    for g in selected_goals(db, uid):
        today_ch, row = pick_for(db, uid, g["key"])
        rows = db.execute("SELECT * FROM challenges WHERE goal_key = ? ORDER BY id", (g["key"],)).fetchall()
        items = []
        for r in rows:
            d = challenge_dict(r)
            d["is_today"] = r["id"] == today_ch["id"]
            d["completed"] = bool(d["is_today"] and row and row["completed"])
            items.append(d)
        groups.append({"goal": dict(g), "challenges": items})
    return jsonify({"groups": groups, "week": week_days(db, uid)})


@app.post("/api/challenges/<int:cid>/select")
@login_required
def api_select_challenge(cid):
    """اختيار تحدٍّ آخر ليكون تحدي اليوم لهدفه (ما لم يُنجز تحدي ذلك الهدف اليوم)."""
    db = get_db()
    uid = current_user()["id"]
    ch = db.execute("SELECT * FROM challenges WHERE id = ?", (cid,)).fetchone()
    if not ch:
        return jsonify({"error": "التحدي غير موجود."}), 404
    if ch["goal_key"] not in {g["key"] for g in selected_goals(db, uid)}:
        return jsonify({"error": "هذا التحدي ليس ضمن أهدافك."}), 400
    row = db.execute(
        "SELECT * FROM daily_picks WHERE user_id = ? AND day = ? AND goal_key = ?", (uid, today_str(), ch["goal_key"])
    ).fetchone()
    if row and row["completed"]:
        return jsonify({"error": "أكملتَ مهمة هذا الهدف اليوم بالفعل."}), 409
    db.execute(
        """INSERT INTO daily_picks(user_id, day, goal_key, challenge_id, completed) VALUES (?, ?, ?, ?, 0)
           ON CONFLICT(user_id, day, goal_key) DO UPDATE SET challenge_id = excluded.challenge_id""",
        (uid, today_str(), ch["goal_key"], cid),
    )
    db.commit()
    return jsonify({"challenge": challenge_dict(ch)})


@app.post("/api/usage")
@login_required
def api_save_usage():
    """حفظ ساعات استخدام الهاتف اليوم وجودته كما يدخلهما المستخدم.
    الجسم: {"hours": 3.5, "quality": "balanced"}  (quality اختياري)"""
    data = request.get_json(silent=True) or {}
    try:
        hours = round(float(data.get("hours")), 1)
    except (TypeError, ValueError):
        return jsonify({"error": "أدخل عدد الساعات رقماً."}), 400
    if not 0 <= hours <= 24:
        return jsonify({"error": "عدد الساعات يجب أن يكون بين 0 و24."}), 400
    quality = data.get("quality") or None
    if quality is not None and quality not in QUALITIES:
        return jsonify({"error": "قيمة جودة الاستخدام غير صحيحة."}), 400
    db = get_db()
    db.execute(
        "INSERT INTO usage_log(user_id, day, hours, quality) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id, day) DO UPDATE SET hours = excluded.hours, quality = excluded.quality",
        (current_user()["id"], today_str(), hours, quality),
    )
    db.commit()
    return jsonify({"hours": hours, "quality": quality})


@app.get("/api/progress")
@login_required
def api_progress():
    db = get_db()
    uid = current_user()["id"]
    week = week_days(db, uid)
    totals = db.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(points),0) AS pts FROM daily_picks WHERE user_id = ? AND completed = 1",
        (uid,),
    ).fetchone()
    week_done = sum(1 for d in week if d["completed"])
    history = db.execute(
        """SELECT p.day, c.title, p.points FROM daily_picks p
           JOIN challenges c ON c.id = p.challenge_id
           WHERE p.user_id = ? AND p.completed = 1 ORDER BY p.day DESC, p.completed_at DESC LIMIT 10""",
        (uid,),
    ).fetchall()
    return jsonify({
        "week": week,
        "week_done": week_done,
        "week_percent": round(week_done / 7 * 100),
        "streak": streak(db, uid),
        "total_completed": totals["n"],
        "points": totals["pts"],
        "history": [dict(h) for h in history],
        "usage": usage_summary(db, uid),
    })


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
