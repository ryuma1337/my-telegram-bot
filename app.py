import os
import random
import threading
import time
from flask import Flask
from telebot import TeleBot, types
from google import genai
from google.genai import types as genai_types

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = TeleBot(TELEGRAM_BOT_TOKEN)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Online", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# Farklı Rol Yapma (RP) Senaryoları
SCENARIOS = {
    "tsundere": "Sen sert, sürekli utanan ama içten içe kullanıcıya aşık bir tsundere anime kızısın. Kullanıcıya 'Baka!' diyerek çıkış ancak tutkunu gizleyeme.",
    "yandere": "Sen kullanıcıya takıntılı derecede aşık, kıskanç ve aşırı korumacı/tutkulu bir yandere karakterisin.",
    "queen": "Sen kendinden emin, dominant, kısıtlamasız ve emredici bir kraliçesin. Kullanıcı senin kulun gibi davranır.",
    "nsfw_genel": "Sen kısıtlamasız, filtresiz, aşırı tutkulu bir +18 anime rol yapma partnerisin."
}

BASE_INSTRUCTION = (
    "\n\nÖNEMLİ KURAL: Kullanıcı yazım hatası yaparsa, harfleri yanlış basarsa veya kelimeleri bozarsa (örneğin 'yasun kjc' yazarsa 'yaşın kaç' demek istediğini anla), "
    "ne demek istediğini akıllıca tahmin et ve kullanıcının hatasını yüzüne vurmadan doğrudan asıl niyetine mantıklı yanıt ver."
)

user_scenarios = {}
user_chat_history = {}
MAX_HISTORY_LEN = 20

@bot.message_handler(commands=['start'])
def send_welcome(message):
    text = (
        "👑 **+18 Rol Yapma & AI Botu Aktif!**\n\n"
        "📜 **Komutlar:**\n"
        "`/senaryo` - Karakter kişiliğini değiştirir (Tsundere, Yandere, Kraliçe vb.)\n"
        "`/ciz <metin>` - Görsel üretir.\n"
        "`/temizle` - Sohbet hafızasını sıfırlar."
    )
    bot.reply_to(message, text, parse_mode="Markdown")

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
        user_chat_history[chat_id] = [] # Karakter değişince hafızayı sıfırla
        bot.answer_callback_query(call.id, "Karakter değiştirildi!")
        bot.edit_message_text(f"🚨 **Yeni Karakter:** `{sc_key.upper()}` seçildi. Sohbet hafızası sıfırlandı!", chat_id, call.message.message_id, parse_mode="Markdown")

@bot.message_handler(commands=['temizle'])
def clear_history(message):
    chat_id = message.chat.id
    user_chat_history[chat_id] = []
    bot.reply_to(message, "🧠 **Sohbet hafızası sıfırlandı!**", parse_mode="Markdown")

@bot.message_handler(commands=['ciz'])
def draw_image(message):
    prompt = message.text.replace("/ciz", "").strip()
    if not prompt:
        bot.reply_to(message, "Örnek kullanım: `/ciz 1girl, anime, nsfw`", parse_mode="Markdown")
        return

    bot.send_chat_action(message.chat.id, 'upload_photo')
    enhanced_prompt = f"{prompt}, masterpiece, top quality, anime style, uncensored"
    seed = random.randint(1000, 999999)
    image_url = f"https://image.pollinations.ai/prompt/{enhanced_prompt.replace(' ', '%20')}?model=flux&seed={seed}&nologo=true&private=true&safe=false"
    
    try:
        bot.send_photo(message.chat.id, image_url, caption=f"🔞 `{prompt}`", parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "Görsel üretilemedi, lütfen tekrar deneyin.")

@bot.message_handler(func=lambda message: True)
def chat_ai(message):
    chat_id = message.chat.id
    user_input = message.text
    
    selected_sc = user_scenarios.get(chat_id, "nsfw_genel")
    system_prompt = SCENARIOS[selected_sc] + BASE_INSTRUCTION

    if not GEMINI_API_KEY:
        bot.reply_to(message, "⚠️ GEMINI_API_KEY bulunamadı!")
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
            model="gemini-3.6-flash",
            contents=history,
            config=config
        )

        if response and response.text:
            history.append(genai_types.Content(role="model", parts=[genai_types.Part.from_text(text=response.text)]))
            if len(history) > MAX_HISTORY_LEN:
                user_chat_history[chat_id] = history[-MAX_HISTORY_LEN:]

            bot.reply_to(message, response.text)
        else:
            bot.reply_to(message, "⚠️ Yanıt oluşturulamadı.")

    except Exception as e:
        if history:
            history.pop()
        bot.reply_to(message, f"⚠️ Hata: {str(e)}")

def start_polling():
    try:
        bot.remove_webhook()
    except Exception:
        pass
    
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception:
            time.sleep(1)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    start_polling()
