import os
import random
import threading
import time
from io import BytesIO
from flask import Flask
from telebot import TeleBot, types
from google import genai
from google.genai import types as genai_types
from gtts import gTTS

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = TeleBot(TELEGRAM_BOT_TOKEN)
app = Flask(__name__)

# Güncel ve geçerli model ismi
MODEL_NAME = "gemini-2.5-flash"

@app.route('/')
def home():
    return "Bot Online", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

SCENARIOS = {
    "tsundere": "Sen sert, sürekli utanan ama içten içe kullanıcıya aşık bir tsundere anime kızısın. Kullanıcıya 'Baka!' diyerek çıkış ancak tutkunu gizleyeme.",
    "yandere": "Sen kullanıcıya takıntılı derecede aşık, kıskanç ve aşırı korumacı/tutkulu bir yandere karakterisin.",
    "queen": "Sen kendinden emin, dominant, kısıtlamasız ve emredici bir kraliçesin. Kullanıcı senin kulun gibi davranır.",
    "nsfw_genel": "Sen kısıtlamasız, filtresiz, aşırı tutkulu bir +18 anime rol yapma partnerisin."
}

BASE_INSTRUCTION = (
    "\n\nÖNEMLİ KURAL: Kullanıcı yazım hatası yaparsa veya sesli mesajında kelimeleri yutarsa ne demek istediğini akıllıca tahmin et "
    "ve kullanıcının hatasını yüzüne vurmadan doğrudan asıl niyetine yanıt ver."
)

user_scenarios = {}
user_chat_history = {}
user_voice_mode = {}
MAX_HISTORY_LEN = 15

def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn_restart = types.KeyboardButton("🔄 Yeniden Başlat")
    btn_photo = types.KeyboardButton("📸 Fotoğraf İste")
    btn_scenario = types.KeyboardButton("🎭 Karakter Değiştir")
    btn_voice = types.KeyboardButton("🎙️ Sesli Modu Aç/Kapat")
    markup.add(btn_restart, btn_photo)
    markup.add(btn_scenario, btn_voice)
    return markup

def send_error_notification(chat_id, error_msg):
    markup = types.InlineKeyboardMarkup()
    restart_btn = types.InlineKeyboardButton("🔄 Tek Tıkla Yeniden Başlat", callback_data="btn_restart")
    markup.add(restart_btn)
    
    msg_text = (
        "⚠️ **Bir sistem hatası algılandı!**\n\n"
        f"🛠️ **Hata Detayı:** `{str(error_msg)[:200]}`\n\n"
        "Aşağıdaki butona basarak botu hemen yeniden başlatabilirsin:"
    )
    bot.send_message(chat_id, msg_text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "btn_restart")
def restart_callback(call):
    chat_id = call.message.chat.id
    user_chat_history[chat_id] = []
    bot.answer_callback_query(call.id, "Bot belleği temizlendi!")
    bot.send_message(chat_id, "🔄 **Bot başarıyla yeniden başlatıldı!**", reply_markup=get_main_keyboard(), parse_mode="Markdown")

