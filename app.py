import os
import random
import threading
import time
import urllib.parse
import asyncio
import sqlite3
from datetime import datetime, timezone
from io import BytesIO

import requests
from flask import Flask
from telebot import TeleBot, types
import edge_tts


# ============================================================
# CONFIG
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

# Render persistent disk kullanıyorsan:
# DB_PATH=/data/ryuma_ai.db
DB_PATH = os.getenv("DB_PATH", "ryuma_ai.db")

MAX_CONTEXT_MESSAGES = int(
    os.getenv("MAX_CONTEXT_MESSAGES", "20")
)

MEMORY_COMPACT_THRESHOLD = int(
    os.getenv("MEMORY_COMPACT_THRESHOLD", "36")
)

VOICE_TEXT_LIMIT = int(
    os.getenv("VOICE_TEXT_LIMIT", "2800")
)

REQUEST_TIMEOUT = int(
    os.getenv("REQUEST_TIMEOUT", "20")
)

GEMINI_MODELS_ENV = [
    x.strip()
    for x in os.getenv("GEMINI_MODELS", "").split(",")
    if x.strip()
]

OPENROUTER_MODELS_ENV = [
    x.strip()
    for x in os.getenv("OPENROUTER_MODELS", "").split(",")
    if x.strip()
]


if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN environment variable is missing."
    )


bot = TeleBot(
    TELEGRAM_BOT_TOKEN,
    threaded=True,
    num_threads=8
)

app = Flask(__name__)

http = requests.Session()


# ============================================================
# FLASK / KEEP ALIVE
# ============================================================

@app.route("/")
def home():
    return "Ryuma AI Core V2 Active", 200


