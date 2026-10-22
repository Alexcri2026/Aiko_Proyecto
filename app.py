import os
import json
import re
import urllib.parse
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

# --- MODELOS FIJOS DE GROQ (NUNCA CAMBIAR) ---
MODEL_CHAT = "openai/gpt-oss-120b"
MODEL_FAST = "openai/gpt-oss-20b"

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

def extract_key_facts_with_ai(user_message):
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
            model=MODEL_FAST,
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

# --- DETECCIÓN DIRECTA Y GENERACIÓN DE IMÁGENES ---
def check_image_generation_intent(message):
    """Detecta de forma directa e infalible si el usuario quiere una imagen."""
    msg = message.lower()
    keywords = [
        "dibuja", "dibújame", "dibujame", "crea una imagen", "genera una imagen", 
        "haz una imagen", "hazme una imagen", "haz un dibujo", "hazme un dibujo", 
        "imagen de", "dibujo de", "foto de", "hazme un arte"
    ]
    return any(kw in msg for kw in keywords)

def generate_image_url(user_prompt):
    """Limpia el mensaje, traduce la idea a un prompt optimizado y devuelve la URL de Pollinations.ai"""
    clean_prompt = user_prompt.lower()
    for kw in ["aiko", "dibuja", "dibújame", "dibujame", "crea una imagen de", "genera una imagen de", "haz una imagen de", "hazme una imagen de", "hazme un dibujo de", "haz un dibujo de", "imagen de", "dibujo de"]:
        clean_prompt = clean_prompt.replace(kw, "")
    
    clean_prompt = clean_prompt.strip()
    if not clean_prompt:
        clean_prompt = user_prompt

    try:
        translation_prompt = (
            f"Convert this image description into a detailed English prompt for AI art (anime style): '{clean_prompt}'. "
            "Output ONLY the English text without explanation or quotes."
        )
        completion = client.chat.completions.create(
            model=MODEL_FAST,
            messages=[{"role": "user", "content": translation_prompt}],
            temperature=0.5,
            max_tokens=60,
        )
        english_prompt = completion.choices[0].message.content.strip()
    except Exception:
        english_prompt = clean_prompt

    encoded_prompt = urllib.parse.quote(english_prompt)
    return f"https://pollinations.ai/p/{encoded_prompt}?width=800&height=600&seed=42&model=flux"

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

    text_content = str(message).strip()
    if not text_content:
        return "Por favor, escribe un mensaje."

    # 1. CASO GENERAR IMAGEN (DETECCIÓN RÁPIDA POR PALABRAS CLAVE)
    if check_image_generation_intent(text_content):
        image_url = generate_image_url(text_content)
        bot_response = f"¡Aquí tienes el dibujo que me pediste! 🌸✨\n\n![Dibujo de Aiko]({image_url})"
        
        memory = load_memory()
        memory["historial"].append({"role": "user", "content": text_content})
        memory["historial"].append({"role": "assistant", "content": bot_response})
        save_memory(memory)
        
        return bot_response

    # 2. CONVERSACIÓN NORMAL
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
            model=MODEL_CHAT,
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
    display: flex; flex-direction: column; align-items: center; justify-content: center
