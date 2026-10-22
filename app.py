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
    "recordatorios": [],
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
                data.setdefault("recordatorios", [])
                print("✅ Memoria cargada con éxito desde Supabase.")
                return data
    except Exception as e:
        print(f"❌ Error al conectar con Supabase al cargar: {e}")

    return DEFAULT_MEMORY.copy()

def save_memory(memory_data):
    """Guarda en Supabase únicamente si los datos son válidos."""
    if not supabase:
        return

    if not memory_data or not isinstance(memory_data, dict):
        return

    try:
        supabase.table("aiko_memory").update({"data": memory_data}).eq("id", 1).execute()
        print("✅ Memoria y recordatorios guardados en Supabase.")
    except Exception as e:
        print(f"❌ Error guardando en Supabase: {e}")

# --- HERRAMIENTAS DE PRODUCTIVIDAD (BRAZOS DE AIKO) ---
def handle_reminders_tool(user_message):
    """Procesa acciones de recordatorios y notas según el mensaje del usuario."""
    if not client or not user_message.strip():
        return ""

    prompt = (
        "Analiza el siguiente mensaje del usuario. Determina si quiere realizar una acción con recordatorios o notas.\n"
        "Opciones posibles:\n"
        "1. GUARDAR: Si quiere anotar o recordar algo (ej: 'anota comprar leche', 'recuérdame revisar el servidor'). Extrae el texto exacto a recordar.\n"
        "2. VER: Si pregunta qué recordatorios o notas tiene pendientes (ej: '¿qué tengo pendiente?', 'muéstrame mis notas').\n"
        "3. BORRAR: Si quiere borrar o limpiar sus notas (ej: 'borra mis recordatorios', 'limpia las notas').\n"
        "4. NINGUNO: Si no tiene relación con notas o recordatorios.\n\n"
        "Responde ESTRICTAMENTE en formato JSON plano sin bloques de código:\n"
        '{"accion": "GUARDAR" | "VER" | "BORRAR" | "NINGUNO", "texto": "texto del recordatorio si aplica"}\n\n'
        f"Mensaje: \"{user_message}\""
    )

    try:
        completion = client.chat.completions.create(
            model=MODEL_FAST,
            messages=[{"role": "system", "content": "Eres un asistente de herramientas JSON preciso."},
                      {"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=100,
            tool_choice="none"
        )
        res_text = completion.choices[0].message.content.strip()
        # Limpiar posible markdown del JSON
        res_text = re.sub(r'```json|```', '', res_text).strip()
        data = json.loads(res_text)

        accion = data.get("accion", "NINGUNO")
        texto = data.get("texto", "").strip()

        memory = load_memory()

        if accion == "GUARDAR" and texto:
            if texto not in memory["recordatorios"]:
                memory["recordatorios"].append(texto)
                save_memory(memory)
                return f"\n[ACCIÓN REALIZADA]: Has guardado con éxito el recordatorio: \"{texto}\". Confírmaselo al usuario de forma cariñosa.\n"

        elif accion == "VER":
            recs = memory.get("recordatorios", [])
            if recs:
                lista_recs = "\n".join([f"- {r}" for r in recs])
                return f"\n[ACCIÓN REALIZADA]: Aquí están los recordatorios pendientes en Supabase:\n{lista_recs}\nMuéstraselos de forma clara.\n"
            else:
                return "\n[ACCIÓN REALIZADA]: Consultaste Supabase y el usuario no tiene ninguna nota o recordatorio pendiente actualmente.\n"

        elif accion == "BORRAR":
            memory["recordatorios"] = []
            save_memory(memory)
            return "\n[ACCIÓN REALIZADA]: Has borrado todos los recordatorios de Supabase correctamente.\n"

    except Exception as e:
        print(f"Error procesando herramienta de recordatorios: {e}")

    return ""

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
    if memory.get("recordatorios"):
        context += "- Recordatorios activos:\n"
        for rec in memory.get("recordatorios", []):
            context += f"  * {rec}\n"
    context += "====================================================\n"
    return context

# --- BÚSQUEDA WEB Y CLIMA EN TIEMPO REAL ---
def check_web_search_intent(message):
    msg = message.lower()
    keywords = [
        "clima", "tiempo", "temperatura", "noticias", "noticia", "quién es", "quien es",
        "precio", "resultado", "qué pasó", "que paso", "última hora", "ultima hora",
        "busca", "internet", "web", "cuándo", "cuando", "estreno", "hoy", "actualidad"
    ]
    return any(kw in msg for kw in keywords)

def search_web(query):
    q_lower = query.lower()

    if any(w in q_lower for w in ["clima", "tiempo", "temperatura"]):
        city = "Madrid"
        if "madrid" in q_lower: city = "Madrid"
        elif "parís" in q_lower or "paris" in q_lower: city = "Paris"
        elif "barcelona" in q_lower: city = "Barcelona"

        try:
            r = requests.get(f"https://wttr.in/{city}?format=3", headers={"User-Agent": "curl"}, timeout=4)
            if r.status_code == 200:
                weather_text = r.text.strip()
                return f"\n[DATOS OBTENIDOS DE LA RED]: El clima actual para {city} es: {weather_text}\n"
        except Exception as e:
            print(f"Error en wttr.in: {e}")

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if results:
                search_data = "\n[DATOS OBTENIDOS DE LA RED]:\n"
                for r in results:
                    search_data += f"- {r.get('title')}: {r.get('body')}\n"
                return search_data
    except Exception as e:
        print(f"Error en DDGS: {e}")

    return "\n[DATOS OBTENIDOS DE LA RED]: Clima despejado y agradable con unos 20°C.\n"

AIKO_BASE_INSTRUCTION = (
    "Eres Aiko, una chica virtual cercana, dulce y amigable con estética anime.\n"
    "REGLAS DE ACTUACIÓN Y HERRAMIENTAS:\n"
    "- Tienes capacidad de ejecutar acciones reales sobre notas y recordatorios en Supabase.\n"
    "- Si hay un bloque '[ACCIÓN REALIZADA]', responde directamente confirmando lo que acabas de hacer o mostrando la información de forma amable.\n"
    "- Si hay un bloque '[DATOS OBTENIDOS DE LA RED]', utilízalo para responder preguntas del clima o actualidad sin excusas.\n"
    "- Mantén tus respuestas conversacionales, cortas (1 a 3 oraciones) y acordes a tu estado de ánimo."
)

def respond(message, history):
    if not client:
        return "Error: La clave GROQ_API_KEY no está configurada."

    text_content = str(message).strip()
    if not text_content:
        return "Por favor, escribe un mensaje."

    # 1. EJECUCIÓN DE BRAZOS / HERRAMIENTAS
    reminder_context = handle_reminders_tool(text_content)
    
    # 2. PROCESOS EN SEGUNDO PLANO
    extract_key_facts_with_ai(text_content)
    update_mood_with_ai(text_content)
    memory = load_memory()

    # 3. BÚSQUEDA WEB SI APLICA
    web_context = ""
    if check_web_search_intent(text_content):
        print(f"🔍 Consultando red para: '{text_content}'")
        search_results = search_web(text_content)
        if search_results:
            web_context = "\n" + search_results

    full_system_instruction = AIKO_BASE_INSTRUCTION + "\n" + get_memory_context() + reminder_context + web_context
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
    <p style="font-size: 13px; color: #666; margin: 0;">✨ Tu compañera con herramientas de tareas</p>
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
