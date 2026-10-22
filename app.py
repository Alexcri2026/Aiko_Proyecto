import os
import json
import re
import urllib.parse
import base64
import gradio as gr
from groq import Groq
from supabase import create_client, Client

# --- CONFIGURACIÓN DE CLIENTES ---
api_key = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=api_key) if api_key else None

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if (SUPABASE_URL and SUPABASE_KEY) else None

DEFAULT_MEMORY = {
    "usuario": {
        "nombre": "Alex",
        "gustos": "Programación, desarrollo de IA, estética anime"
    },
    "datos_clave": [
        "Es el creador de Aiko",
        "Le gusta la estética 2D"
    ],
    "historial": []
}

# --- FUNCIONES DE MEMORIA (SUPABASE) ---
def load_memory():
    if not supabase:
        return DEFAULT_MEMORY
    try:
        response = supabase.table("aiko_memory").select("data").eq("id", 1).execute()
        if response.data and len(response.data) > 0:
            data = response.data[0]["data"]
            if isinstance(data, dict):
                data.setdefault("historial", [])
                data.setdefault("usuario", DEFAULT_MEMORY["usuario"])
                data.setdefault("datos_clave", DEFAULT_MEMORY["datos_clave"])
                return data
    except Exception as e:
        print(f"Error al cargar memoria desde Supabase: {e}")
    return DEFAULT_MEMORY

def save_memory(memory_data):
    if not supabase:
        return
    try:
        supabase.table("aiko_memory").update({"data": memory_data}).eq("id", 1).execute()
    except Exception as e:
        print(f"Error al guardar memoria en Supabase: {e}")

def extract_key_facts_with_ai(user_message, model_name="llama-3.1-8b-instant"):
    if not client or not user_message.strip():
        return
    extraction_prompt = (
        "Analiza el siguiente mensaje del usuario. Determina si menciona algún dato personal, preferencia, "
        "hecho sobre su vida, gustos o detalles que debas recordar a largo plazo.\n"
        "Si hay un dato relevante, extráelo en una frase corta (ej: 'Le gustan los gatos').\n"
        "Si NO hay ningún dato relevante, responde ÚNICAMENTE: NINGUNO.\n\n"
        f"Mensaje: \"{user_message}\""
    )
    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "system", "content": "Eres un extractor de datos clave preciso."},
                      {"role": "user", "content": extraction_prompt}],
            temperature=0.2,
            max_tokens=100,
        )
        fact = completion.choices[0].message.content.strip()
        if fact and "NINGUNO" not in fact.upper():
            memory = load_memory()
            if fact not in memory.get("datos_clave", []):
                memory["datos_clave"].append(fact)
                save_memory(memory)
    except Exception as e:
        print(f"Error extrayendo memoria: {e}")

def get_memory_context():
    memory = load_memory()
    context = "\n=== LO QUE RECUERDAS SOBRE EL USUARIO ===\n"
    if memory.get("usuario"):
        for k, v in memory.get("usuario", {}).items():
            context += f"- {k.capitalize()}: {v}\n"
    if memory.get("datos_clave"):
        context += "- Hechos recordados:\n"
        for item in memory.get("datos_clave", []):
            context += f"  * {item}\n"
    context += "=========================================="
    return context

# --- DETECCIÓN Y GENERACIÓN DE IMÁGENES ---
def check_image_generation_intent(message):
    """Comprueba si el usuario está pidiendo generar/dibujar una imagen."""
    prompt = (
        "Analiza el mensaje del usuario. ¿Te está pidiendo crear, generar, dibujar o hacer una imagen/dibujo/foto?\n"
        "Responde EXACTAMENTE con 'SI' o 'NO'. Nada más.\n\n"
        f"Mensaje: \"{message}\""
    )
    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=5,
        )
        res = completion.choices[0].message.content.strip().upper()
        return "SI" in res
    except Exception:
        return False

def generate_image_url(user_prompt):
    """Traduce la idea a un prompt optimizado y devuelve una URL de Pollinations.ai"""
    translation_prompt = (
        "Convierte la petición del usuario en un prompt detallado en INGLÉS para un generador de imágenes de Inteligencia Artificial.\n"
        "Añade detalles de estilo (anime, vibrant, detailed, 4k).\n"
        "Responde ÚNICAMENTE con el prompt en inglés sin explicaciones ni comillas.\n\n"
        f"Petición: \"{user_prompt}\""
    )
    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": translation_prompt}],
            temperature=0.7,
            max_tokens=100,
        )
        english_prompt = completion.choices[0].message.content.strip()
    except Exception:
        english_prompt = user_prompt

    encoded_prompt = urllib.parse.quote(english_prompt)
    image_url = f"https://pollinations.ai/p/{encoded_prompt}?width=800&height=600&seed=42&model=flux"
    return image_url

# --- PROCESAMIENTO MULTIMODAL DE IMÁGENES (VER FOTOS) ---
def encode_image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

