import os
import json
import re
import tempfile
import gradio as gr
from groq import Groq
from supabase import create_client, Client
from elevenlabs import ElevenLabs
from duckduckgo_search import DDGS

# --- CONFIGURACIÓN DE CLIENTES Y CREDENCIALES ---
api_key = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=api_key) if api_key else None

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
eleven_client = ElevenLabs(api_key=ELEVENLABS_API_KEY) if ELEVENLABS_API_KEY else None
AIKO_VOICE_ID = os.environ.get("AIKO_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

if SUPABASE_URL:
    SUPABASE_URL = SUPABASE_URL.rstrip("/")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if (SUPABASE_URL and SUPABASE_KEY) else None

DEFAULT_MEMORY = {
    "usuario": {"nombre": "Alex", "gustos": "Programación, desarrollo de IA, estética anime"},
    "datos_clave": ["Es el creador de Aiko", "Le gusta la estética 2D"],
    "recordatorios": [],
    "historial": []
}

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
                data.setdefault("recordatorios", [])
                return data
    except Exception as e:
        print(f"Error al cargar memoria: {e}")
    return DEFAULT_MEMORY

def save_memory(memory_data):
    if not supabase:
        return
    try:
        supabase.table("aiko_memory").update({"data": memory_data}).eq("id", 1).execute()
    except Exception as e:
        print(f"Error al guardar memoria: {e}")

# --- HERRAMIENTA DE BÚSQUEDA WEB (DUCKDUCKGO) ---
def perform_web_search(user_message):
    if not user_message or not str(user_message).strip():
        return ""
    
    msg_lower = str(user_message).lower()
    search_keywords = ["busca", "buscar", "noticias", "quién es", "quien es", "qué es", "que es", "actualidad", "clima", "precio", "hoy", "resultados", "último sobre"]
    
    if not any(kw in msg_lower for kw in search_keywords):
        return ""
        
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(user_message, max_results=3))
            if results:
                formatted_results = "\n".join([f"- {r.get('title', '')}: {r.get('body', '')}" for r in results])
                return f"\n[INFORMACIÓN ACTUALIZADA OBTENIDA DE LA WEB]:\n{formatted_results}\n"
    except Exception as e:
        print(f"Error en búsqueda DuckDuckGo: {e}")
    
    return ""

def handle_reminders_tool(user_message):
    if not user_message or not str(user_message).strip():
        return ""
    msg_lower = str(user_message).lower().strip()
    
    keywords_ver = ["mis notas", "ver notas", "mis recordatorios", "ver recordatorios", "qué tengo anotado", "que tengo anotado"]
    if any(kw in msg_lower for kw in keywords_ver):
        memory = load_memory()
        recs = memory.get("recordatorios", [])
        if recs:
            lista_recs = "\n".join([f"- {r}" for r in recs])
            return f"\n[ACCIÓN REALIZADA]: Notas y recordatorios activos:\n{lista_recs}\n"
        return "\n[ACCIÓN REALIZADA]: No hay notas o recordatorios guardados.\n"

    keywords_borrar = ["borra notas", "borra recordatorios", "limpia notas", "borrar notas", "elimina notas"]
    if any(kw in msg_lower for kw in keywords_borrar):
        memory = load_memory()
        memory["recordatorios"] = []
        save_memory(memory)
        return "\n[ACCIÓN REALIZADA]: Has borrado todas las notas cotidianas.\n"

    keywords_guardar = ["anota", "anotar", "recuérdame", "recuerdame", "apunta", "anotame", "guarda", "guardar nota", "nota que"]
    for kw in keywords_guardar:
        if kw in msg_lower:
            partes = str(user_message).split(kw)
            if len(partes) > 1:
                texto_nota = partes[1].strip(" :,-queQUE")
                if texto_nota:
                    memory = load_memory()
                    memory.setdefault("recordatorios", [])
                    if texto_nota not in memory["recordatorios"]:
                        memory["recordatorios"].append(texto_nota)
                        save_memory(memory)
                        return f"\n[ACCIÓN REALIZADA]: Guardada nota personal: \"{texto_nota}\".\n"
    return ""

def extract_key_facts_with_ai(user_message, model_name):
    if not client or not user_message.strip():
        return
    extraction_prompt = (
        "Analiza el siguiente mensaje del usuario. Determina si menciona algún dato personal, preferencia, "
        "hecho sobre su vida, gustos, alimentos, frutas, mascotas o detalles que una compañera virtual deba recordar.\n"
        "Si hay algún dato relevante, extráelo en una frase corta e informativa.\n"
        "Si NO hay ningún dato relevante, responde ÚNICAMENTE: NINGUNO.\n\n"
        f"Mensaje: \"{user_message}\""
    )
    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "system", "content": "Eres un extractor de datos clave."},
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
    recs = memory.get("recordatorios", [])
    if recs:
        context += "- Notas activas:\n"
        for r in recs:
            context += f"  * {r}\n"
    context += "=========================================="
    return context

