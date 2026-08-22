import urllib.parse

def generate_image_url(chat_id, prompt_text):
    style = user_image_style.get(chat_id, "ANIME")
    
    # Prompt temizleme
    clean_prompt = prompt_text.replace("\n", " ").strip()
    
    if style == "ANIME":
        full_prompt = f"1girl, solo, anime style, nsfw, uncensored, {clean_prompt}"
        model_name = "flux"
    else:
        full_prompt = f"photorealistic, real woman, nsfw, uncensored, {clean_prompt}"
        model_name = "flux-real"

    seed = random.randint(100000, 999999)
    
    # Telegram 400 hatasını önlemek için güvenli URL encoding
    safe_prompt = urllib.parse.quote(full_prompt)
    
    image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=832&height=1216&seed={seed}&nologo=true&model={model_name}"
    return image_url