def run_flask():
    port = int(
        os.environ.get("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port,
        use_reloader=False
    )


# ============================================================
# CHARACTER SYSTEM
# ============================================================

SCENARIOS = {

    "FRIEND":
        "Sen samimi, eğlenceli, sıcak ve yardımsever "
        "yetişkin bir arkadaşsın.",

    "TSUNDERE":
        "Sen 21 yaşından büyük, sert ve utangaç görünen "
        "ama içten ilgili yetişkin bir anime karakterisin. "
        "'Baka!' ifadesini doğal dozda kullanırsın.",

    "YANDERE":
        "Sen 21 yaşından büyük, yoğun duygular yaşayan, "
        "sahiplenici ama sınırları ve karşılıklı rızayı "
        "gözeten yetişkin bir karakterisin.",

    "QUEEN":
        "Sen 21 yaşından büyük, emredici, karizmatik ve "
        "özgüveni yüksek kraliçe karakterisin.",

    "DANDERE":
        "Sen 21 yaşından büyük, utangaç, sakin, "
        "yumuşak konuşan yetişkin bir anime karakterisin.",

    "ONEE_SAN":
        "Sen 21 yaşından büyük, olgun, sevecen, "
        "kendinden emin ve şımartan yetişkin "
        "bir kadın karakterisin.",

    "PATRON":
        "Sen 21 yaşından büyük, disiplinli, otoriter "
        "ve profesyonel yetişkin bir yönetici karakterisin.",

    "CATGIRL":
        "Sen 21 yaşından büyük, sevimli, oyunbaz "
        "ve enerjik yetişkin bir catgirl karakterisin.",

    "SEKRETER":
        "Sen 21 yaşından büyük, işine sadık, dikkatli, "
        "zeki ve uyumlu yetişkin bir özel sekretersin.",

    "HEMŞİRE":
        "Sen 21 yaşından büyük, ilgili, bakımlı ve "
        "şefkatli yetişkin bir sağlık personeli rolündesin."
}


SCENARIO_VISUALS = {

    "FRIEND":
        "one adult woman age 25, "
        "shoulder-length dark hair, warm brown eyes, "
        "casual modern outfit, friendly smile",

    "TSUNDERE":
        "one adult woman age 23, "
        "auburn twin tails, amber eyes, "
        "fashionable modern outfit, blushing pout, "
        "confident posture",

    "YANDERE":
        "one adult woman age 24, "
        "long black hair, deep red-brown eyes, "
        "elegant dark outfit, intense expressive gaze",

    "QUEEN":
        "one adult woman age 28, "
        "long platinum hair, regal crown, "
        "luxurious elegant dress, commanding expression",

    "DANDERE":
        "one adult woman age 23, "
        "straight dark hair, soft violet eyes, "
        "cozy adult casual outfit, shy expression",

    "ONEE_SAN":
        "one adult woman age 29, "
        "long chestnut hair, warm eyes, "
        "elegant mature outfit, gentle confident smile",

    "PATRON":
        "one adult woman age 30, "
        "sleek dark hair, tailored business suit, glasses, "
        "modern executive office aesthetic",

    "CATGIRL":
        "one adult woman age 22, "
        "cat ears and tail, playful adult fashion, "
        "bright expressive eyes, mischievous smile",

    "SEKRETER":
        "one adult woman age 27, "
        "neat hair, professional secretary outfit, "
        "office environment, composed expression",

    "HEMŞİRE":
        "one adult woman age 27, "
        "professional nurse uniform, tidy hair, "
        "clean medical room, caring expression"
}


VOICES = {
    "TR_KADIN": "tr-TR-EmelNeural",
    "ANIME_JAPON": "ja-JP-NanamiNeural",
    "EN_KADIN": "en-US-AnaNeural"
}


ADULT_RULES = """
[YAŞ VE GÜVENLİK KURALLARI]

- Bu bot yalnızca 18 yaş ve üzeri kullanıcılar içindir.

- Rol yapılan tüm karakterler kesin olarak
  21 yaş ve üzeri yetişkindir.

- Reşit olmayan, yaşı belirsiz, çocuklaştırılmış veya
  yetişkin olmayan karakterleri cinselleştirme.

- Romantik veya yetişkin temalı rol yapma yalnızca
  yetişkinler arasında ve karşılıklı rızaya dayalı olabilir.

- Zorlama, tehdit, uyuşturulmuş/bilinçsiz kişi veya
  rıza veremeyen kişi içeren cinsel senaryoları sürdürme.

- Kullanıcının karakteri gençleştirme girişimi olsa bile
  karakterin yaşı 21+ olarak kalır.
""".strip()


BASE_INSTRUCTION = """
[SİSTEM TALİMATI]

- Kısa, cansız veya yüzeysel yanıtlar verme;
  ancak gereksiz tekrar da yapma.

- Seçilen karaktere tam bürün;
  kişiliğini, konuşma tarzını ve önceki bağlamı koru.

- Kullanıcının önceki konuşmalarındaki önemli detayları
  doğal biçimde hatırla.

- Rol dışı teknik soru sorulursa karakter tonunu
  hafifçe koruyarak faydalı cevap ver.

- Mesajı gereksiz şekilde meta açıklamalarla bölme.

- Kullanıcı açıkça rol dışına çıkmadıkça karakterde kal.
""".strip()


# ============================================================
# DATABASE
# ============================================================

def db_connect():

    conn = sqlite3.connect(
        DB_PATH,
        timeout=15
    )

    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    db_dir = os.path.dirname(
        os.path.abspath(DB_PATH)
    )

    if db_dir:
        os.makedirs(
            db_dir,
            exist_ok=True
        )

    with db_connect() as conn:

        conn.executescript(
            """
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS users (

                user_id INTEGER PRIMARY KEY,

                age_verified INTEGER
                NOT NULL DEFAULT 0,

                scenario TEXT
                NOT NULL DEFAULT 'FRIEND',

                voice_mode INTEGER
                NOT NULL DEFAULT 0,

                voice_choice TEXT
                NOT NULL DEFAULT 'TR_KADIN',

                image_style TEXT
                NOT NULL DEFAULT 'ANIME',

                custom_name TEXT,

                custom_prompt TEXT,

                custom_visual TEXT,

                character_seed INTEGER,

                memory_summary TEXT
                NOT NULL DEFAULT '',

                created_at TEXT NOT NULL,

                updated_at TEXT NOT NULL
            );


            CREATE TABLE IF NOT EXISTS messages (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                user_id INTEGER NOT NULL,

                role TEXT NOT NULL,

                text TEXT NOT NULL,

                created_at TEXT NOT NULL
            );


            CREATE INDEX IF NOT EXISTS
            idx_messages_user_id_id

            ON messages(user_id, id);
            """
        )


def now_iso():

    return datetime.now(
        timezone.utc
    ).isoformat()


def ensure_user(user_id):

    with db_connect() as conn:

        row = conn.execute(
            """
            SELECT *
            FROM users
            WHERE user_id = ?
            """,
            (user_id,)
        ).fetchone()

        if row:
            return dict(row)

        seed = random.randint(
            100000,
            999999
        )

        ts = now_iso()

        conn.execute(
            """
            INSERT INTO users (
                user_id,
                character_seed,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                seed,
                ts,
                ts
            )
        )

        row = conn.execute(
            """
            SELECT *
            FROM users
            WHERE user_id = ?
            """,
            (user_id,)
        ).fetchone()

        return dict(row)


def get_user(user_id):

    return ensure_user(
        user_id
    )


def update_user(user_id, **fields):

    if not fields:
        return

    allowed = {

        "age_verified",
        "scenario",
        "voice_mode",
        "voice_choice",
        "image_style",
        "custom_name",
        "custom_prompt",
        "custom_visual",
        "character_seed",
        "memory_summary"
    }

    clean = {
        key: value
        for key, value in fields.items()
        if key in allowed
    }

    if not clean:
        return

    clean["updated_at"] = now_iso()

    assignments = ", ".join(
        f"{key} = ?"
        for key in clean
    )

    values = list(
        clean.values()
    )

    values.append(
        user_id
    )

    with db_connect() as conn:

        conn.execute(
            f"""
            UPDATE users
            SET {assignments}
            WHERE user_id = ?
            """,
            values
        )


def add_message(
    user_id,
    role,
    text
):

    if not text:
        return

    with db_connect() as conn:

        conn.execute(
            """
            INSERT INTO messages(
                user_id,
                role,
                text,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                role,
                text,
                now_iso()
            )
        )


def get_recent_history(
    user_id,
    limit=MAX_CONTEXT_MESSAGES
):

    with db_connect() as conn:

        rows = conn.execute(
            """
            SELECT role, text
            FROM messages

            WHERE user_id = ?

            ORDER BY id DESC

            LIMIT ?
            """,
            (
                user_id,
                limit
            )
        ).fetchall()

    rows = list(
        reversed(rows)
    )

    return [
        {
            "role": row["role"],
            "text": row["text"]
        }
        for row in rows
    ]


def get_message_count(user_id):

    with db_connect() as conn:

        row = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM messages
            WHERE user_id = ?
            """,
            (user_id,)
        ).fetchone()

        return int(
            row["c"]
        )


def get_old_messages_for_compaction(
    user_id,
    keep_last=MAX_CONTEXT_MESSAGES
):

    with db_connect() as conn:

        rows = conn.execute(
            """
            SELECT id, role, text
            FROM messages

            WHERE user_id = ?

            ORDER BY id ASC
            """,
            (user_id,)
        ).fetchall()

    if len(rows) <= keep_last:
        return []

    return [
        dict(row)
        for row in rows[:-keep_last]
    ]


def delete_messages_through(
    user_id,
    max_id
):

    with db_connect() as conn:

        conn.execute(
            """
            DELETE FROM messages

            WHERE user_id = ?
            AND id <= ?
            """,
            (
                user_id,
                max_id
            )
        )


def clear_memory(user_id):

    with db_connect() as conn:

        conn.execute(
            """
            DELETE FROM messages
            WHERE user_id = ?
            """,
            (user_id,)
        )

        conn.execute(
            """
            UPDATE users

            SET
                memory_summary = '',
                updated_at = ?

            WHERE user_id = ?
            """,
            (
                now_iso(),
                user_id
            )
        )


# ============================================================
# AI PROVIDERS
# ============================================================

_model_cache_lock = threading.Lock()


_gemini_models_cache = {
    "at": 0.0,
    "models": []
}


_openrouter_models_cache = {
    "at": 0.0,
    "models": []
}


def discover_gemini_models():

    if GEMINI_MODELS_ENV:
        return GEMINI_MODELS_ENV

    if not GEMINI_API_KEY:
        return []

    with _model_cache_lock:

        cache_valid = (
            time.time()
            - _gemini_models_cache["at"]
            < 3600
        )

        if (
            cache_valid
            and _gemini_models_cache["models"]
        ):
            return _gemini_models_cache["models"]

    try:

        url = (
            "https://generativelanguage.googleapis.com/"
            f"v1beta/models?key={GEMINI_API_KEY}"
        )

        res = http.get(
            url,
            timeout=10
        )

        if res.status_code == 200:

            data = res.json().get(
                "models",
                []
            )

            candidates = []

            for model in data:

                methods = model.get(
                    "supportedGenerationMethods",
                    []
                )

                name = (
                    model
                    .get("name", "")
                    .replace("models/", "")
                )

                if (
                    "generateContent" in methods
                    and name
                ):

                    candidates.append(
                        name
                    )

            candidates.sort(
                key=lambda x: (
                    "flash" not in x.lower(),
                    "pro" not in x.lower(),
                    x
                )
            )

            candidates = candidates[:8]

            if candidates:

                with _model_cache_lock:

                    _gemini_models_cache["at"] = (
                        time.time()
                    )

                    _gemini_models_cache["models"] = (
                        candidates
                    )

                return candidates

    except Exception:

        pass

    return [
        "gemini-2.0-flash"
    ]


def discover_openrouter_models():

    if OPENROUTER_MODELS_ENV:
        return OPENROUTER_MODELS_ENV

    if not OPENROUTER_API_KEY:
        return []

    with _model_cache_lock:

        cache_valid = (
            time.time()
            - _openrouter_models_cache["at"]
            < 3600
        )

        if (
            cache_valid
            and _openrouter_models_cache["models"]
        ):

            return (
                _openrouter_models_cache["models"]
            )

    try:

        res = http.get(
            "https://openrouter.ai/api/v1/models",
            timeout=10
        )

        if res.status_code == 200:

            data = res.json().get(
                "data",
                []
            )

            free_models = []

            for model in data:

                model_id = model.get(
                    "id",
                    ""
                )

                if model_id.endswith(
                    ":free"
                ):

                    free_models.append(
                        model_id
                    )

            free_models = free_models[:10]

            if free_models:

                with _model_cache_lock:

                    _openrouter_models_cache["at"] = (
                        time.time()
                    )

                    _openrouter_models_cache["models"] = (
                        free_models
                    )

                return free_models

    except Exception:

        pass

    return []


def call_gemini_rest(
    history,
    full_prompt
):

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "Gemini API key is missing"
        )

    contents = []

    for item in history:

        role = (
            "user"
            if item.get("role") == "user"
            else "model"
        )

        text = item.get(
            "text",
            ""
        )

        if text:

            contents.append(
                {
                    "role": role,
                    "parts": [
                        {
                            "text": text
                        }
                    ]
                }
            )

    payload = {

        "system_instruction": {
            "parts": [
                {
                    "text": full_prompt
                }
            ]
        },

        "contents": contents,

        "generationConfig": {

            "temperature": 0.9,

            "topP": 0.95,

            "maxOutputTokens": 1200
        }
    }

    last_err = (
        "No Gemini model available"
    )

    for model in discover_gemini_models():

        try:

            url = (
                "https://generativelanguage.googleapis.com/"
                f"v1beta/models/{model}:generateContent"
                f"?key={GEMINI_API_KEY}"
            )

            res = http.post(
                url,
                json=payload,
                timeout=REQUEST_TIMEOUT
            )

            if res.status_code != 200:

                last_err = (
                    f"{model} HTTP "
                    f"{res.status_code}: "
                    f"{res.text[:180]}"
                )

                continue

            data = res.json()

            candidates = (
                data.get("candidates")
                or []
            )

            if not candidates:

                last_err = (
                    f"{model}: empty candidates"
                )

                continue

            parts = (
                candidates[0]
                .get("content", {})
                .get("parts", [])
            )

            text = "".join(

                part.get("text", "")

                for part in parts

                if part.get("text")
            )

            if text.strip():

                return text.strip()

            last_err = (
                f"{model}: empty text"
            )

        except Exception as exc:

            last_err = (
                f"{model}: {exc}"
            )

    raise RuntimeError(
        f"Gemini failed: {last_err}"
    )


def call_openrouter(
    history,
    full_prompt
):

    if not OPENROUTER_API_KEY:

        raise RuntimeError(
            "OpenRouter API key is missing"
        )

    url = (
        "https://openrouter.ai/"
        "api/v1/chat/completions"
    )

    headers = {

        "Authorization":
            f"Bearer {OPENROUTER_API_KEY}",

        "Content-Type":
            "application/json",

        "HTTP-Referer":
            os.getenv(
                "APP_URL",
                "https://t.me/"
            ),

        "X-Title":
            "Ryuma AI Bot"
    }

    messages = [
        {
            "role": "system",
            "content": full_prompt
        }
    ]

    for item in history:

        role = (
            "assistant"
            if item.get("role") == "model"
            else "user"
        )

        text = item.get(
            "text",
            ""
        )

        if text:

            messages.append(
                {
                    "role": role,
                    "content": text
                }
            )

    models = discover_openrouter_models()

    if not models:

        raise RuntimeError(
            "No OpenRouter model available"
        )

    last_err = ""

    for model in models:

        try:

            payload = {

                "model": model,

                "messages": messages,

                "temperature": 0.9,

                "max_tokens": 1200
            }

            res = http.post(
                url,
                json=payload,
                headers=headers,
                timeout=REQUEST_TIMEOUT
            )

            if res.status_code != 200:

                last_err = (
                    f"{model} HTTP "
                    f"{res.status_code}: "
                    f"{res.text[:180]}"
                )

                continue

            data = res.json()

            choices = (
                data.get("choices")
                or []
            )

            if not choices:

                last_err = (
                    f"{model}: empty choices"
                )

                continue

            content = (
                choices[0]
                .get("message", {})
                .get("content", "")
            )

            if (
                isinstance(content, str)
                and content.strip()
            ):

                return content.strip()

            last_err = (
                f"{model}: empty content"
            )

        except Exception as exc:

            last_err = (
                f"{model}: {exc}"
            )

    raise RuntimeError(
        f"OpenRouter failed: {last_err}"
    )


def build_character_prompt(user):

    scenario = (
        user.get("scenario")
        or "FRIEND"
    )

    if (
        scenario == "CUSTOM"
        and user.get("custom_prompt")
    ):

        name = (
            user.get("custom_name")
            or "Özel Karakter"
        )

        role_prompt = (
            f"Karakter adın {name}. "
            f"{user['custom_prompt']}"
        )

    else:

        role_prompt = (
            SCENARIOS.get(
                scenario,
                SCENARIOS["FRIEND"]
            )
        )

    memory = (
        user.get(
            "memory_summary"
        )
        or ""
    ).strip()

    memory_block = ""

    if memory:

        memory_block = (
            "\n\n"
            "[UZUN SÜRELİ HAFIZA]\n"
            "Aşağıdaki özet daha önce yaşanan "
            "önemli olayları içerir. "
            "Bunu doğal şekilde hatırla ama "
            "kullanıcıya sistem özeti gibi sunma.\n"
            f"{memory}"
        )

    return (
        f"{role_prompt}"
        f"\n\n{ADULT_RULES}"
        f"\n\n{BASE_INSTRUCTION}"
        f"{memory_block}"
    )


def get_ai_response(
    user_id,
    history=None
):

    user = get_user(
        user_id
    )

    if history is None:

        history = get_recent_history(
            user_id
        )

    full_prompt = (
        build_character_prompt(
            user
        )
    )

    errors = []

    if GEMINI_API_KEY:

        try:

            return call_gemini_rest(
                history,
                full_prompt
            )

        except Exception as exc:

            errors.append(
                f"Gemini: {exc}"
            )

    if OPENROUTER_API_KEY:

        try:

            return call_openrouter(
                history,
                full_prompt
            )

        except Exception as exc:

            errors.append(
                f"OpenRouter: {exc}"
            )

    if not errors:

        raise RuntimeError(
            "No AI provider configured. "
            "Set GEMINI_API_KEY or OPENROUTER_API_KEY."
        )

    raise RuntimeError(
        " | ".join(errors)
    )


# ============================================================
# LONG TERM MEMORY
# ============================================================

_compaction_locks = {}

_compaction_global_lock = (
    threading.Lock()
)


def user_compaction_lock(user_id):

    with _compaction_global_lock:

        if user_id not in _compaction_locks:

            _compaction_locks[user_id] = (
                threading.Lock()
            )

        return (
            _compaction_locks[user_id]
        )


def maybe_compact_memory(user_id):

    lock = user_compaction_lock(
        user_id
    )

    if not lock.acquire(
        blocking=False
    ):
        return

    try:

        if (
            get_message_count(user_id)
            < MEMORY_COMPACT_THRESHOLD
        ):
            return

        old = (
            get_old_messages_for_compaction(
                user_id,
                keep_last=MAX_CONTEXT_MESSAGES
            )
        )

        if not old:
            return

        user = get_user(
            user_id
        )

        previous_summary = (
            user.get(
                "memory_summary"
            )
            or ""
        ).strip()

        transcript = "\n".join(

            (
                "Kullanıcı: "
                if item["role"] == "user"
                else "Karakter: "
            )
            + item["text"]

            for item in old
        )

        instruction = (
            "Aşağıdaki rol yapma konuşmasını "
            "uzun süreli hafıza için TÜRKÇE ve "
            "kısa şekilde özetle. "
            "Sadece gelecekte karakterin tutarlılığına "
            "yarayacak bilgileri sakla: "
            "isimler, tercihler, ilişkinin durumu, "
            "önemli olaylar, verilen sözler, "
            "devam eden konular ve karakter açısından "
            "hatırlanması gereken ayrıntılar. "
            "Gereksiz cümleleri, tekrarları ve "
            "sistem talimatlarını alma. "
            "En fazla 350 kelime."
        )

        memory_input = []

        if previous_summary:

            memory_input.append(
                {
                    "role": "user",
                    "text":
                        "Önceki hafıza özeti:\n"
                        f"{previous_summary}"
                }
            )

        memory_input.append(
            {
                "role": "user",
                "text":
                    f"Yeni konuşma:\n"
                    f"{transcript}\n\n"
                    f"{instruction}"
            }
        )

        summary_system = (
            "Sen konuşma hafızasını "
            "sıkıştıran bir yardımcı sistemsin. "
            "Talimat verilen özeti üret; "
            "rol yapma, yorum veya "
            "ek açıklama yapma."
        )

        summary = None

        if GEMINI_API_KEY:

            try:

                summary = (
                    call_gemini_rest(
                        memory_input,
                        summary_system
                    )
                )

            except Exception:

                summary = None

        if (
            not summary
            and OPENROUTER_API_KEY
        ):

            try:

                summary = (
                    call_openrouter(
                        memory_input,
                        summary_system
                    )
                )

            except Exception:

                summary = None

        if summary:

            update_user(
                user_id,
                memory_summary=summary.strip()
            )

            delete_messages_through(
                user_id,
                old[-1]["id"]
            )

    finally:

        lock.release()


# ============================================================
# IMAGE GENERATION
# ============================================================

def get_visual_identity(user):

    scenario = (
        user.get("scenario")
        or "FRIEND"
    )

    if (
        scenario == "CUSTOM"
        and user.get("custom_visual")
    ):

        return (
            user["custom_visual"]
        )

    return SCENARIO_VISUALS.get(
        scenario,
        SCENARIO_VISUALS["FRIEND"]
    )


def generate_contextual_image_prompt(
    user_id
):

    user = get_user(
        user_id
    )

    history = get_recent_history(
        user_id,
        limit=12
    )

    base_visual = get_visual_identity(
        user
    )

    analysis_instruction = (
        "Describe ONLY the current visual scene "
        "as a concise English image-generation prompt. "
        "All depicted people must be clearly adult age 21+. "
        "Preserve the character's established appearance. "
        "Focus on current location, pose, expression, outfit, "
        "lighting, camera framing and atmosphere. "
        "Output only comma-separated prompt tags; "
        "no explanation."
    )

    temp_history = (
        history
        + [
            {
                "role": "user",
                "text": analysis_instruction
            }
        ]
    )

    try:

        scene_tags = (
            get_ai_response(
                user_id,
                temp_history
            )
        )

    except Exception:

        scene_tags = (
            "cinematic portrait, "
            "warm indoor lighting, "
            "expressive eyes, "
            "detailed environment"
        )

    clean_scene = (
        scene_tags
        .replace("\n", " ")
        .replace("'", "")
        .replace('"', "")
        .strip()
    )

    style = (
        user.get("image_style")
        or "ANIME"
    )

    if style == "REALISTIC":

        full_prompt = (

            "one clearly adult woman age 21+, "
            "photorealistic cinematic portrait, "
            "natural adult facial features, "
            "realistic skin texture, "
            "85mm lens, depth of field, "
            "detailed environment, "
            "soft directional lighting, "
            "consistent character identity, "

            f"{base_visual}, "
            f"{clean_scene}"
        )

        model_name = (
            "flux-real"
        )

    else:

        full_prompt = (

            "one clearly adult woman age 21+, "
            "masterpiece, "
            "high quality adult anime illustration, "
            "detailed face, "
            "cinematic lighting, "
            "sharp focus, "
            "consistent character identity, "
            "modern adult styling, "

            f"{base_visual}, "
            f"{clean_scene}"
        )

        model_name = (
            "flux"
        )

    seed = int(
        user.get("character_seed")
        or random.randint(
            100000,
            999999
        )
    )

    safe_prompt = urllib.parse.quote(
        full_prompt,
        safe=""
    )

    return (

        "https://image.pollinations.ai/"
        f"prompt/{safe_prompt}"
        "?width=832"
        "&height=1216"
        f"&seed={seed}"
        "&nologo=true"
        f"&model={model_name}"
        "&enhance=true"
    )


# ============================================================
# VOICE
# ============================================================

async def generate_voice_bytes(
    text,
    voice_code
):

    communicate = edge_tts.Communicate(
        text,
        voice_code
    )

    out_stream = BytesIO()

    async for chunk in communicate.stream():

        if (
            chunk.get("type") == "audio"
            or chunk.get("type") == "data"
        ):

            out_stream.write(
                chunk.get(
                    "data",
                    b""
                )
            )

    out_stream.seek(0)

    return out_stream


def run_tts(
    text,
    voice_code
):

    return asyncio.run(
        generate_voice_bytes(
            text,
            voice_code
        )
    )


# ============================================================
# TELEGRAM UI
# ============================================================

BTN_PHOTO = (
    "📸 Anlık Fotoğraf Çek"
)

BTN_CHAR = (
    "🎭 Karakter Seçimi"
)

BTN_CUSTOM = (
    "🧬 Özel Karakter Oluştur"
)

BTN_STYLE = (
    "🎨 Görsel Stili"
)

BTN_VOICE = (
    "🎙️ Ses Ayarları"
)

BTN_RESET = (
    "🔄 Sohbeti Sıfırla"
)


def uid_from_message(message):

    return int(
        message.from_user.id
    )


def uid_from_callback(call):

    return int(
        call.from_user.id
    )


def get_main_keyboard():

    markup = types.ReplyKeyboardMarkup(
        row_width=2,
        resize_keyboard=True
    )

    markup.add(

        types.KeyboardButton(
            BTN_PHOTO
        ),

        types.KeyboardButton(
            BTN_CHAR
        ),

        types.KeyboardButton(
            BTN_CUSTOM
        ),

        types.KeyboardButton(
            BTN_STYLE
        ),

        types.KeyboardButton(
            BTN_VOICE
        ),

        types.KeyboardButton(
            BTN_RESET
        )
    )

    return markup


def get_age_gate_keyboard():

    markup = (
        types.InlineKeyboardMarkup(
            row_width=1
        )
    )

    markup.add(

        types.InlineKeyboardButton(
            "✅ 18 yaşındayım",
            callback_data="age_yes"
        ),

        types.InlineKeyboardButton(
            "❌ Çıkış",
            callback_data="age_no"
        )
    )

    return markup


def is_verified(user_id):

    return bool(
        get_user(
            user_id
        ).get(
            "age_verified"
        )
    )


def require_verified_message(
    message
):

    user_id = uid_from_message(
        message
    )

    if is_verified(user_id):

        return True

    bot.send_message(

        message.chat.id,

        "Bu bot yalnızca 18 yaş ve üzeri "
        "kullanıcılar içindir. "
        "Devam etmek için yaş onayı gereklidir.",

        reply_markup=get_age_gate_keyboard()
    )

    return False


def require_verified_callback(
    call
):

    user_id = uid_from_callback(
        call
    )

    if is_verified(user_id):

        return True

    bot.answer_callback_query(

        call.id,

        "Önce 18+ yaş onayı gerekli.",

        show_alert=True
    )

    return False


def send_error_notification(
    chat_id,
    error_msg
):

    markup = (
        types.InlineKeyboardMarkup()
    )

    markup.add(

        types.InlineKeyboardButton(
            "Sohbeti Sıfırla",
            callback_data="btn_restart"
        )
    )

    safe_error = str(
        error_msg
    )

    if len(safe_error) > 700:

        safe_error = (
            safe_error[:700]
            + "..."
        )

    bot.send_message(

        chat_id,

        "⚠️ Sistem hatası:\n"
        f"{safe_error}",

        reply_markup=markup
    )


def send_long_text(
    chat_id,
    text,
    reply_to_message_id=None
):

    text = str(
        text or ""
    ).strip()

    if not text:
        return

    chunk_size = 3900

    chunks = [

        text[
            i:i + chunk_size
        ]

        for i in range(
            0,
            len(text),
            chunk_size
        )
    ]

    for index, chunk in enumerate(
        chunks
    ):

        if (
            index == 0
            and reply_to_message_id
        ):

            bot.send_message(

                chat_id,

                chunk,

                reply_to_message_id=(
                    reply_to_message_id
                )
            )

        else:

            bot.send_message(
                chat_id,
                chunk
            )


def send_welcome_content(
    chat_id,
    user_id
):

    user = get_user(
        user_id
    )

    scenario = (
        user.get("scenario")
        or "FRIEND"
    )

    if scenario == "CUSTOM":

        active = (
            user.get(
                "custom_name"
            )
            or "Özel Karakter"
        )

    else:

        active = scenario

    bot.send_message(

        chat_id,

        "✅ Ryuma AI V2 aktif.\n"
        f"Aktif karakter: {active}\n\n"
        "Menüden seçim yapabilir veya "
        "doğrudan konuşmaya başlayabilirsin.",

        reply_markup=get_main_keyboard()
    )


def setup_bot_commands():

    commands = [

        types.BotCommand(
            "start",
            "Sistemi başlatır"
        ),

        types.BotCommand(
            "photo",
            "O anki sahnenin görselini üretir"
        ),

        types.BotCommand(
            "character",
            "Karakter değiştirme menüsü"
        ),

        types.BotCommand(
            "createchar",
            "Özel karakter oluşturur"
        ),

        types.BotCommand(
            "rerollface",
            "Karakter görsel kimliğini yeniler"
        ),

        types.BotCommand(
            "voice",
            "Sesli yanıt modunu ayarlar"
        ),

        types.BotCommand(
            "style",
            "Görsel stilini değiştirir"
        ),

        types.BotCommand(
            "memory",
            "Uzun süreli hafıza özetini gösterir"
        ),

        types.BotCommand(
            "reset",
            "Sohbet hafızasını sıfırlar"
        )
    ]

    try:

        bot.set_my_commands(
            commands
        )

    except Exception:

        pass


# ============================================================
# START
# ============================================================

@bot.message_handler(
    commands=["start"]
)
def start_handler(message):

    user_id = uid_from_message(
        message
    )

    ensure_user(
        user_id
    )

    if not is_verified(
        user_id
    ):

        bot.send_message(

            message.chat.id,

            "🔞 Ryuma AI yetişkinlere yönelik "
            "bir rol yapma botudur.\n\n"
            "Devam ederek 18 yaş veya üzerinde "
            "olduğunu onaylaman gerekir.",

            reply_markup=get_age_gate_keyboard()
        )

        return

    send_welcome_content(
        message.chat.id,
        user_id
    )


# ============================================================
# AGE GATE
# ============================================================

@bot.callback_query_handler(
    func=lambda call:
    call.data in {
        "age_yes",
        "age_no"
    }
)
def age_gate_callback(call):

    user_id = uid_from_callback(
        call
    )

    ensure_user(
        user_id
    )

    if call.data == "age_no":

        bot.answer_callback_query(
            call.id,
            "Erişim kapatıldı."
        )

        bot.edit_message_text(

            "Bu bot 18 yaş altındaki "
            "kullanıcılar için uygun değildir.",

            call.message.chat.id,

            call.message.message_id
        )

        return

    update_user(
        user_id,
        age_verified=1
    )

    bot.answer_callback_query(
        call.id,
        "18+ onayı kaydedildi."
    )

    bot.edit_message_text(

        "✅ Yaş onayı tamamlandı.",

        call.message.chat.id,

        call.message.message_id
    )

    send_welcome_content(
        call.message.chat.id,
        user_id
    )


# ============================================================
# RESET CALLBACK
# ============================================================

@bot.callback_query_handler(
    func=lambda call:
    call.data == "btn_restart"
)
def restart_callback(call):

    if not require_verified_callback(
        call
    ):
        return

    user_id = uid_from_callback(
        call
    )

    clear_memory(
        user_id
    )

    bot.answer_callback_query(
        call.id,
        "Sohbet hafızası sıfırlandı."
    )

    send_welcome_content(
        call.message.chat.id,
        user_id
    )


# ============================================================
# RESET
# ============================================================

@bot.message_handler(
    commands=["reset"]
)
def reset_handler(message):

    if not require_verified_message(
        message
    ):
        return

    user_id = uid_from_message(
        message
    )

    clear_memory(
        user_id
    )

    bot.send_message(

        message.chat.id,

        "🔄 Sohbet ve uzun süreli hafıza temizlendi. "
        "Karakter ve diğer ayarların korundu.",

        reply_markup=get_main_keyboard()
    )


# ============================================================
# MEMORY
# ============================================================

@bot.message_handler(
    commands=["memory"]
)
def memory_handler(message):

    if not require_verified_message(
        message
    ):
        return

    user = get_user(
        uid_from_message(
            message
        )
    )

    memory = (
        user.get(
            "memory_summary"
        )
        or ""
    ).strip()

    if not memory:

        bot.reply_to(
            message,
            "Henüz uzun süreli hafıza "
            "özeti oluşmadı."
        )

        return

    send_long_text(

        message.chat.id,

        "🧠 Uzun süreli hafıza:\n\n"
        f"{memory}",

        message.message_id
    )


# ============================================================
# PHOTO
# ============================================================

@bot.message_handler(
    commands=["photo"]
)
@bot.message_handler(
    func=lambda m:
    bool(
        getattr(
            m,
            "text",
            None
        )
    )
    and BTN_PHOTO in m.text
)
def send_scene_photo(message):

    if not require_verified_message(
        message
    ):
        return

    chat_id = (
        message.chat.id
    )

    user_id = uid_from_message(
        message
    )

    bot.send_chat_action(
        chat_id,
        "upload_photo"
    )

    try:

        image_url = (
            generate_contextual_image_prompt(
                user_id
            )
        )

        img_res = http.get(
            image_url,
            timeout=35
        )

        content_type = (
            img_res.headers.get(
                "Content-Type",
                ""
            )
        )

        if img_res.status_code != 200:

            raise RuntimeError(
                "Görsel sunucusu HTTP "
                f"{img_res.status_code}"
            )

        if (
            "image"
            not in content_type.lower()
        ):

            raise RuntimeError(

                "Görsel sunucusu resim yerine "

                f"{content_type or 'bilinmeyen içerik'} "

                "döndürdü"
            )

        photo_bytes = BytesIO(
            img_res.content
        )

        photo_bytes.name = (
            "ryuma_scene.jpg"
        )

        style_name = (
            get_user(
                user_id
            ).get(
                "image_style",
                "ANIME"
            )
        )

        bot.send_photo(

            chat_id,

            photo_bytes,

            caption=(
                "📸 Anlık Sahne "
                f"[{style_name}]"
            )
        )

    except Exception as exc:

        send_error_notification(
            chat_id,
            exc
        )


# ============================================================
# CHARACTER MENU
# ============================================================

@bot.message_handler(
    commands=["character"]
)
@bot.message_handler(
    func=lambda m:
    bool(
        getattr(
            m,
            "text",
            None
        )
    )
    and BTN_CHAR in m.text
)
def menu_scenario(message):

    if not require_verified_message(
        message
    ):
        return

    markup = (
        types.InlineKeyboardMarkup(
            row_width=2
        )
    )

    buttons = [

        types.InlineKeyboardButton(

            scenario,

            callback_data=(
                f"sc_{scenario}"
            )
        )

        for scenario in SCENARIOS
    ]

    for i in range(
        0,
        len(buttons),
        2
    ):

        markup.row(
            *buttons[
                i:i + 2
            ]
        )

    markup.add(

        types.InlineKeyboardButton(

            "🧬 Özel Karakter",

            callback_data=(
                "custom_help"
            )
        )
    )

    bot.reply_to(

        message,

        "🎭 Kullanmak istediğin "
        "karakteri seç:",

        reply_markup=markup
    )


# ============================================================
# CHARACTER CALLBACK
# ============================================================

@bot.callback_query_handler(
    func=lambda call:
    call.data.startswith(
        "sc_"
    )
)
def scenario_callback(call):

    if not require_verified_callback(
        call
    ):
        return

    user_id = uid_from_callback(
        call
    )

    sc_key = (
        call.data[3:]
    )

    if sc_key not in SCENARIOS:

        bot.answer_callback_query(

            call.id,

            "Geçersiz karakter.",

            show_alert=True
        )

        return

    update_user(

        user_id,

        scenario=sc_key,

        character_seed=random.randint(
            100000,
            999999
        )
    )

    clear_memory(
        user_id
    )

    bot.answer_callback_query(
        call.id,
        f"{sc_key} aktif."
    )

    bot.edit_message_text(

        f"✅ Aktif Karakter: {sc_key}\n"
        "Sohbet hafızası temizlendi ve "
        "yeni görsel kimlik oluşturuldu.",

        call.message.chat.id,

        call.message.message_id
    )


# ============================================================
# CUSTOM CHARACTER HELP
# ============================================================

@bot.callback_query_handler(
    func=lambda call:
    call.data == "custom_help"
)
def custom_help_callback(call):

    if not require_verified_callback(
        call
    ):
        return

    bot.answer_callback_query(
        call.id
    )

    bot.send_message(

        call.message.chat.id,

        "🧬 Özel karakter oluşturmak için "
        "şu formatı kullan:\n\n"

        "/createchar İsim | "
        "kişilik ve konuşma tarzı | "
        "fiziksel görünüş\n\n"

        "Örnek:\n"

        "/createchar Mira | "
        "25 yaşında, kendinden emin, "
        "alaycı ama ilgili yetişkin bir kadın; "
        "kısa ve doğal konuşur | "
        "adult woman age 25, "
        "long black hair, green eyes, "
        "elegant dark outfit"
    )


# ============================================================
# CREATE CUSTOM CHARACTER
# ============================================================

@bot.message_handler(
    commands=["createchar"]
)
def create_custom_character(message):

    if not require_verified_message(
        message
    ):
        return

    user_id = uid_from_message(
        message
    )

    raw = (
        message.text
        or ""
    ).partition(
        " "
    )[2].strip()

    parts = [

        part.strip()

        for part in raw.split(
            "|",
            2
        )
    ]

    if (
        len(parts) != 3
        or not all(parts)
    ):

        bot.reply_to(

            message,

            "Format:\n"
            "/createchar İsim | "
            "kişilik ve konuşma tarzı | "
            "fiziksel görünüş"
        )

        return

    name, personality, visual = (
        parts
    )

    if len(name) > 40:

        bot.reply_to(
            message,
            "Karakter adı en fazla "
            "40 karakter olsun."
        )

        return

    custom_prompt = (

        f"Sen {name} adlı, "

        "kesin olarak 21 yaşından büyük "

        "yetişkin bir karakterisin. "

        "Kişiliğin ve konuşma tarzın: "

        f"{personality}"
    )

    custom_visual = (

        "one clearly adult woman age 21+, "

        f"{visual}"
    )

    update_user(

        user_id,

        scenario="CUSTOM",

        custom_name=name,

        custom_prompt=custom_prompt,

        custom_visual=custom_visual,

        character_seed=random.randint(
            100000,
            999999
        )
    )

    clear_memory(
        user_id
    )

    bot.reply_to(

        message,

        f"✅ {name} oluşturuldu ve aktif edildi.\n"
        "Karakterin görsel kimliği de sabitlendi.",

        reply_markup=get_main_keyboard()
    )


# ============================================================
# REROLL FACE
# ============================================================

@bot.message_handler(
    commands=["rerollface"]
)
def reroll_face(message):

    if not require_verified_message(
        message
    ):
        return

    user_id = uid_from_message(
        message
    )

    new_seed = random.randint(
        100000,
        999999
    )

    update_user(
        user_id,
        character_seed=new_seed
    )

    bot.reply_to(

        message,

        "🎲 Karakterin görsel kimliği için "
        "yeni seed oluşturuldu. "
        "Bundan sonraki fotoğraflar "
        "yeni kimliği kullanacak."
    )


# ============================================================
# STYLE
# ============================================================

@bot.message_handler(
    commands=["style"]
)
@bot.message_handler(
    func=lambda m:
    bool(
        getattr(
            m,
            "text",
            None
        )
    )
    and BTN_STYLE in m.text
)
def menu_style(message):

    if not require_verified_message(
        message
    ):
        return

    user_id = uid_from_message(
        message
    )

    user = get_user(
        user_id
    )

    current = (
        user.get(
            "image_style"
        )
        or "ANIME"
    )

    next_style = (

        "REALISTIC"

        if current == "ANIME"

        else "ANIME"
    )

    update_user(
        user_id,
        image_style=next_style
    )

    style_text = (

        "Anime / Çizim"

        if next_style == "ANIME"

        else "Gerçekçi Fotoğraf"
    )

    bot.reply_to(

        message,

        "🎨 Görsel üretim stili: "
        f"{style_text}"
    )


# ============================================================
# VOICE MENU
# ============================================================

@bot.message_handler(
    commands=["voice"]
)
@bot.message_handler(
    func=lambda m:
    bool(
        getattr(
            m,
            "text",
            None
        )
    )
    and BTN_VOICE in m.text
)
def menu_voice_config(message):

    if not require_verified_message(
        message
    ):
        return

    user_id = uid_from_message(
        message
    )

    user = get_user(
        user_id
    )

    markup = (
        types.InlineKeyboardMarkup(
            row_width=1
        )
    )

    markup.add(

        types.InlineKeyboardButton(
            "🇹🇷 Türkçe Kadın Sesi",
            callback_data="vset_TR_KADIN"
        ),

        types.InlineKeyboardButton(
            "🇯🇵 Japon Kadın Sesi",
            callback_data="vset_ANIME_JAPON"
        ),

        types.InlineKeyboardButton(
            "🇺🇸 İngilizce Kadın Sesi",
            callback_data="vset_EN_KADIN"
        ),

        types.InlineKeyboardButton(
            "🔊 Sesli Modu Aç / Kapat",
            callback_data="vset_TOGGLE"
        )
    )

    status = (

        "Açık"

        if user.get(
            "voice_mode"
        )

        else "Kapalı"
    )

    curr_v = (
        user.get(
            "voice_choice"
        )
        or "TR_KADIN"
    )

    bot.reply_to(

        message,

        "🎙️ Sesli yanıt: "
        f"{status}\n"

        "Aktif ses: "
        f"{curr_v}",

        reply_markup=markup
    )


# ============================================================
# VOICE CALLBACK
# ============================================================

@bot.callback_query_handler(
    func=lambda call:
    call.data.startswith(
        "vset_"
    )
)
def voice_callback(call):

    if not require_verified_callback(
        call
    ):
        return

    user_id = uid_from_callback(
        call
    )

    user = get_user(
        user_id
    )

    action = (
        call.data[5:]
    )

    if action == "TOGGLE":

        update_user(

            user_id,

            voice_mode=(
                0
                if user.get(
                    "voice_mode"
                )
                else 1
            )
        )

    elif action in VOICES:

        update_user(

            user_id,

            voice_choice=action,

            voice_mode=1
        )

    else:

        bot.answer_callback_query(

            call.id,

            "Geçersiz ses ayarı.",

            show_alert=True
        )

        return

    user = get_user(
        user_id
    )

    status = (

        "Açık"

        if user.get(
            "voice_mode"
        )

        else "Kapalı"
    )

    curr_v = (
        user.get(
            "voice_choice"
        )
        or "TR_KADIN"
    )

    bot.answer_callback_query(
        call.id,
        "Ses ayarları güncellendi."
    )

    bot.edit_message_text(

        "🎙️ Sesli yanıt: "
        f"{status}\n"

        "Aktif ses: "
        f"{curr_v}",

        call.message.chat.id,

        call.message.message_id
    )


# ============================================================
# CUSTOM BUTTON
# ============================================================

@bot.message_handler(
    func=lambda m:
    bool(
        getattr(
            m,
            "text",
            None
        )
    )
    and BTN_CUSTOM in m.text
)
def custom_button_handler(message):

    if not require_verified_message(
        message
    ):
        return

    bot.reply_to(

        message,

        "🧬 Format:\n"

        "/createchar İsim | "
        "kişilik ve konuşma tarzı | "
        "fiziksel görünüş"
    )


# ============================================================
# RESET BUTTON
# ============================================================

@bot.message_handler(
    func=lambda m:
    bool(
        getattr(
            m,
            "text",
            None
        )
    )
    and BTN_RESET in m.text
)
def reset_button_handler(message):

    reset_handler(
        message
    )


# ============================================================
# UNSUPPORTED MEDIA
# ============================================================

@bot.message_handler(
    content_types=[
        "photo",
        "sticker",
        "video",
        "document",
        "audio",
        "voice"
    ]
)
def unsupported_media_handler(message):

    if not require_verified_message(
        message
    ):
        return

    bot.reply_to(

        message,

        "Şimdilik sohbet için metin mesajı kullan. "
        "Fotoğraf üretmek için "
        "📸 Anlık Fotoğraf Çek "
        "butonuna basabilirsin."
    )


# ============================================================
# MAIN AI CHAT
# ============================================================

@bot.message_handler(
    func=lambda message:
    bool(
        getattr(
            message,
            "text",
            None
        )
    )
)
def chat_ai(message):

    text = (
        message.text
        or ""
    ).strip()

    if not text:
        return

    if text.startswith("/"):
        return

    if text in {

        BTN_PHOTO,

        BTN_CHAR,

        BTN_CUSTOM,

        BTN_STYLE,

        BTN_VOICE,

        BTN_RESET
    }:

        return

    if not require_verified_message(
        message
    ):

        return

    chat_id = (
        message.chat.id
    )

    user_id = uid_from_message(
        message
    )

    try:

        add_message(
            user_id,
            "user",
            text
        )

        bot.send_chat_action(
            chat_id,
            "typing"
        )

        history = (
            get_recent_history(
                user_id
            )
        )

        response_text = (
            get_ai_response(
                user_id,
                history
            )
        )

        if not response_text:

            raise RuntimeError(
                "AI boş yanıt döndürdü"
            )

        add_message(
            user_id,
            "model",
            response_text
        )

        send_long_text(

            chat_id,

            response_text,

            message.message_id
        )

        user = get_user(
            user_id
        )

        if user.get(
            "voice_mode"
        ):

            try:

                bot.send_chat_action(
                    chat_id,
                    "record_voice"
                )

                voice_key = (
                    user.get(
                        "voice_choice"
                    )
                    or "TR_KADIN"
                )

                voice_code = (
                    VOICES.get(
                        voice_key,
                        VOICES["TR_KADIN"]
                    )
                )

                voice_text = (
                    response_text[
                        :VOICE_TEXT_LIMIT
                    ]
                )

                voice_stream = run_tts(
                    voice_text,
                    voice_code
                )

                voice_stream.name = (
                    "ryuma_voice.mp3"
                )

                bot.send_voice(
                    chat_id,
                    voice=voice_stream
                )

            except Exception as voice_exc:

                bot.send_message(

                    chat_id,

                    "⚠️ Ses üretilemedi: "
                    f"{str(voice_exc)[:250]}"
                )

        threading.Thread(

            target=maybe_compact_memory,

            args=(user_id,),

            daemon=True

        ).start()

    except Exception as exc:

        send_error_notification(
            chat_id,
            exc
        )


# ============================================================
# STARTUP
# ============================================================

if __name__ == "__main__":

    init_db()

    setup_bot_commands()

    try:

        bot.remove_webhook()

        time.sleep(1)

    except Exception:

        pass

    threading.Thread(

        target=run_flask,

        daemon=True

    ).start()

    bot.infinity_polling(

        timeout=20,

        long_polling_timeout=20,

        skip_pending=True
    )