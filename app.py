import os
import json
import gradio as gr
from groq import Groq

# Inicializar cliente de Groq
api_key = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=api_key) if api_key else None

# Personalidad original de Aiko
AIKO_SYSTEM_INSTRUCTION = (
    "Eres Aiko, una compañera virtual de anime en 2D dulce, atenta, empática y alegre. "
    "Tus respuestas deben ser expresivas, detalladas y fluidas. Demuestra curiosidad por lo que te cuenta "
    "el usuario, haz preguntas de seguimiento, comparte opiniones y exprésate con un tono cálido y afable, "
    "usando emojis kawaii de forma natural."
)

# Priorizando los modelos GPT-OSS de OpenAI alojados en Groq, seguidos de Llama
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
    """Limpia recursivamente cualquier estructura JSON anidada o etiquetas extra del texto"""
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
    return cleaned

def respond(message, history):
    if not client:
        return "Error: La clave GROQ_API_KEY no está configurada en Render."

    messages = [{"role": "system", "content": AIKO_SYSTEM_INSTRUCTION}]

    # Conversión flexible del historial
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
        
        raw_text = completion.choices[0].message.content
        return clean_response(raw_text)

    except Exception as e:
        return f"Ocurrió un error con el modelo {model_to_use}: {str(e)}"

theme = gr.themes.Soft(
    primary_hue="indigo",
    secondary_hue="blue",
)

with gr.Blocks(theme=theme, title="Aiko Companion") as demo:
    gr.Markdown("# ✨ Aiko AI Companion")
    
    gr.ChatInterface(
        fn=respond
    )

port = int(os.environ.get("PORT", 7860))

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=port)
