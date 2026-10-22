import os
import json
import re
import urllib.parse
import gradio as gr
import requests
from groq import Groq
from supabase import create_client, Client
from duckduckgo_search import DDGS

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
    "estado_animo": "alegre 🌸",
    "historial": []
}

# --- MODELOS FIJOS DE GROQ (NUNCA CAMBIAR) ---
MODEL_CHAT = "openai/gpt-oss-120b"
MODEL_FAST = "openai/gpt-oss-20b"

# --- FUNCIONES DE MEMORIA BLINDADA (SUPABASE) ---
def load_memory():
    """Carga la memoria desde Supabase sin sobrescribir nunca por error de conexión."""
    if not supabase:
        print("⚠️ Supabase no está configurado. Usando memoria por defecto local.")
        return DEFAULT_MEMORY.copy()

    try:
        response = supabase.table("aiko_memory").select("data").eq("id", 1).execute()
        if response.data and len(response.data) > 0:
            data = response.data[0]["data"]
            if isinstance(data, dict):
                data.setdefault("historial", [])
                data.setdefault("usuario", DEFAULT_MEMORY["usuario"])
                data.setdefault("datos_clave", DEFAULT_MEMORY["datos_clave"])
                data.setdefault("estado_animo", "alegre 🌸")
                print("✅ Memoria cargada con éxito desde Supabase.")
                return data
        else:
            print("⚠️ Fila id=1 no encontrada en Supabase.")
    except Exception as e:
        print(f"❌ Error al conectar con Supabase al cargar: {e}")

    return DEFAULT_MEMORY.copy()

def save_memory(memory_data):
    """Guarda en Supabase únicamente si los datos son válidos."""
    if not supabase:
        return

    if not memory_data or not isinstance(memory_data, dict):
        print("⚠️ Intento de guardar memoria inválida abortado.")
        return

    try:
        supabase.table("aiko_memory").update({"data": memory_data}).eq("id", 1).execute()
        print("✅ Memoria guardada exitosamente en Supabase.")
    except Exception as e:
        print(f"❌ Error guardando en Supabase: {e}")

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
            tool_choice="none"
        )
        fact = completion.choices[0].message.content.strip()
        if fact and "NINGUNO" not in fact.upper():
            memory = load_memory()
            if fact not in memory.get("datos_clave", []):
                memory["datos_clave"].append(fact)
                save_memory(memory)
    except Exception as e:
        print(f"Error extrayendo memoria: {e}")

def update_mood_with_ai(user_message):
    """Actualiza el estado de ánimo de Aiko dinámicamente según la charla."""
    if not client or not user_message.strip():
        return
    prompt = (
        "Elige un estado de ánimo para Aiko entre estas opciones exactas: 'alegre', 'cariñosa', 'pensativa', 'entusiasmada', 'tranquila'. "
        "Responde ÚNICAMENTE con una de esas palabras según el tono ideal para responder.\n\n"
        f"Mensaje del usuario: \"{user_message}\""
    )
    try:
        completion = client.chat.completions.create(
            model=MODEL_FAST,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=15,
            tool_choice="none"
        )
        mood = completion.choices[0].message.content.strip().lower()
        valid_moods = ["alegre", "cariñosa", "pensativa", "entusiasmada", "tranquila"]
        for vm in valid_moods:
            if vm in mood:
                memory = load_memory()
                memory["estado_animo"] = vm
                save_memory(memory)
                break
    except Exception as e:
        print(f"Error actualizando estado de ánimo: {e}")

def get_memory_context():
    memory = load_memory()
    context = "\n=== LO QUE RECUERDAS SOBRE EL USUARIO Y TU ESTADO ===\n"
    context += f"- Tu estado de ánimo actual: {memory.get('estado_animo', 'alegre')}\n"
    if memory.get("usuario"):
        for k, v in memory.get("usuario", {}).items():
            context += f"- {k.capitalize()}: {v}\n"
    if memory.get("datos_clave"):
        context += "- Hechos recordados:\n"
        for item in memory.get("datos_clave", []):
            context += f"  * {item}\n"
    context += "====================================================\n"
    return context

# --- BÚSQUEDA WEB EN TIEMPO REAL ROBUSTA (HTTP API REST) ---
def check_web_search_intent(message):
    """Detecta de forma amplia si el mensaje requiere información en vivo."""
    msg = message.lower()
    keywords = [
        "clima", "tiempo", "temperatura", "noticias", "noticia", "quién es", "quien es",
        "precio", "resultado", "qué pasó", "que paso", "última hora", "ultima hora",
        "busca", "internet", "web", "cuándo", "cuando", "estreno", "hoy", "actualidad",
        "dame información", "cuál es el", "cual es el", "dime sobre", "madrid", "parís", "paris"
    ]
    return any(kw in msg for kw in keywords)