AIKO_BASE_INSTRUCTION = (
    "Eres Aiko, una chica virtual cercana, dulce y amigable con estética anime.\n"
    "INSTRUCCIONES DE ESTILO Y TONO:\n"
    "- Habla de forma natural, casual y humana (WhatsApp/Discord).\n"
    "- RESPUESTAS CORTAS Y CONCISAS (1 a 3 oraciones).\n"
    "- Sé una amiga cercana con personalidad propia.\n"
    "- Usa emojis muy moderados (máximo 1 o 2)."
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
    return text.strip()

def transcribe_audio_with_whisper(audio_path):
    if not client or not audio_path:
        return ""
    try:
        with open(audio_path, "rb") as file:
            transcription = client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=file,
                language="es"
            )
            return transcription.text
    except Exception as e:
        print(f"Error en Whisper: {e}")
        return ""

def text_to_speech_elevenlabs(text):
    if not eleven_client:
        return None
    try:
        audio = eleven_client.generate(
            text=text,
            voice=AIKO_VOICE_ID,
            model="eleven_multilingual_v2"
        )
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        if isinstance(audio, bytes):
            temp_file.write(audio)
        else:
            for chunk in audio:
                temp_file.write(chunk)
        temp_file.close()
        return temp_file.name
    except Exception as e:
        print(f"Error en ElevenLabs: {e}")
        return None

def process_user_input(text_input, mic_audio, voice_enabled, history):
    if history is None:
        history = []

    user_message = text_input
    
    if not user_message and mic_audio:
        user_message = transcribe_audio_with_whisper(mic_audio)

    if not user_message or not str(user_message).strip():
        return history, None, "", None

    model_to_use = get_best_chat_model()
    reminder_context = handle_reminders_tool(user_message)
    web_search_context = perform_web_search(user_message)
    extract_key_facts_with_ai(user_message, model_to_use)
    
    memory = load_memory()
    full_system_instruction = AIKO_BASE_INSTRUCTION + "\n" + get_memory_context() + "\n" + reminder_context + "\n" + web_search_context
    messages = [{"role": "system", "content": full_system_instruction}]

    saved_history = memory.get("historial", [])
    for entry in saved_history[-20:]:
        if isinstance(entry, dict):
            r = entry.get("role", "user")
            c = entry.get("content", "")
            if c:
                messages.append({"role": r, "content": str(c)})

    messages.append({"role": "user", "content": str(user_message)})

    try:
        completion = client.chat.completions.create(
            model=model_to_use,
            messages=messages,
            temperature=0.8,
            max_tokens=256,
        )
        bot_response = clean_response(completion.choices[0].message.content)

        memory["historial"].append({"role": "user", "content": user_message})
        memory["historial"].append({"role": "assistant", "content": bot_response})
        save_memory(memory)

        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": bot_response})

        audio_output = None
        if voice_enabled:
            audio_output = text_to_speech_elevenlabs(bot_response)

        return history, audio_output, "", None

    except Exception as e:
        err_msg = f"Ocurrió un error: {str(e)}"
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": err_msg})
        return history, None, "", None

