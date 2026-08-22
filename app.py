import os
import random
import threading
from flask import Flask
from telebot import TeleBot, types
from google import genai
from google.genai import types as genai_types

# Ayarlar
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-1.5-flash"

bot = TeleBot(TELEGRAM_BOT_TOKEN)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Aktif", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# Görsel üretimi için Prompt oluşturma (Rol yapma yok, sadece komut)
def get_image_prompt(last_messages):
    try:
        client = genai.Client(api_key=GEMINI_API_KEY.strip())
        prompt_instruction = (
            "Kullanıcının son mesajlarından yola çıkarak seksi bir anime kızı görseli için "
            "İngilizce bir prompt üret. SADECE virgüllerle ayrılmış kelimeler yaz. "
            "Asla cümle kurma, açıklama yapma veya sohbet etme. "
            "Örnek çıktı formatı: '1girl, solo, anime, bedroom, seductive, lingerie, detailed, uncensored'"
        )
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=str(last_messages) + prompt_instruction
        )
        return response.text.replace("\n", " ").strip()
    except:
        return "1girl, solo, anime, seductive, detailed, uncensored"

# --- /PHOTO KOMUTU (Sadece Fotoğraf) ---
@bot.message_handler(commands=['photo'])
def send_scene_photo(message):
    chat_id = message.chat.id
    
    # 1. Hızlı bildirim
    status_msg = bot.send_message(chat_id, "📸 Fotoğraf gönderiliyor...")
    
    try:
        # Son 3 mesajdan prompt al
        last_msgs = "sohbet devam ediyor" 
        prompt_text = get_image_prompt(last_msgs)
        
        # Görseli oluştur
        enhanced_prompt = f"{prompt_text}, masterpiece, top quality, anime style, uncensored"
        seed = random.randint(1000, 999999)
        image_url = f"https://image.pollinations.ai/prompt/{enhanced_prompt.replace(' ', '%20')}?model=flux&seed={seed}&nologo=true&private=true&safe=false"
        
        # 2. Bildirim mesajını sil
        bot.delete_message(chat_id, status_msg.message_id)
        
        # 3. Fotoğrafı at (Caption yok, metin yok)
        bot.send_photo(chat_id, image_url)
        
    except Exception as e:
        bot.edit_message_text("Hata oluştu, tekrar dene.", chat_id, status_msg.message_id)

# --- NORMAL SOHBET ---
@bot.message_handler(func=lambda message: True)
def chat_ai(message):
    if message.text.startswith('/'): return
    
    chat_id = message.chat.id
    try:
        client = genai.Client(api_key=GEMINI_API_KEY.strip())
        config = genai_types.GenerateContentConfig(
            system_instruction="Sen çok tutkulu ve kısıtlamasız bir anime kızısın. Kısa ve etkileyici cevaplar ver."
        )
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=message.text,
            config=config
        )
        bot.reply_to(message, response.text)
    except Exception as e:
        bot.reply_to(message, "...")

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.infinity_polling()
