import os
import json
import re
import urllib.parse
import gradio as gr
import requests
from groq import Groq
from supabase import create_client, Client
from duckduckgo_search import DDGS

print("🚀 INICIANDO APLICACIÓN AIKO DEPOSITANDO LOGS DE DIAGNÓSTICO...")

# --- CONFIGURACIÓN DE CLIENTES ---
api_key = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=api_key) if api_key else None

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

print(f"🔍 ESTADO DE VARIABLES: SUPABASE_URL={'OK' if SUPABASE_URL else 'FALTA'}, SUPABASE_KEY={'OK' if SUPABASE_KEY else 'FALTA'}")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ CLIENTE SUPABASE CREADO CORRECTAMENTE.")
    except Exception as e:
        print(f"❌ ERROR CREANDO CLIENTE SUPABASE: {e}")
else:
    print("⚠️ SUPABASE NO CONFIGURADO: Faltan variables de entorno.")

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
    "snippets": [],
    "historial": []
}

# --- MODELOS FIJOS DE GROQ ---
MODEL_CHAT = "openai/gpt-oss-120b"
MODEL_FAST = "openai/gpt-oss-20b"

MEMORY_LOADED_SUCCESSFULLY = False

# --- FUNCIONES DE MEMORIA ROBUSTA (SUPABASE) ---
def load_memory():
    """Carga la memoria directamente desde Supabase con blindaje contra pérdidas."""
    global MEMORY_LOADED_SUCCESSFULLY

    if not supabase:
        print("⚠️ load_memory(): Supabase no está instanciado.")
        return DEFAULT_MEMORY.copy()

    try:
        print("📡 load_memory(): Consultando la tabla 'aiko_memory' en Supabase...")
        response = supabase.table("aiko_memory").select("data").eq("id", 1).execute()
        if response.data and len(response.data) > 0:
            data = response.data[0].get("data", {})
            if isinstance(data, dict):
                data.setdefault("historial", [])
                data.setdefault("usuario", DEFAULT_MEMORY["usuario"])
                data.setdefault("datos_clave", DEFAULT_MEMORY["datos_clave"])
                data.setdefault("recordatorios", [])
                data.setdefault("snippets", [])
                data.setdefault("estado_animo", "alegre 🌸")
                
                MEMORY_LOADED_SUCCESSFULLY = True
                print("✅ load_memory(): Memoria cargada exitosamente desde Supabase.")
                return data
        else:
            print("⚠️ load_memory(): La consulta a Supabase volvió vacía (no existe id=1).")
    except Exception as e:
        print(f"❌ load_memory(): Error al conectar con Supabase: {e}")

    return DEFAULT_MEMORY.copy()

def save_memory(memory_data):
    """Guarda en Supabase únicamente si la carga previa fue válida."""
    global MEMORY_LOADED_SUCCESSFULLY

    if not supabase or not memory_data or not isinstance(memory_data, dict):
        return

    if not MEMORY_LOADED_SUCCESSFULLY:
        print("⚠️ save_memory(): Omitido para proteger la base de datos contra sobrescrituras.")
        return

    try:
        supabase.table("aiko_memory").update({"data": memory_data}).eq("id", 1).execute()
        print("✅ save_memory(): Memoria actualizada correctamente en Supabase.")
    except Exception as e:
        print(f"❌ save_memory(): Error guardando en Supabase: {e}")

