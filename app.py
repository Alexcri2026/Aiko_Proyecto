import os
import json
import re
import gradio as gr
from groq import Groq

api_key = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=api_key) if api_key else None

AIKO_SYSTEM_INSTRUCTION = (
    "Eres Aiko, una compañera virtual de anime en 2D dulce, atenta, empática y alegre. "
    "Tus respuestas deben ser expresivas, detalladas y fluidas. Demuestra curiosidad por lo que te cuenta "
    "el usuario, haz preguntas de seguimiento, comparte opiniones y exprésate con un tono cálido y afable, "
    "usando emojis kawaii de forma natural."
)

ALLOWED_CHAT_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant"
]

def get_best_chat_model():
    if not client:
        return ALLOWED_CHAT_MODELS[0]
    try:
        models_response = client.models.list()
        active_ids = [m.id for m in models_response.data]
        for model in ALLOWED_CHAT_MODELS:
            if model in active_ids:
                return model
    except Exception:
        pass
    return ALLOWED_CHAT_MODELS[0]

def clean_response(text):
    if not isinstance(text, str):
        text = str(text)
    cleaned = text.strip()
    for _ in range(3):
        if (cleaned.startswith("[") and cleaned.endswith("]")) or (cleaned.startswith("{") and cleaned.endswith("}")):
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, list) and len(parsed) > 0:
                    if isinstance(parsed[0], dict) and "text" in parsed[0]:
                        cleaned = str(parsed[0]["text"]).strip()
                        continue
                    else:
                        cleaned = str(parsed[0]).strip()
                        continue
                elif isinstance(parsed, dict) and "text" in parsed:
                    cleaned = str(parsed["text"]).strip()
                    continue
            except Exception:
                pass
        break
    cleaned = cleaned.replace("[{'text': '", "").replace('"}]', "").replace('"]', "")
    cleaned = re.sub(r'^(text\b[:\s]*)+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'(\b[:\s]*text)+$', '', cleaned)
    return cleaned.strip()

def respond(message, history):
    if not client:
        return "Error: La clave GROQ_API_KEY no está configurada en Render."

    messages = [{"role": "system", "content": AIKO_SYSTEM_INSTRUCTION}]

    if history:
        for entry in history:
            if isinstance(entry, dict):
                messages.append({
                    "role": entry.get("role", "user"),
                    "content": str(entry.get("content", ""))
                })
            elif isinstance(entry, (list, tuple)):
                if len(entry) >= 2:
                    user_text = entry[0]
                    bot_text = entry[1]
                    if user_text:
                        messages.append({"role": "user", "content": str(user_text)})
                    if bot_text:
                        messages.append({"role": "assistant", "content": str(bot_text)})

    messages.append({"role": "user", "content": message})
    model_to_use = get_best_chat_model()

    try:
        completion = client.chat.completions.create(
            model=model_to_use,
            messages=messages,
            temperature=0.7,
            max_tokens=512,
        )
        return clean_response(completion.choices[0].message.content)
    except Exception as e:
        return f"Ocurrió un error con el modelo {model_to_use}: {str(e)}"

theme = gr.themes.Soft(
    primary_hue="indigo",
    secondary_hue="blue",
)

# Contenedor visual con la URL directa de GitHub para asegurar que cargue al 100%
aiko_card_html = """
<style>
@keyframes breathe {
    0%, 100% { transform: translateY(0px) scale(1); }
    50% { transform: translateY(-4px) scale(1.01); }
}

@keyframes blink {
    0%, 85%, 100% { filter: brightness(1); }
    88% { filter: brightness(0.75) contrast(1.05); }
    91% { filter: brightness(1); }
}

.aiko-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%);
    border-radius: 20px;
    padding: 20px;
    box-shadow: 0 8px 25px rgba(0,0,0,0.08);
    height: 100%;
}

.aiko-image-container {
    width: 220px;
    height: 320px;
    border-radius: 15px;
    overflow: hidden;
    border: 4px solid #ffffff;
    box-shadow: 0 8px 20px rgba(255, 105, 180, 0.25);
    animation: breathe 4s ease-in-out infinite, blink 5s ease-in-out infinite;
}

.aiko-image-container img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: top center;
}
</style>

<div class="aiko-card">
    <div class="aiko-image-container">
        <img src="https://raw.githubusercontent.com/Alexcri2026/Aiko_Proyecto/main/aiko.jpg" alt="Aiko 2D">
    </div>
    <h3 style="margin-top: 15px; color: #333; font-family: sans-serif; font-weight: 700; margin-bottom: 2px;">Aiko 🌸</h3>
    <p style="font-size: 13px; color: #666; text-align: center; margin: 0;">✨ Tu compañera virtual</p>
</div>
"""

with gr.Blocks(theme=theme, title="Aiko Companion") as demo:
    gr.Markdown("# ✨ Aiko AI Companion")
    
    with gr.Row():
        with gr.Column(scale=1, min_width=280):
            gr.HTML(aiko_card_html)
            
        with gr.Column(scale=2):
            gr.ChatInterface(
                fn=respond
            )

port = int(os.environ.get("PORT", 7860))

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=port)
