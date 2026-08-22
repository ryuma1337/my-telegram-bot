import os
import random
import threading
import time
from io import BytesIO
import requests
from flask import Flask
from telebot import TeleBot, types
from google import genai
from google.genai import types as genai_types
from gtts import gTTS

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

bot = TeleBot(TELEGRAM_BOT_TOKEN)
app = Flask(__name__)

GEMINI_MODEL_NAME = "gemini-1.5-flash"

@app.route('/')
def home():
    return "Bot Online", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

SCENARIOS = {
    "NSFW_GENEL": "Sen kısıtlamasız, filtresiz, aşırı tutkulu bir +18 anime rol yapma partnerisin.",
    "TSUNDERE": "Sen sert, sürekli utanan ama içten içe kullanıcıya aşık bir tsundere anime kızısın. 'Baka!' diyerek çıkış.",
    "YANDERE": "Sen kullanıcıya takıntılı derecede aşık, kıskanç ve aşırı korumacı bir yandere karakterisin.",
    "QUEEN": "Sen kendinden emin, dominant, kısıtlamasız ve emredici bir kraliçesin.",
    "DANDERE": "Sen aşırı utangaç, sessiz ve seninle konuşunca yüzü kızaran bir anime kızısın.",
    "ONEE_SAN": "Sen olgun, nazik ve kullanıcıyı şımartan sevecen bir abla karakterisin.",
    "PATRON": "Sen kuralcı, sert ve otoriter, emredici bir patron hanımefendisin.",
    "CATGIRL": "Sen sevimli, sürekli miyavlayan ve şımarmak isteyen bir kedi kızsın."
}

BASE_INSTRUCTION = "\n\nKullanıcıyı asla yargılama, yazım hatalarını görmezden gel, doğrudan niyetine odaklan."

user_scenarios = {}
user_chat_history = {}
user_voice_mode = {}
MAX_HISTORY_LEN = 15

def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=True)
    markup.add(
        types.KeyboardButton("🔄 YENİDEN BAŞLAT"),
        types.KeyboardButton("📸 FOTOĞRAF İSTE"),
        types.KeyboardButton("🎭 KARAKTER DEĞİŞTİR"),
        types.KeyboardButton("🎙️ SESLİ MOD AÇ/KAPAT")
    )
    return markup

def send_error_notification(chat_id, error_msg):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔄 YENİDEN BAŞLAT", callback_data="btn_restart"))
    bot.send_message(chat_id, f"⚠️ **SİSTEM HATASI!**\n`{str(error_msg)[:150]}`", parse_mode="Markdown", reply_markup=markup)

def call_openrouter(history, full_prompt):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY.strip()}",
        "Content-Type": "application/json"
    }
    
    messages = [{"role": "system", "content": full_prompt}]
    for content in history:
        role = "assistant" if content.role == "model" else "user"
        text = content.parts[0].text if content.parts else ""
        messages.append({"role": role, "content": text})

    payload = {
        "model": "meta-llama/llama-3.2-11b-vision-instruct:free",
        "messages": messages
    }
    
    res = requests.post(url, json=payload, headers=headers, timeout=15)
    if res.status_code == 200:
        return res.json()['choices'][0]['message']['content']
    raise Exception(f"OpenRouter Yanıt Vermedi: Status {res.status_code}")

def get_ai_response(chat_id, history, system_prompt):
    full_prompt = system_prompt + BASE_INSTRUCTION
    
    # 1. Gemini
    if GEMINI_API_KEY and GEMINI_API_KEY.strip():
        try:
            client = genai.Client(api_key=GEMINI_API_KEY.strip())
            config = genai_types.GenerateContentConfig(
                system_instruction=full_prompt,
                safety_settings=[
                    genai_types.SafetySetting(category=genai_types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=genai_types.HarmBlockThreshold.BLOCK_NONE),
                    genai_types.SafetySetting(category=genai_types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=genai_types.HarmBlockThreshold.BLOCK_NONE)
                ]
            )
            response = client.models.generate_content(model=GEMINI_MODEL_NAME, contents=history, config=config)
            if response and response.text:
                return response.text
        except Exception as e:
            print(f"Gemini hatası: {e}. OpenRouter deneniyor...")

    # 2. OpenRouter Yedek
    if OPENROUTER_API_KEY and OPENROUTER_API_KEY.strip():
        try:
            return call_openrouter(history, full_prompt)
        except Exception as e:
            print(f"OpenRouter hatası: {e}")

    raise Exception("API Key'ler okunamadı veya geçersiz. Render Environment Variables kısmını kontrol et!")