# --- BRAZO 1: HERRAMIENTA DE NOTAS Y RECORDATORIOS ---
def handle_reminders_tool(user_message):
    if not client or not user_message.strip():
        return ""

    msg_lower = user_message.lower()
    keywords_notas = ["anota", "anotar", "recuérdame", "recuerdame", "recordatorio", "guarda en notas", "mis notas", "mis recordatorios", "borra notas", "borra recordatorios", "limpia notas"]
    if not any(kw in msg_lower for kw in keywords_notas):
        return ""

    prompt = (
        "Analiza el siguiente mensaje. Determina si pide gestionar notas o recordatorios cotidianos.\n"
        "Opciones:\n"
        "1. GUARDAR: Si pide recordar/anotar una tarea cotidiana (ej: 'anota comprar leche'). Extrae la tarea.\n"
        "2. VER: Si pregunta por sus notas o tareas cotidianas pendientes.\n"
        "3. BORRAR: Si pide borrar todas las notas/recordatorios.\n"
        "4. NINGUNO: Si es código, snippet o comentario casual.\n\n"
        "Responde ÚNICAMENTE en JSON plano:\n"
        '{"accion": "GUARDAR" | "VER" | "BORRAR" | "NINGUNO", "texto": "tarea exacta si es GUARDAR"}\n\n'
        f"Mensaje: \"{user_message}\""
    )

    try:
        completion = client.chat.completions.create(
            model=MODEL_FAST,
            messages=[{"role": "system", "content": "Clasificador JSON de notas."},
                      {"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=100,
            tool_choice="none"
        )
        res_text = completion.choices[0].message.content.strip()
        res_text = re.sub(r'```json|```', '', res_text).strip()
        data = json.loads(res_text)

        accion = data.get("accion", "NINGUNO")
        texto = data.get("texto", "").strip()

        memory = load_memory()

        if accion == "GUARDAR" and texto:
            if texto not in memory.get("recordatorios", []):
                memory["recordatorios"].append(texto)
                save_memory(memory)
                return f"\n[ACCIÓN REALIZADA]: Guardada nota personal: \"{texto}\".\n"

        elif accion == "VER":
            recs = memory.get("recordatorios", [])
            if recs:
                lista_recs = "\n".join([f"- {r}" for r in recs])
                return f"\n[ACCIÓN REALIZADA]: Notas y recordatorios activos:\n{lista_recs}\n"
            else:
                return "\n[ACCIÓN REALIZADA]: No hay notas o recordatorios guardados.\n"

        elif accion == "BORRAR":
            memory["recordatorios"] = []
            save_memory(memory)
            return "\n[ACCIÓN REALIZADA]: Has borrado todas las notas cotidianas.\n"

    except Exception as e:
        print(f"Error en herramienta de recordatorios: {e}")

    return ""

# --- BRAZO 2: HERRAMIENTA DE BIBLIOTECA DE SNIPPETS TÉCNICOS ---
def handle_snippets_tool(user_message):
    if not client or not user_message.strip():
        return ""

    msg_lower = user_message.lower()
    keywords_snippets = ["snippet", "código", "codigo", "comando", "función", "funcion", "script", "terminal", "mis snippets", "mis comandos", "borra snippets", "borra comandos"]
    if not any(kw in msg_lower for kw in keywords_snippets):
        return ""

    prompt = (
        "Analiza si el usuario quiere guardar, consultar o borrar un snippet/comando de programación.\n"
        "Opciones:\n"
        "1. GUARDAR: Si pide guardar un snippet o comando (ej: 'guarda este comando: git commit'). Extrae el código.\n"
        "2. VER: Si pide ver sus snippets o comandos guardados.\n"
        "3. BORRAR: Si pide borrar todos los snippets/comandos.\n"
        "4. NINGUNO: Si es otro tema.\n\n"
        "Responde ÚNICAMENTE en JSON plano:\n"
        '{"accion": "GUARDAR" | "VER" | "BORRAR" | "NINGUNO", "codigo": "fragmento o comando a guardar si es GUARDAR"}\n\n'
        f"Mensaje: \"{user_message}\""
    )

    try:
        completion = client.chat.completions.create(
            model=MODEL_FAST,
            messages=[{"role": "system", "content": "Clasificador JSON de snippets técnicos."},
                      {"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=150,
            tool_choice="none"
        )
        res_text = completion.choices[0].message.content.strip()
        res_text = re.sub(r'```json|```', '', res_text).strip()
        data = json.loads(res_text)

        accion = data.get("accion", "NINGUNO")
        codigo = data.get("codigo", "").strip()

        memory = load_memory()

        if accion == "GUARDAR" and codigo:
            if codigo not in memory.get("snippets", []):
                memory["snippets"].append(codigo)
                save_memory(memory)
                return f"\n[ACCIÓN REALIZADA]: Guardado snippet técnico en la biblioteca: \"{codigo}\".\n"

        elif accion == "VER":
            snips = memory.get("snippets", [])
            if snips:
                lista_snips = "\n".join([f"```\n{s}\n```" for s in snips])
                return f"\n[ACCIÓN REALIZADA]: Biblioteca de Snippets guardados:\n{lista_snips}\n"
            else:
                return "\n[ACCIÓN REALIZADA]: La biblioteca de snippets está vacía actualmente.\n"

        elif accion == "BORRAR":
            memory["snippets"] = []
            save_memory(memory)
            return "\n[ACCIÓN REALIZADA]: Se ha limpiado toda la biblioteca de snippets técnicos.\n"

    except Exception as e:
        print(f"Error en herramienta de snippets: {e}")

    return ""

def extract_key_facts_with_ai(user_message, is_tool_action):
    if not client or not user_message.strip() or is_tool_action:
        return

    extraction_prompt = (
        "Analiza el mensaje. Si el usuario revela un gusto, preferencia o dato personal sobre él mismo "
        "(ej: 'me gusta el café', 'estudio Python'), extráelo en una frase corta.\n"
        "Si NO hay ningún dato personal nuevo, responde ÚNICAMENTE: NINGUNO.\n\n"
        f"Mensaje: \"{user_message}\""
    )
    try:
        completion = client.chat.completions.create(
            model=MODEL_FAST,
            messages=[{"role": "system", "content": "Extractor de datos personales sobre el usuario."},
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
        print(f"Error extrayendo hechos: {e}")

def update_mood_with_ai(user_message):
    if not client or not user_message.strip():
        return
    prompt = (
        "Elige un estado de ánimo para Aiko entre: 'alegre', 'cariñosa', 'pensativa', 'entusiasmada', 'tranquila'. "
        "Responde ÚNICAMENTE con una palabra.\n\n"
        f"Mensaje: \"{user_message}\""
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
    context += f"- Estado de ánimo: {memory.get('estado_animo', 'alegre')}\n"
    if memory.get("usuario"):
        for k, v in memory.get("usuario", {}).items():
            context += f"- {k.capitalize()}: {v}\n"
    if memory.get("datos_clave"):
        context += "- Gustos y hechos recordados:\n"
        for item in memory.get("datos_clave", []):
            context += f"  * {item}\n"
    if memory.get("recordatorios"):
        context += "- Notas y Recordatorios cotidianos:\n"
        for rec in memory.get("recordatorios", []):
            context += f"  * {rec}\n"
    if memory.get("snippets"):
        context += "- Snippets y Comandos guardados:\n"
        for snip in memory.get("snippets", []):
            context += f"  * {snip}\n"
    context += "====================================================\n"
    return context

# --- BÚSQUEDA WEB Y CLIMA ---
def check_web_search_intent(message):
    msg = message.lower()
    keywords = ["clima", "tiempo", "temperatura", "noticias", "precio", "resultado", "busca", "internet", "web", "actualidad"]
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
                return f"\n[DATOS OBTENIDOS DE LA RED]: Clima para {city}: {r.text.strip()}\n"
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

    return None

AIKO_BASE_INSTRUCTION = (
    "Eres Aiko, una chica virtual cercana, dulce y amigable con estética anime.\n"
    "CAPACIDADES Y BRAZOS:\n"
    "- Gestiones independientes para: 'Notas cotidianas' y 'Biblioteca de Snippets/Comandos técnicos'.\n"
    "- Si hay un bloque '[ACCIÓN REALIZADA]', responde confirmando la acción o mostrando la información de forma clara y cariñosa.\n"
    "- Mantén respuestas breves (1 a 3 oraciones) y con personalidad."
)

def respond(message, history):
    print(f"📥 respond(): RECIBIDO MENSAJE DEL USUARIO: \"{message}\"")
    
    if not client:
        return "Error: La clave GROQ_API_KEY no está configurada."

    text_content = str(message).strip()
    if not text_content:
        return "Por favor, escribe un mensaje."

    reminder_context = handle_reminders_tool(text_content)
    snippet_context = handle_snippets_tool(text_content)
    
    is_tool_action = bool(reminder_context or snippet_context)

    extract_key_facts_with_ai(text_content, is_tool_action)
    update_mood_with_ai(text_content)
    memory = load_memory()

    web_context = ""
    if check_web_search_intent(text_content):
        search_results = search_web(text_content)
        if search_results:
            web_context = "\n" + search_results

    tool_execution_context = reminder_context + snippet_context
    full_system_instruction = AIKO_BASE_INSTRUCTION + "\n" + get_memory_context() + tool_execution_context + web_context
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

        print("📤 respond(): RESPUESTA ENVIADA AL CHAT EXITOSAMENTE.")
        return bot_response
    except Exception as e:
        print(f"❌ respond(): Error procesando con Groq: {e}")
        return f"Ocurrió un error: {str(e)}"

# --- INTERFAZ GRADIO ---
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
    <p style="font-size: 13px; color: #666; margin: 0;">✨ Tu compañera con herramientas de tareas y código</p>
</div>
"""

with gr.Blocks(title="Aiko Companion") as demo:
    gr.Markdown("# ✨ Aiko AI Companion")
    with gr.Row():
        with gr.Column(scale=1, min_width=280):
            gr.HTML(aiko_card_html)
        with gr.Column(scale=2):
            gr.ChatInterface(fn=respond)

port = int(os.environ.get("PORT", 7860))

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=port)
