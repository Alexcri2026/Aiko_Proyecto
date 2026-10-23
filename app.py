import os
import gradio as gr
from groq import Groq
from supabase import create_client, Client

# --- CONFIGURACIÓN DE CLIENTES Y CREDENCIALES ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Limpieza preventiva de la URL (quita barras finales si las hubiera)
if SUPABASE_URL:
    SUPABASE_URL = SUPABASE_URL.rstrip("/")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# --- PERSONALIDAD E INSTRUCCIÓN BASE DE AIKO ---
AIKO_BASE_INSTRUCTION = """
Eres Aiko, una compañera virtual amigable, empática, cercana y servicial. 
Mantienes conversaciones fluidas y naturales en español. Ayudas al usuario con sus notas, recuerdos y charla cotidiana.
"""

# --- FUNCIONES DE PERSISTENCIA EN SUPABASE ---
def load_memory():
    """Carga la memoria centralizada desde la fila id=1 en Supabase."""
    if not supabase:
        return {"historial": [], "recordatorios": [], "snippets": {}}
    try:
        response = supabase.table("aiko_memory").select("data").eq("id", 1).execute()
        if response.data and len(response.data) > 0:
            data = response.data[0].get("data", {})
            # Asegurar que existan las llaves básicas
            if "historial" not in data: data["historial"] = []
            if "recordatorios" not in data: data["recordatorios"] = []
            if "snippets" not in data: data["snippets"] = {}
            return data
    except Exception as e:
        print(f"❌ Error cargando memoria de Supabase: {e}")
    return {"historial": [], "recordatorios": [], "snippets": {}}

def save_memory(memory_data):
    """Guarda toda la estructura de memoria en la fila id=1 de Supabase."""
    if not supabase:
        return
    try:
        supabase.table("aiko_memory").update({"data": memory_data}).eq("id", 1).execute()
    except Exception as e:
        print(f"❌ Error guardando memoria en Supabase: {e}")

# --- HERRAMIENTA DE NOTAS Y RECORDATORIOS (BLINDADA) ---
def handle_reminders_tool(user_message):
    """Gestiona ver, borrar y guardar notas de forma directa e infalible."""
    if not user_message or not user_message.strip():
        return ""

    msg_lower = user_message.lower().strip()
    
    # 1. VER NOTAS
    keywords_ver = ["mis notas", "ver notas", "mis recordatorios", "ver recordatorios", "qué tengo anotado", "que tengo anotado"]
    if any(kw in msg_lower for kw in keywords_ver):
        memory = load_memory()
        recs = memory.get("recordatorios", [])
        if recs:
            lista_recs = "\n".join([f"- {r}" for r in recs])
            return f"\n[ACCIÓN REALIZADA]: Notas y recordatorios activos:\n{lista_recs}\n"
        else:
            return "\n[ACCIÓN REALIZADA]: No hay notas o recordatorios guardados.\n"

    # 2. BORRAR NOTAS
    keywords_borrar = ["borra notas", "borra recordatorios", "limpia notas", "borrar notas", "elimina notas"]
    if any(kw in msg_lower for kw in keywords_borrar):
        memory = load_memory()
        memory["recordatorios"] = []
        save_memory(memory)
        print("🗑️ Notas limpiadas en Supabase.")
        return "\n[ACCIÓN REALIZADA]: Has borrado todas las notas cotidianas.\n"

    # 3. GUARDAR NOTAS (Extracción automática de contenido)
    keywords_guardar = ["anota", "anotar", "recuérdame", "recuerdame", "apunta", "anotame", "guarda", "guardar nota", "nota que"]
    for kw in keywords_guardar:
        if kw in msg_lower:
            partes = user_message.split(kw)
            if len(partes) > 1:
                texto_nota = partes[1].strip(" :,-queQUE")
                if texto_nota:
                    memory = load_memory()
                    if "recordatorios" not in memory:
                        memory["recordatorios"] = []
                    
                    if texto_nota not in memory["recordatorios"]:
                        memory["recordatorios"].append(texto_nota)
                        save_memory(memory)
                        print(f"✅ ¡NOTA GUARDADA EN SUPABASE!: \"{texto_nota}\"")
                        return f"\n[ACCIÓN REALIZADA]: Guardada nota personal: \"{texto_nota}\".\n"

    return ""

def handle_snippets_tool(user_message):
    return ""

def get_memory_context():
    """Genera un resumen de los recordatorios activos para inyectarlos en el prompt del sistema."""
    memory = load_memory()
    recs = memory.get("recordatorios", [])
    contexto = ""
    if recs:
        contexto += "\nRecordatorios y notas actuales del usuario:\n" + "\n".join([f"- {r}" for r in recs])
    return contexto

# --- FUNCIÓN PRINCIPAL DE CHAT ---
def respond(message, history):
    print(f"📥 respond(): RECIBIDO MENSAJE: \"{message}\"")
    
    if not client:
        return "Error: La clave GROQ_API_KEY no está configurada."

    text_content = str(message).strip()
    if not text_content:
        return "Por favor, escribe un mensaje."

    # 1. Procesar herramientas y actualizar notas en Supabase
    reminder_context = handle_reminders_tool(text_content)
    snippet_context = handle_snippets_tool(text_content)
    
    # 2. CARGAR FRESCO DESDE SUPABASE (Evita pérdida de memoria tras inactividad en Render)
    memory = load_memory()

    tool_execution_context = reminder_context + snippet_context
    full_system_instruction = AIKO_BASE_INSTRUCTION + "\n" + get_memory_context() + tool_execution_context
    messages = [{"role": "system", "content": full_system_instruction}]

    # 3. Cargar historial guardado (últimos 20 mensajes)
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
            temperature=0.7,
            max_tokens=512,
        )
        bot_response = completion.choices[0].message.content.strip()

        # 4. Registrar interacción y GUARDAR INMEDIATAMENTE EN SUPABASE
        memory["historial"].append({"role": "user", "content": text_content})
        memory["historial"].append({"role": "assistant", "content": bot_response})
        save_memory(memory)

        print("📤 respond(): RESPUESTA ENVIADA Y GUARDADA EN SUPABASE.")
        return bot_response
    except Exception as e:
        print(f"❌ respond(): Error procesando con Groq: {e}")
        return f"Ocurrió un error: {str(e)}"

# --- INTERFAZ DE GRADIO ---
demo = gr.ChatInterface(
    fn=respond,
    title="Aiko - Tu Compañera Virtual",
    description="Conversa con Aiko y pídele que guarde notas o recordatorios.",
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.launch(server_name="0.0.0.0", server_port=port)