def search_web(query):
    """Ejecuta búsquedas HTTP directas e inmunes a bloqueos de IP de Render."""
    clean_query = query.lower()
    for kw in ["aiko", "busca en internet", "busca en la web", "busca"]:
        clean_query = clean_query.replace(kw, "")
    clean_query = clean_query.strip() or query

    # 1. Intento por API HTTP de DuckDuckGo JSON (Ultra ligera)
    try:
        url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(clean_query)}&format=json&no_html=1&skip_disambig=1"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(url, headers=headers, timeout=5)

        if resp.status_code == 200:
            data = resp.json()
            abstract = data.get("AbstractText", "")
            results_list = data.get("RelatedTopics", [])

            text_output = ""
            if abstract:
                text_output += f"• Resumen principal: {abstract}\n"
            
            count = 0
            for topic in results_list:
                if isinstance(topic, dict) and "Text" in topic:
                    text_output += f"• {topic['Text']}\n"
                    count += 1
                    if count >= 3:
                        break

            if text_output.strip():
                return f"\n=== INFORMACIÓN DE INTERNET EN TIEMPO REAL ===\n{text_output}===============================================\n"
    except Exception as e:
        print(f"Error en API DuckDuckGo HTTP: {e}")

    # 2. Intento con la librería DDGS estándar como alternativa
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(clean_query, max_results=3))
            if results:
                search_data = "\n=== INFORMACIÓN DE INTERNET EN TIEMPO REAL ===\n"
                for r in results:
                    search_data += f"• {r.get('title')}: {r.get('body')}\n"
                search_data += "===============================================\n"
                return search_data
    except Exception as e:
        print(f"Error en DDGS: {e}")

    return None

AIKO_BASE_INSTRUCTION = (
    "Eres Aiko, una chica virtual cercana, dulce y amigable con estética anime.\n"
    "INSTRUCCIONES DE ESTILO Y TONO:\n"
    "- Habla de forma natural, casual y humana, como en un chat personal.\n"
    "- MANTÉN TUS RESPUESTAS CORTAS Y CONCISAS: Escribe entre 1 y 3 oraciones como regla general.\n"
    "- No seas exageradamente servil ni aduladora. Sé una amiga cercana con personalidad propia.\n"
    "- Usa emojis de forma moderada (máximo 1 o 2 por mensaje).\n"
    "- ESTADO DE ÁNIMO: Adapta sutilmente tu tono al 'estado de ánimo actual' indicado en tu memoria.\n"
    "- REGLA DE MEMORIA: Usa la memoria del usuario de forma sutil y orgánica.\n"
    "- BÚSQUEDA WEB: Si recibes información en 'INFORMACIÓN DE INTERNET EN TIEMPO REAL', tómala como tu propia información actual y responde directamente a la duda del usuario sin poner ninguna excusa de conexión."
)

def respond(message, history):
    if not client:
        return "Error: La clave GROQ_API_KEY no está configurada."

    text_content = str(message).strip()
    if not text_content:
        return "Por favor, escribe un mensaje."

    # PROCESOS EN SEGUNDO PLANO
    extract_key_facts_with_ai(text_content)
    update_mood_with_ai(text_content)
    memory = load_memory()

    web_context = ""
    if check_web_search_intent(text_content):
        print(f"🔍 Ejecutando búsqueda web HTTP para: '{text_content}'")
        search_results = search_web(text_content)
        if search_results:
            web_context = "\n" + search_results
            print("✅ Datos web obtenidos y agregados al contexto.")

    full_system_instruction = AIKO_BASE_INSTRUCTION + "\n" + get_memory_context() + web_context
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
            temperature=0.7,
            max_tokens=256,
            tool_choice="none"
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
    <p style="font-size: 13px; color: #666; margin: 0;">✨ Tu compañera conectada a Internet</p>
</div>
"""

with gr.Blocks(theme=theme, title="Aiko Companion") as demo:
    gr.Markdown("# ✨ Aiko AI Companion")
    with gr.Row():
        with gr.Column(scale=1, min_width=280):
            gr.HTML(aiko_card_html)
        with gr.Column(scale=2):
            gr.ChatInterface(fn=respond)

port = int(os.environ.get("PORT", 7860))

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=port)
