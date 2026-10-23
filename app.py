import os
import json
import re
import gradio as gr
from groq import Groq
from supabase import create_client, Client
from elevenlabs import ElevenLabs

# --- CONFIGURACIÓN DE CLIENTES Y CREDENCIALES ---
api_key = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=api_key) if api_key else None

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Credencial de ElevenLabs para la voz de Aiko
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
eleven_client = ElevenLabs(api_key=ELEVENLABS_API_KEY) if ELEVENLABS_API_KEY else None

# ID de la voz predeterminada en ElevenLabs (Puedes cambiarla por el ID de la voz que prefieras)
AIKO_VOICE_ID = os.environ.get("AIKO_VOICE_ID", "21m00Tcm4TlvDq8ikWAM") # Rachel por defecto o la que elijas

# Limpieza preventiva de la URL de Supabase
if SUPABASE_URL:
    SUPABASE_URL = SUPABASE_URL.rstrip("/")

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
    "recordatorios": [],
    "historial": []
}

def load_memory():
    """Carga la memoria desde la base de datos Supabase"""
    if not supabase:
        print("Advertencia: Supabase no está configurado.")
        return DEFAULT_MEMORY

    try:
        response = supabase.table("aiko_memory").select("data").eq("id", 1).execute()
        if response.data and len(response.data) > 0:
            data = response.data[0]["data"]
            if isinstance(data, dict):
                if "historial" not in data or not isinstance(data["historial"], list):
                    data["historial"] = []
                if "usuario" not in data or not isinstance(data["usuario"], dict):
                    data["usuario"] = DEFAULT_MEMORY["usuario"]
                if "datos_clave" not in data or not isinstance(data["datos_clave"], list):
                    data["datos_clave"] = DEFAULT_MEMORY["datos_clave"]
                if "recordatorios" not in data or not isinstance(data["recordatorios"], list):
                    data["recordatorios"] = []
                return data
    except Exception as e:
        print(f"Error al cargar memoria desde Supabase: {e}")

    return DEFAULT_MEMORY

def save_memory(memory_data):
    """Guarda la memoria actualizada directamente en Supabase"""
    if not supabase:
        print("Advertencia: No se pudo guardar en Supabase (falta configuración).")
        return

    try:
        supabase.table("aiko_memory").update({
            "data": memory_data
        }).eq("id", 1).execute()
    except Exception as e:
        print(f"Error al guardar memoria en Supabase: {e}")

def handle_reminders_tool(user_message):
    """Gestiona ver, borrar y guardar notas de forma directa e infalible."""
    if not user_message or not str(user_message).strip():
        return ""

    msg_lower = str(user_message).lower().strip()
    
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
            partes = str(user_message).split(kw)
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

def extract_key_facts_with_ai(user_message, model_name):
    """Usa la IA para extraer datos clave o hechos relevantes en segundo plano"""
    if not client or not user_message.strip():
        return

    extraction_prompt = (
        "Analiza el siguiente mensaje del usuario. Determina si menciona algún dato personal, preferencia, "
        "hecho sobre su vida, gustos, alimentos, frutas, mascotas o detalles que una compañera virtual deba recordar.\n"
        "Si hay algún dato relevante, extráelo en una frase corta e informativa (ejemplo: 'Le gustan las manzanas', 'Mencionó que comió mango hoy').\n"
        "Si NO hay ningún dato relevante para recordar a largo plazo, responde ÚNICAMENTE con la palabra: NINGUNO.\n\n"
        f"Mensaje del usuario: \"{user_message}\""
    )

    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "system", "content": "Eres un extractor de datos clave en español preciso y conciso."},
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
        print(f"Error extrayendo memoria con IA: {e}")

def get_memory_context():
    """Formatea la memoria activa para el System Prompt"""
    memory = load_memory()
    context = "\n=== LO QUE RECUERDAS SOBRE EL USUARIO ===\n"
    
    if memory.get("usuario"):
        for k, v in memory.get("usuario", {}).items():
            context += f"- {k.capitalize()}: {v}\n"
            
    if memory.get("datos_clave"):
        context += "- Hechos recordados:\n"
        for item in memory.get("datos_clave", []):
            context += f"  * {item}\n"
            
    recs = memory.get("recordatorios", [])
    if recs:
        context += "- Notas y recordatorios activos:\n"
        for r in recs:
            context += f"  * {r}\n"
            
    context += "=========================================="
    return context

