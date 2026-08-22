# KARAKTERLERE ÖZEL VARSAYILAN KILIK VE STİL DETAYLARI
SCENARIO_VISUALS = {
    "NSFW_GENEL": "beautiful woman, seductive, elegant atmosphere",
    "TSUNDERE": "tsundere anime girl, blushing, school uniform, pouting, twintails",
    "YANDERE": "yandere anime girl, intense dark eyes, crazy smile, dark aesthetic",
    "QUEEN": "dominant queen, crown, luxury dress, high heel, regal throne room",
    "DANDERE": "shy anime girl, cute sweater, blushing face, looking down, indoor",
    "ONEE_SAN": "mature beauty, voluptuous, cozy room, soft lighting, attractive smile",
    "PATRON": "business woman, suit, office setting, glasses, elegant desk",
    "CATGIRL": "cute catgirl, cat ears, tail, playful pose, anime aesthetic",
    "SEKRETER": "sexy secretary, unbuttoned shirt, glasses, office desk background",
    "HEMŞİRE": "nurse outfit, medical room background, cute expression"
}

def generate_contextual_image_prompt(chat_id):
    selected_sc = user_scenarios.get(chat_id, "NSFW_GENEL")
    history = user_chat_history.get(chat_id, [])
    
    # Karakterin varsayılan görsel ögeleri
    base_visual = SCENARIO_VISUALS.get(selected_sc, "beautiful female")
    
    analysis_instruction = (
        "Describe the visual scene of the conversation right now in concise English image prompt tags. "
        "Focus on: clothing, facial expression, body position, camera angle, and room background. "
        "Return ONLY comma-separated English tags."
    )
    
    temp_history = history + [{"role": "user", "text": analysis_instruction}]
    
    try:
        prompt_tags = get_ai_response(chat_id, temp_history, SCENARIOS[selected_sc])
    except Exception:
        prompt_tags = "intimate moment, looking at viewer, detailed room"

    style = user_image_style.get(chat_id, "ANIME")
    clean_prompt = prompt_tags.replace("\n", " ").replace("'", "").replace('"', '').strip()
    
    if style == "ANIME":
        # Yüksek Kaliteli Anime Motoru Ayarları
        full_prompt = (
            f"masterpiece, best quality, ultra-detailed, anime artwork, Japanese anime style, "
            f"vibrant colors, dynamic lighting, {base_visual}, {clean_prompt}, NSFW, uncensored"
        )
        model_name = "anime"  # Pollinations'ın özel anime motoru
    else:
        # Yüksek Kaliteli Realistik Motor Ayarları
        full_prompt = (
            f"8k resolution, photorealistic, RAW photo, detailed skin texture, realistic lighting, "
            f"shot on 35mm lens, {base_visual}, {clean_prompt}, NSFW, uncensored"
        )
        model_name = "flux-real"

    seed = random.randint(100000, 999999)
    safe_prompt = urllib.parse.quote(full_prompt)
    
    return f"https://image.pollinations.ai/prompt/{safe_prompt}?width=832&height=1216&seed={seed}&nologo=true&model={model_name}"