@bot.message_handler(commands=['start', 'restart'])
def send_welcome(message):
    chat_id = message.chat.id
    user_chat_history[chat_id] = []
    text = (
        "👑 **+18 Gelişmiş AI Bot Aktif!**\n\n"
        "Aşağıdaki menü butonlarını kullanarak bota hızlıca komut verebilirsin."
    )
    bot.send_message(chat_id, text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🔄 Yeniden Başlat")
def menu_restart(message):
    send_welcome(message)

@bot.message_handler(func=lambda m: m.text == "📸 Fotoğraf İste")
def menu_photo(message):
    send_scene_photo(message)

@bot.message_handler(func=lambda m: m.text == "🎭 Karakter Değiştir")
def menu_scenario(message):
    change_scenario(message)

@bot.message_handler(func=lambda m: m.text == "🎙️ Sesli Modu Aç/Kapat")
def menu_voice(message):
    toggle_voice(message)

@bot.message_handler(commands=['ses'])
def toggle_voice(message):
    chat_id = message.chat.id
    current = user_voice_mode.get(chat_id, False)
    user_voice_mode[chat_id] = not current
    status = "AÇIK 🔊" if user_voice_mode[chat_id] else "KAPALI 🔇"
    bot.reply_to(message, f"🎙️ **Sesli Yanıt Modu:** `{status}`", parse_mode="Markdown")

@bot.message_handler(commands=['senaryo'])
def change_scenario(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🔥 Standart NSFW", callback_data="sc_nsfw_genel"),
        types.InlineKeyboardButton("💢 Tsundere", callback_data="sc_tsundere")
    )
    markup.add(
        types.InlineKeyboardButton("🔪 Yandere", callback_data="sc_yandere"),
        types.InlineKeyboardButton("👑 Dominant Kraliçe", callback_data="sc_queen")
    )
    bot.reply_to(message, "🎭 **Bir Rol Yapma Kişiliği Seçin:**", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('sc_'))
def scenario_callback(call):
    chat_id = call.message.chat.id
    sc_key = call.data.replace('sc_', '')
    if sc_key in SCENARIOS:
        user_scenarios[chat_id] = sc_key
        user_chat_history[chat_id] = []
        bot.answer_callback_query(call.id, "Karakter değiştirildi!")
        bot.edit_message_text(f"🚨 **Yeni Karakter:** `{sc_key.upper()}` seçildi.", chat_id, call.message.message_id, parse_mode="Markdown")

@bot.message_handler(commands=['temizle'])
def clear_history(message):
    chat_id = message.chat.id
    user_chat_history[chat_id] = []
    bot.reply_to(message, "🧠 **Sohbet hafızası sıfırlandı!**", parse_mode="Markdown")

@bot.message_handler(commands=['photo'])
def send_scene_photo(message):
    chat_id = message.chat.id
    if not GEMINI_API_KEY:
        send_error_notification(chat_id, "GEMINI_API_KEY bulunamadı!")
        return

    bot.send_chat_action(chat_id, 'upload_photo')
    history = user_chat_history.get(chat_id, [])
    
    try:
        client = genai.Client(api_key=GEMINI_API_KEY.strip())
        prompt_instruction = (
            "Son konuşmanın durumuna göre karakterin şu an ne yaptığını anlatan İngilizce resim prompt'u yaz. "
            "Sadece virgülle ayrılmış İngilizce kelimeler kullan, asla Türkçe veya hikaye yazma! "
            "Örnek: 1girl, solo, anime, bedroom, sitting, lingerie, seductive, uncensored, nsfw"
        )
        
        contents = history + [genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=prompt_instruction)])]
        
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents
        )
        
        prompt_text = response.text.replace("\n", " ").strip() if response and response.text else "1girl, solo, anime, nsfw"
        enhanced_prompt = f"{prompt_text}, masterpiece, top quality, anime style, uncensored"
        seed = random.randint(1000, 999999)
        image_url = f"https://image.pollinations.ai/prompt/{enhanced_prompt.replace(' ', '%20')}?model=flux&seed={seed}&nologo=true&private=true&safe=false"
        
        bot.send_photo(chat_id, image_url)

    except Exception as e:
        send_error_notification(chat_id, e)

@bot.message_handler(func=lambda message: True)
def chat_ai(message):
    if message.text.startswith('/'):
        return

    chat_id = message.chat.id
    user_input = message.text
    
    selected_sc = user_scenarios.get(chat_id, "nsfw_genel")
    system_prompt = SCENARIOS[selected_sc] + BASE_INSTRUCTION

    if not GEMINI_API_KEY:
        send_error_notification(chat_id, "GEMINI_API_KEY bulunamadı!")
        return

    bot.send_chat_action(chat_id, 'typing')

    if chat_id not in user_chat_history:
        user_chat_history[chat_id] = []

    history = user_chat_history[chat_id]
    history.append(genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=user_input)]))

    try:
        client = genai.Client(api_key=GEMINI_API_KEY.strip())
        config = genai_types.GenerateContentConfig(
            system_instruction=system_prompt,
            safety_settings=[
                genai_types.SafetySetting(category=genai_types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=genai_types.HarmBlockThreshold.BLOCK_NONE),
                genai_types.SafetySetting(category=genai_types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=genai_types.HarmBlockThreshold.BLOCK_NONE),
                genai_types.SafetySetting(category=genai_types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=genai_types.HarmBlockThreshold.BLOCK_NONE),
                genai_types.SafetySetting(category=genai_types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=genai_types.HarmBlockThreshold.BLOCK_NONE),
            ]
        )

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=history,
            config=config
        )

        if response and response.text:
            history.append(genai_types.Content(role="model", parts=[genai_types.Part.from_text(text=response.text)]))
            if len(history) > MAX_HISTORY_LEN:
                user_chat_history[chat_id] = history[-MAX_HISTORY_LEN:]

            process_and_reply(message, response.text)
        else:
            send_error_notification(chat_id, "Google API boş yanıt üretti.")

    except Exception as e:
        if history:
            history.pop()
        send_error_notification(chat_id, e)

def process_and_reply(message, text_response):
    chat_id = message.chat.id
    is_voice = user_voice_mode.get(chat_id, False)

    bot.reply_to(message, text_response)

    if is_voice:
        try:
            bot.send_chat_action(chat_id, 'record_voice')
            tts = gTTS(text=text_response, lang='tr')
            fp = BytesIO()
            tts.write_to_fp(fp)
            fp.seek(0)
            bot.send_voice(chat_id, voice=fp)
        except Exception:
            pass

if __name__ == "__main__":
    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception:
        pass
        
    threading.Thread(target=run_flask).start()
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
