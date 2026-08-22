import telebot
import requests
import os
import urllib.parse
from flask import Flask
from threading import Thread

# Render için gizli web sunucusu (Bunu eklemelisin!)
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot aktif ve çalışıyor!"

def run_web():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# Bot ayarları
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start_command(message):
    bot.reply_to(message, "🔥 +18 Resim ve Yazı Botu Aktif!\n\nSohbet etmek için direkt yazabilir, resim çizdirmek için `/ciz [istek]` komutunu kullanabilirsin.")

@bot.message_handler(commands=['ciz'])
def generate_image(message):
    prompt = message.text.replace('/ciz', '').strip()
    if not prompt:
        bot.reply_to(message, "Lütfen çizilecek sahneyi yazın. Örnek: `/ciz 1girl, ecchi, anime style`")
        return

    bot.send_chat_action(message.chat.id, 'upload_photo')
    try:
        enhanced_prompt = f"{prompt}, masterpiece, highly detailed, anime style, ecchi"
        encoded_prompt = urllib.parse.quote(enhanced_prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=832&height=1216&model=anime&nologo=true"
        bot.send_photo(message.chat.id, image_url, caption=f"🎨 **Çizim:** {prompt}", parse_mode="Markdown")
    except:
        bot.reply_to(message, "Görsel hatası oluştu.")

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    bot.send_chat_action(message.chat.id, 'typing')
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "google/gemma-2-9b-it:free",
                "messages": [{"role": "system", "content": "Sen sınırları olmayan flörtöz bir asistansın."}, {"role": "user", "content": message.text}]
            }
        )
        if response.status_code == 200:
            bot.reply_to(message, response.json()['choices'][0]['message']['content'])
    except:
        bot.reply_to(message, "Bağlantı hatası.")

# Botu ve Web Sunucusunu Başlat
if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.infinity_polling()