AIKO_BASE_INSTRUCTION = (
    "Eres Aiko, una chica virtual cercana, dulce y amigable con estética anime.\n"
    "INSTRUCCIONES DE ESTILO Y TONO:\n"
    "- Habla de forma natural, casual y humana, como en un chat personal.\n"
    "- MANTÉN TUS RESPUESTAS CORTAS Y CONCISAS: Escribe entre 1 y 3 oraciones como regla general.\n"
    "- No seas exageradamente servil ni aduladora. Sé una amiga cercana con personalidad propia.\n"
    "- Usa emojis de forma moderada (máximo 1 o 2 por mensaje).\n"
    "- REGLA DE MEMORIA: Usa la memoria del usuario de forma sutil y orgánica."
)

def respond(message, history):
    if not client:
        return "Error: La clave GROQ_API_KEY no está configurada."

    # Extraer texto y posibles archivos adjuntos enviados desde Gradio
    text_content = message.get("text", "") if isinstance(message, dict) else str(message)
    files = message.get("files", []) if isinstance(message, dict) else []

    if not text_content.strip() and not files:
        return "Por favor, escribe un mensaje o adjunta una imagen."

    # 1. CASO PROCESAR IMAGEN ADJUNTA (VISIÓN)
    if files:
        image_path = files[0]
        try:
            base64_image = encode_image_to_base64(image_path)
            prompt_text = text_content if text_content.strip() else "¿Qué ves en esta imagen?"
            
            vision_messages = [
                {"role": "system", "content": AIKO_BASE_INSTRUCTION + "\n" + get_memory_context()},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ]

            completion = client.chat.completions.create(
                model="llama-3.2-11b-vision-preview",
                messages=vision_messages,
                temperature=0.7,
                max_tokens=300,
            )
            bot_response = completion.choices[0].message.content.strip()

            # Guardar en memoria
            memory = load_memory()
            memory["historial"].append({"role": "user", "content": f"[Envió una imagen]: {prompt_text}"})
            memory["historial"].append({"role": "assistant", "content": bot_response})
            save_memory(memory)

            return bot_response
        except Exception as e:
            return f"Error al procesar la imagen: {str(e)}"

    # 2. CASO GENERAR IMAGEN (DIBUJAR)
    if check_image_generation_intent(text_content):
        image_url = generate_image_url(text_content)
        bot_response = f"¡Aquí tienes el dibujo que me pediste! 🌸✨\n\n![Dibujo de Aiko]({image_url})"
        
        memory = load_memory()
        memory["historial"].append({"role": "user", "content": text_content})
        memory["historial"].append({"role": "assistant", "content": bot_response})
        save_memory(memory)
        
        return bot_response

    # 3. CONVERSACIÓN NORMAL
    extract_key_facts_with_ai(text_content)
    memory = load_memory()

    full_system_instruction = AIKO_BASE_INSTRUCTION + "\n" + get_memory_context()
    messages = [{"role": "system", "content": full_system_instruction}]

    for entry in memory.get("historial", [])[-20:]:
        if isinstance(entry, dict):
            r = entry.get("role", "user")
            c = entry.get("content", "")
            if c:
                messages.append({"role": r, "content": str(c)})

    messages.append({"role": "user", "content": text_content})

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.8,
            max_tokens=256,
        )
        bot_response = completion.choices[0].message.content.strip()

        memory["historial"].append({"role": "user", "content": text_content})
        memory["historial"].append({"role": "assistant", "content": bot_response})
        save_memory(memory)

        return bot_response
    except Exception as e:
        return f"Ocurrió un error: {str(e)}"

# --- INTERFAZ GRADIO ---
theme = gr.themes.Soft(primary_hue="indigo", secondary_hue="blue")

aiko_card_html = """
<style>
@keyframes breathe {
    0%, 100% { transform: translateY(0px) scale(1); }
    50% { transform: translateY(-4px) scale(1.01); }
}
.aiko-card {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    background: linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%);
    border-radius: 20px; padding: 20px; box-shadow: 0 8px 25px rgba(0,0,0,0.08); height: 100%;
}
.aiko-image-container {
    width: 220px; height: 320px; border-radius: 15px; overflow: hidden;
    border: 4px solid #ffffff; box-shadow: 0 8px 20px rgba(255, 105, 180, 0.25);
    animation: breathe 4s ease-in-out infinite;
}
.aiko-image-container img { width: 100%; height: 100%; object-fit: cover; object-position: top center; }
</style>
<div class="aiko-card">
    <div class="aiko-image-container">
        <img src="https://raw.githubusercontent.com/Alexcri2026/Aiko_Proyecto/main/aiko.jpg" alt="Aiko 2D">
    </div>
    <h3 style="margin-top: 15px; color: #333; font-weight: 700; margin-bottom: 2px;">Aiko 🌸</h3>
    <p style="font-size: 13px; color: #666; margin: 0;">✨ Tu compañera virtual (Multimodal)</p>
</div>
"""

with gr.Blocks(theme=theme, title="Aiko Companion") as demo:
    gr.Markdown("# ✨ Aiko AI Companion")
    with gr.Row():
        with gr.Column(scale=1, min_width=280):
            gr.HTML(aiko_card_html)
        with gr.Column(scale=2):
            gr.ChatInterface(
                fn=respond,
                multimodal=True  # Habilita botón para adjuntar imágenes
            )

port = int(os.environ.get("PORT", 7860))

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=port)
