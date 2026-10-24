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

# --- CSS PERSONALIZADO PARA LA CÁPSULA ESTILO GEMINI ---
custom_css = """
@keyframes floatAnim {
    0%, 100% { transform: translateY(0px); }
    50% { transform: translateY(-6px); }
}

.aiko-organic-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 22px;
    background: rgba(255, 255, 255, 0.6);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border-radius: 24px;
    border: 1px solid rgba(255, 255, 255, 0.9);
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.05);
}

.aiko-hero-image {
    width: 200px;
    height: 280px;
    border-radius: 20px;
    object-fit: cover;
    object-position: top center;
    box-shadow: 0 8px 24px rgba(255, 105, 180, 0.25);
    animation: floatAnim 4.5s ease-in-out infinite;
}

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

/* Burbujas del chat dinámicas con avatar */
.aiko-chat-container .message {
    border-radius: 18px !important;
    padding: 12px 16px !important;
    font-size: 14.5px !important;
}
.aiko-chat-container .bot-row .message {
    background: #ffffff !important;
    border: 1px solid #f0f0f5 !important;
    border-bottom-left-radius: 6px !important;
    box-shadow: 0 3px 10px rgba(0,0,0,0.03) !important;
}
.aiko-chat-container .user-row .message {
    background: linear-gradient(135deg, #ff7eb3 0%, #ff758c 100%) !important;
    color: white !important;
    border-bottom-right-radius: 6px !important;
    box-shadow: 0 3px 10px rgba(255, 117, 140, 0.25) !important;
}

/* Ocultar elementos auxiliares para que la interfaz quede limpia */
.element-hidden {
    display: none !important;
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
        # --- COLUMNA IZQUIERDA: PERFIL ORGÁNICO ---
        with gr.Column(scale=1, min_width=280):
            gr.HTML("""
                <div class="aiko-organic-card">
                    <img class="aiko-hero-image" src="https://raw.githubusercontent.com/Alexcri2026/Aiko_Proyecto/main/aiko.jpg" alt="Aiko 2D">
                    <h3 style="margin-top: 14px; color: #2d3748; font-weight: 700; margin-bottom: 0px; font-size: 20px;">Aiko 🌸</h3>
                    <div class="aiko-badge">
                        <span style="width:7px; height:7px; background-color:#38a169; border-radius:50%; display:inline-block;"></span>
                        En línea
                    </div>
                </div>
            """)
            voice_toggle = gr.Checkbox(label="🔊 Activar respuesta por voz (ElevenLabs)", value=False)
            audio_output = gr.Audio(label="Voz de Aiko", autoplay=True, interactive=False, visible=False)

        # --- COLUMNA DERECHA: CHAT Y BARRA ESTILO GEMINI ---
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(
                height=480, 
                placeholder="Escribe o habla con Aiko para comenzar...",
                avatar_images=(None, AIKO_AVATAR_URL),
                elem_classes="aiko-chat-container"
            )
            
            # Componentes reales de Gradio ocultos para enlazar la lógica
            with gr.Row(elem_classes="element-hidden"):
                msg_input = gr.Textbox(show_label=False)
                mic_input = gr.Audio(sources=["microphone"], type="filepath")
                send_btn = gr.Button("Enviar")

            # --- CÁPSULA FLOTANTE INTERACTIVA ESTILO GEMINI (HTML + JS) ---
            gr.HTML("""
                <div id="gemini-pill-container" style="
                    background: #ffffff;
                    border: 1px solid #e2e8f0;
                    border-radius: 40px;
                    padding: 8px 16px;
                    box-shadow: 0 8px 25px rgba(0, 0, 0, 0.06);
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    margin-top: 10px;
                    transition: all 0.3s ease;
                ">
                    <span style="font-size: 20px; color: #718096; cursor: pointer; padding: 0 4px;" title="Añadir">＋</span>
                    
                    <input id="custom-text-input" type="text" placeholder="Pregúntá..." style="
                        border: none;
                        outline: none;
                        flex-grow: 1;
                        font-size: 15px;
                        background: transparent;
                        color: #2d3748;
                    ">

                    <button id="custom-mic-btn" style="
                        background: transparent;
                        border: none;
                        cursor: pointer;
                        font-size: 18px;
                        padding: 6px;
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        color: #4a5568;
                    " title="Hablar con voz">🎙️</button>

                    <button id="custom-send-btn" style="
                        background: linear-gradient(135deg, #ff7eb3 0%, #ff758c 100%);
                        border: none;
                        cursor: pointer;
                        width: 38px;
                        height: 38px;
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        color: white;
                        box-shadow: 0 4px 12px rgba(255, 117, 140, 0.3);
                    " title="Enviar">🚀</button>
                </div>

                <script>
                setTimeout(() => {
                    const customInput = document.getElementById('custom-text-input');
                    const customSend = document.getElementById('custom-send-btn');
                    const customMic = document.getElementById('custom-mic-btn');

                    // Buscar los inputs reales de Gradio en el DOM
                    const gradioTextbox = document.querySelector('#' + CSS.escape('input-box') + ' textarea, .gradio-container textarea, input[type="text"]');
                    const gradioSendBtn = document.querySelector('button.primary');

                    if (customInput && gradioTextbox) {
                        customInput.addEventListener('keydown', function(e) {
                            if (e.key === 'Enter') {
                                gradioTextbox.value = customInput.value;
                                gradioTextbox.dispatchEvent(new Event('input', { bubbles: true }));
                                gradioTextbox.dispatchEvent(new Event('change', { bubbles: true }));
                                customInput.value = '';
                                
                                setTimeout(() => {
                                    const submitBtn = document.querySelector('button.primary');
                                    if (submitBtn) submitBtn.click();
                                }, 100);
                            }
                        });
                    }

                    if (customSend) {
                        customSend.addEventListener('click', function() {
                            const activeTextbox = document.querySelector('.gradio-container textarea, input[type="text"]');
                            if (activeTextbox && customInput.value.trim() !== '') {
                                activeTextbox.value = customInput.value;
                                activeTextbox.dispatchEvent(new Event('input', { bubbles: true }));
                                activeTextbox.dispatchEvent(new Event('change', { bubbles: true }));
                                customInput.value = '';

                                setTimeout(() => {
                                    const submitBtn = document.querySelector('button.primary');
                                    if (submitBtn) submitBtn.click();
                                }, 100);
                            }
                        });
                    }
                }, 1000);
                </script>
            """)

            # --- VINCULACIÓN DE EVENTOS BACKEND ---
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