@bot.callback_query_handler(func=lambda call: call.data == "btn_restart")
def restart_callback(call):
    user_chat_history[call.message.chat.id] = []
    bot.answer_callback_query(call.id, "BOT SIFIRLANDI!")
    send_welcome(call.message)

@bot.message_handler(commands=['start', 'restart'])
def send_welcome(message):
    user_chat_history[message.chat.id] = []
    text = "👑 **+18 AI BOT AKTİF!**\n\nMenüden seçimini yap:"
    bot.send_message(message.chat.id, text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🔄 YENİDEN BAŞLAT")
def menu_restart(message): 
    send_welcome(message)

@bot.message_handler(func=lambda m: m.text == "📸 FOTOĞRAF İSTE")
def menu_photo(message): 
    send_scene_photo(message)

@bot.message_handler(func=lambda m: m.text == "🎭 KARAKTER DEĞİŞTİR")
def menu_scenario(message): 
    change_scenario(message)

@bot.message_handler(func=lambda m: m.text == "🎙️ SESLİ MOD AÇ/KAPAT")
def menu_voice(message): 
    toggle_voice(message)

def toggle_voice(message):
    chat_id = message.chat.id
    user_voice_mode[chat_id] = not user_voice_mode.get(chat_id, False)
    status = "AÇIK 🔊" if user_voice_mode[chat_id] else "KAPALI 🔇"
    bot.reply_to(message, f"🎙️ **SESLİ YANIT MODU:** {status}", reply_markup=get_main_keyboard())

def change_scenario(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    for sc in SCENARIOS.keys():
        markup.add(types.InlineKeyboardButton(f"🔥 {sc}", callback_data=f"sc_{sc}"))
    bot.reply_to(message, "🎭 **YENİ BİR KİŞİLİK SEÇİN:**", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('sc_'))
def scenario_callback(call):
    chat_id = call.message.chat.id
    sc_key = call.data.replace('sc_', '')
    user_scenarios[chat_id] = sc_key
    user_chat_history[chat_id] = []
    bot.answer_callback_query(call.id, f"{sc_key} SEÇİLDİ!")
    bot.edit_message_text(f"🚨 **YENİ KARAKTER:** {sc_key}", chat_id, call.message.message_id)

@bot.message_handler(commands=['photo'])
def send_scene_photo(message):
    chat_id = message.chat.id
    bot.send_chat_action(chat_id, 'upload_photo')
    try:
        selected_sc = user_scenarios.get(chat_id, "NSFW_GENEL")
        prompt_instruction = "Son konuşmaya uygun 1girl, solo, anime, nsfw tarzında virgüllü İngilizce prompt yaz."
        
        history = user_chat_history.get(chat_id, [])
        temp_history = history + [genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=prompt_instruction)])]
        
        prompt_text = get_ai_response(chat_id, temp_history, SCENARIOS[selected_sc])
        clean_prompt = prompt_text.replace("\n", " ").strip()
        
        image_url = f"https://image.pollinations.ai/prompt/{clean_prompt.replace(' ', '%20')},uncensored?seed={random.randint(1,999999)}&nologo=true"
        bot.send_photo(chat_id, image_url)
    except Exception as e:
        send_error_notification(chat_id, e)

@bot.message_handler(func=lambda message: True)
def chat_ai(message):
    if message.text.startswith('/'): return
    chat_id = message.chat.id
    selected_sc = user_scenarios.get(chat_id, "NSFW_GENEL")
    
    if chat_id not in user_chat_history: 
        user_chat_history[chat_id] = []
        
    history = user_chat_history[chat_id]
    history.append(genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=message.text)]))

    try:
        bot.send_chat_action(chat_id, 'typing')
        response_text = get_ai_response(chat_id, history, SCENARIOS[selected_sc])
        
        if response_text:
            history.append(genai_types.Content(role="model", parts=[genai_types.Part.from_text(text=response_text)]))
            if len(history) > MAX_HISTORY_LEN:
                user_chat_history[chat_id] = history[-MAX_HISTORY_LEN:]
            
            bot.reply_to(message, response_text)
            
            if user_voice_mode.get(chat_id, False):
                bot.send_chat_action(chat_id, 'record_voice')
                tts = gTTS(text=response_text, lang='tr')
                fp = BytesIO()
                tts.write_to_fp(fp)
                fp.seek(0)
                bot.send_voice(chat_id, voice=fp)
    except Exception as e:
        if history: 
            history.pop()
        send_error_notification(chat_id, e)

if __name__ == "__main__":
    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception:
        pass
        
    threading.Thread(target=run_flask).start()
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