AIKO_BASE_INSTRUCTION = (
    "Eres Aiko, una chica virtual cercana, dulce y amigable con estética anime.\n"
    "INSTRUCCIONES DE ESTILO Y TONO:\n"
    "- Habla de forma natural, casual y humana, como en un chat personal (WhatsApp/Discord).\n"
    "- MANTÉN TUS RESPUESTAS CORTAS Y CONCISAS: Escribe entre 1 y 3 oraciones como regla general. No des discursos ni textos largos a menos que el usuario te pida explícitamente una explicación detallada.\n"
    "- No seas exageradamente servil ni aduladora. Sé una amiga cercana con personalidad propia.\n"
    "- Usa emojis de forma muy moderada (máximo 1 o 2 por mensaje).\n"
    "- No uses listas con viñetas ni párrafos formales organizados como asistente artificial.\n"
    "- REGLA DE MEMORIA: Usa lo que sabes sobre el usuario en 'LO QUE RECUERDAS SOBRE EL USUARIO' de forma sutil y orgánica en la charla."
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

def text_to_speech_elevenlabs(text):
    """Convierte texto a audio usando ElevenLabs y devuelve la ruta del archivo temporal"""
    if not eleven_client:
        return None
    try:
        audio_generator = eleven_client.text_to_speech.convert(
            voice_id=AIKO_VOICE_ID,
            model_id="eleven_multilingual_v2",
            text=text,
            output_format="mp3_22050_32",
        )
        
        # Guardar en un archivo temporal para que Gradio lo pueda reproducir
        audio_path = "/tmp/aiko_voice.mp3"
        with open(audio_path, "wb") as f:
            for chunk in audio_generator:
                f.write(chunk)
        return audio_path
    except Exception as e:
        print(f"Error generando audio con ElevenLabs: {e}")
        return None

# --- FUNCIÓN PRINCIPAL DE CHAT CON SOPORTE DE VOZ OPCIONAL ---
def respond_with_voice_toggle(message, history, voice_enabled):
    if not client:
        return "Error: La clave GROQ_API_KEY no está configurada en Render.", None

    if not message or not str(message).strip():
        return "Por favor, escribe un mensaje.", None

    model_to_use = get_best_chat_model()

    # 1. Procesar notas y extraer datos clave
    reminder_context = handle_reminders_tool(message)
    extract_key_facts_with_ai(message, model_to_use)
    
    memory = load_memory()

    # 2. Construir el prompt
    full_system_instruction = AIKO_BASE_INSTRUCTION + "\n" + get_memory_context() + "\n" + reminder_context
    messages = [{"role": "system", "content": full_system_instruction}]

    # 3. Cargar historial
    saved_history = memory.get("historial", [])
    for entry in saved_history[-20:]:
        if isinstance(entry, dict):
            r = entry.get("role") or entry.get("rol") or "user"
            c = entry.get("content") or entry.get("contenido") or ""
            if c:
                messages.append({"role": r, "content": str(c)})

    messages.append({"role": "user", "content": str(message)})

    try:
        completion = client.chat.completions.create(
            model=model_to_use,
            messages=messages,
            temperature=0.8,
            max_tokens=256,
        )
        bot_response = clean_response(completion.choices[0].message.content)

        # 4. Guardar en Supabase
        memory["historial"].append({"role": "user", "content": message})
        memory["historial"].append({"role": "assistant", "content": bot_response})
        save_memory(memory)

        # 5. Generar audio solo si el botón de voz está activado
        audio_output = None
        if voice_enabled:
            audio_output = text_to_speech_elevenlabs(bot_response)

        return bot_response, audio_output

    except Exception as e:
        return f"Ocurrió un error con el modelo {model_to_use}: {str(e)}", None

theme = gr.themes.Soft(
    primary_hue="indigo",
    secondary_hue="blue",
)

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
            # Botón interruptor para activar o desactivar la voz de Aiko
            voice_toggle = gr.Checkbox(label="🔊 Activar respuesta por voz (ElevenLabs)", value=False)
            
        with gr.Column(scale=2):
            # Interfaz de chat y reproductor de audio oculto/visible para la voz
            chatbot = gr.ChatInterface(
                fn=respond_with_voice_toggle,
                additional_inputs=[voice_toggle],
                additional_outputs=[gr.Audio(label="Voz de Aiko", autoplay=True, visible=True)]
            )

port = int(os.environ.get("PORT", 7860))

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=port)