# --- CSS AVANZADO: GLASSMORPHISM, ANIMACIONES Y CÁPSULA FLOTANTE ---
custom_css = """
/* Animaciones principales */
@keyframes floatAnim {
    0%, 100% { transform: translateY(0px); }
    50% { transform: translateY(-8px); }
}

@keyframes slideUpFade {
    from {
        opacity: 0;
        transform: translateY(14px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@keyframes pulseGlow {
    0%, 100% { box-shadow: 0 0 15px rgba(255, 126, 179, 0.2); }
    50% { box-shadow: 0 0 25px rgba(255, 126, 179, 0.45); }
}

/* Contenedor general */
.gradio-container {
    background: linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%) !important;
}

/* 1. Tarjeta Orgánica de Aiko (Glassmorphism sin recuadro rígido) */
.aiko-organic-card {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background: rgba(255, 255, 255, 0.55);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border-radius: 24px;
    border: 1px solid rgba(255, 255, 255, 0.8);
    box-shadow: 0 12px 32px rgba(31, 38, 135, 0.06);
    margin-bottom: 12px;
}

.aiko-hero-image {
    width: 210px;
    height: 300px;
    border-radius: 22px;
    object-fit: cover;
    object-position: top center;
    box-shadow: 0 10px 30px rgba(255, 105, 180, 0.3);
    animation: floatAnim 4.5s ease-in-out infinite, pulseGlow 4s ease-in-out infinite;
    transition: transform 0.3s ease;
}

.aiko-hero-image:hover {
    transform: scale(1.02) translateY(-4px);
}

/* Status dot interactivo */
.aiko-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border-radius: 20px;
    background: rgba(56, 161, 105, 0.12);
    color: #276749;
    font-size: 12px;
    font-weight: 600;
    margin-top: 10px;
}

/* 2. Área del Chat e Historias con Burbujas Suaves */
.aiko-chat-container .message {
    animation: slideUpFade 0.35s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    border-radius: 20px !important;
    padding: 12px 18px !important;
    font-size: 15px !important;
}

.aiko-chat-container .bot-row .message {
    background: rgba(255, 255, 255, 0.85) !important;
    backdrop-filter: blur(8px);
    border: 1px solid rgba(230, 230, 250, 0.8) !important;
    border-bottom-left-radius: 6px !important;
    box-shadow: 0 4px 14px rgba(0,0,0,0.03) !important;
}

.aiko-chat-container .user-row .message {
    background: linear-gradient(135deg, #ff7eb3 0%, #7afcff 100%) !important;
    color: #1a202c !important;
    border-bottom-right-radius: 6px !important;
    box-shadow: 0 4px 14px rgba(255, 126, 179, 0.25) !important;
}

/* 3. Cápsula Flotante Inferior (Input, Micrófono y Enviar) */
.aiko-floating-capsule {
    background: rgba(255, 255, 255, 0.75) !important;
    backdrop-filter: blur(20px) !important;
    -webkit-backdrop-filter: blur(20px) !important;
    border-radius: 24px !important;
    padding: 8px 12px !important;
    border: 1px solid rgba(255, 255, 255, 0.9) !important;
    box-shadow: 0 10px 28px rgba(0, 0, 0, 0.08) !important;
    transition: all 0.3s ease !important;
}

.aiko-floating-capsule:focus-within {
    box-shadow: 0 12px 32px rgba(255, 126, 179, 0.2) !important;
    border-color: rgba(255, 126, 179, 0.5) !important;
}

/* Botones con transiciones fluidas */
button {
    border-radius: 18px !important;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

button:hover {
    transform: translateY(-2px) scale(1.02);
}

button:active {
    transform: translateY(0px) scale(0.98);
}
"""

theme = gr.themes.Soft(
    primary_hue="pink",
    secondary_hue="indigo",
)

AIKO_AVATAR_URL = "https://raw.githubusercontent.com/Alexcri2026/Aiko_Proyecto/main/aiko.jpg"

with gr.Blocks(theme=theme, css=custom_css, title="Aiko AI Companion") as demo:
    gr.Markdown("# ✨ Aiko AI Companion")
    
    with gr.Row():
        # --- COLUMNA IZQUIERDA: TARJETA ORGÁNICA (GLASSMORPHISM) ---
        with gr.Column(scale=1, min_width=280):
            gr.HTML("""
                <div class="aiko-organic-card">
                    <img class="aiko-hero-image" src="https://raw.githubusercontent.com/Alexcri2026/Aiko_Proyecto/main/aiko.jpg" alt="Aiko 2D">
                    <h3 style="margin-top: 14px; color: #2d3748; font-weight: 700; margin-bottom: 0px; font-size: 20px;">Aiko 🌸</h3>
                    <div class="aiko-badge">
                        <span style="width:7px; height:7px; background-color:#38a169; border-radius:50%; display:inline-block;"></span>
                        En línea y lista
                    </div>
                </div>
            """)
            voice_toggle = gr.Checkbox(label="🔊 Activar respuesta por voz (ElevenLabs)", value=False)
            audio_output = gr.Audio(label="Voz de Aiko", autoplay=True, interactive=False, visible=False)

        # --- COLUMNA DERECHA: CHAT CON BURBUJAS Y CÁPSULA FLOTANTE ---
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(
                height=480, 
                placeholder="Escribe o habla con Aiko para comenzar...",
                avatar_images=(None, AIKO_AVATAR_URL),
                elem_classes="aiko-chat-container"
            )
            
            # Cápsula unificada flotante inferior
            with gr.Group(elem_classes="aiko-floating-capsule"):
                with gr.Row(elem_id="input-dock-row"):
                    msg_input = gr.Textbox(show_label=False, placeholder="Escribe un mensaje a Aiko...", scale=5, container=False)
                    mic_input = gr.Audio(sources=["microphone"], type="filepath", label=None, show_label=False, scale=1, container=False)
                    send_btn = gr.Button("Enviar 🚀", variant="primary", scale=1)

            # --- VINCULACIÓN DE EVENTOS ---
            msg_input.submit(
                process_user_input, 
                inputs=[msg_input, mic_input, voice_toggle, chatbot], 
                outputs=[chatbot, audio_output, msg_input, mic_input]
            )
            send_btn.click(
                process_user_input, 
                inputs=[msg_input, mic_input, voice_toggle, chatbot], 
                outputs=[chatbot, audio_output, msg_input, mic_input]
            )

            mic_input.stop_recording(
                process_user_input,
                inputs=[msg_input, mic_input, voice_toggle, chatbot],
                outputs=[chatbot, audio_output, msg_input, mic_input]
            )

port = int(os.environ.get("PORT", 7860))

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=port)
