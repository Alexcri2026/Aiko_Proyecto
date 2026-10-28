import os
import base64
import tempfile
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from groq import Groq
from supabase import create_client, Client
from elevenlabs import ElevenLabs
from googlesearch import search

app = FastAPI(title="Aiko AI App")

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

# --- FUNCIÓN DE VOZ ELEVENLABS (BASE64) ---
def text_to_speech_base64(text_response):
    if not eleven_client or not text_response:
        return None
    try:
        audio_generator = eleven_client.text_to_speech.convert(
            voice_id=AIKO_VOICE_ID,
            model_id="eleven_multilingual_v2",
            text=text_response,
            output_format="mp3_44105_128",
        )
        audio_bytes = b"".join(audio_generator)
        return base64.b64encode(audio_bytes).decode("utf-8")
    except Exception as e:
        print(f"Error en ElevenLabs TTS: {e}")
        return None

# --- HERRAMIENTA DE BÚSQUEDA WEB (GOOGLE) ---
def perform_web_search(user_message):
    if not user_message or not str(user_message).strip():
        return ""
    msg_lower = str(user_message).lower()
    search_keywords = ["busca", "buscar", "noticias", "quién es", "quien es", "qué es", "que es", "actualidad", "clima", "precio", "hoy", "resultados", "último sobre"]
    if not any(kw in msg_lower for kw in search_keywords):
        return ""
    try:
        resultados_urls = list(search(user_message, num_results=3, lang="es"))
        if resultados_urls:
            formatted_results = "\n".join([f"- {url}" for url in resultados_urls])
            return f"\n[INFORMACIÓN ACTUALIZADA OBTENIDA DE LA WEB]:\n{formatted_results}\n"
    except Exception as e:
        print(f"Error en búsqueda web: {e}")
    return ""

def handle_reminders_tool(user_message):
    if not user_message or not str(user_message).strip():
        return "", False
    msg_lower = str(user_message).lower().strip()
    
    keywords_ver = ["mis notas", "ver notas", "mis recordatorios", "ver recordatorios", "qué tengo anotado", "que tengo anotado"]
    if any(kw in msg_lower for kw in keywords_ver):
        memory = load_memory()
        recs = memory.get("recordatorios", [])
        if recs:
            lista_recs = "\n".join([f"- {r}" for r in recs])
            return f"\n[ACCIÓN REALIZADA]: Notas y recordatorios activos:\n{lista_recs}\n", False
        return "\n[ACCIÓN REALIZADA]: No hay notas o recordatorios guardados.\n", False

    keywords_borrar = ["borra notas", "borra recordatorios", "limpia notas", "borrar notas", "elimina notas"]
    if any(kw in msg_lower for kw in keywords_borrar):
        memory = load_memory()
        memory["recordatorios"] = []
        save_memory(memory)
        return "\n[ACCIÓN REALIZADA]: Has borrado todas las notas cotidianas.\n", False

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
                        return f"\n[ACCIÓN REALIZADA]: Guardada nota personal o recordatorio: \"{texto_nota}\".\n", True
    return "", False

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

def get_best_chat_model():
    return "openai/gpt-oss-120b"

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

@app.post("/api/chat")
async def chat_endpoint(message: str = Form(None), audio: UploadFile = File(None), voice_enabled: bool = Form(False)):
    user_message = message
    
    if (not user_message or not user_message.strip()) and audio:
        suffix = os.path.splitext(audio.filename)[1] or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
            temp.write(await audio.read())
            temp_path = temp.name
        user_message = transcribe_audio_with_whisper(temp_path)
        try:
            os.unlink(temp_path)
        except:
            pass

    if not user_message or not user_message.strip():
        return JSONResponse({"error": "Mensaje vacío"}, status_code=400)

    model_to_use = get_best_chat_model()
    
    reminder_context, note_saved = handle_reminders_tool(user_message)
    web_search_context = perform_web_search(user_message)
    extract_key_facts_with_ai(user_message, model_to_use)
    
    memory = load_memory()
    full_system_instruction = AIKO_BASE_INSTRUCTION + "\n" + get_memory_context() + "\n" + reminder_context + "\n" + web_search_context
    messages = [{"role": "system", "content": full_system_instruction}]

    for entry in memory.get("historial", [])[-20:]:
        if isinstance(entry, dict):
            messages.append({"role": entry.get("role", "user"), "content": str(entry.get("content", ""))})

    messages.append({"role": "user", "content": str(user_message)})

    try:
        completion = client.chat.completions.create(
            model=model_to_use,
            messages=messages,
            temperature=0.8,
            max_tokens=256,
        )
        bot_response = completion.choices[0].message.content.strip()

        memory["historial"].append({"role": "user", "content": user_message})
        memory["historial"].append({"role": "assistant", "content": bot_response})
        save_memory(memory)

        response_data = {
            "user_message": user_message,
            "bot_response": bot_response,
            "note_saved": note_saved
        }

        if voice_enabled and eleven_client:
            audio_b64 = text_to_speech_base64(bot_response)
            if audio_b64:
                response_data["audio_base64"] = audio_b64

        return response_data

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/reminders")
async def get_reminders_api():
    memory = load_memory()
    return {"recordatorios": memory.get("recordatorios", [])}

@app.get("/", response_class=HTMLResponse)
async def get_frontend():
    return """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Aiko AI Companion</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @keyframes floatAnim {
            0%, 100% { transform: translateY(0px); }
            50% { transform: translateY(-6px); }
        }
        .animate-float { animation: floatAnim 4.5s ease-in-out infinite; }
    </style>
</head>
<body class="bg-gradient-to-br from-slate-50 to-pink-50 h-screen flex flex-col justify-between overflow-hidden font-sans">

    <!-- Modal / Video Flotante de Nota Guardada -->
    <div id="noteModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm opacity-0 pointer-events-none transition-opacity duration-300">
        <div class="bg-white/90 backdrop-blur-md p-4 rounded-3xl shadow-2xl border border-pink-200 flex flex-col items-center max-w-xs w-full mx-4">
            <h3 class="font-bold text-slate-700 text-sm mb-2">¡Aiko anotando tu nota! 🌸</h3>
            <video id="noteVideo" src="https://raw.githubusercontent.com/Alexcri2026/Aiko_Proyecto/main/Aiko_note.mp4" class="w-full h-64 rounded-2xl object-cover object-top shadow-md" muted playsinline></video>
        </div>
    </div>

    <!-- Notificación Flotante de Alarma / Recordatorio -->
    <div id="alarmBanner" class="fixed top-5 right-5 z-50 transform translate-y-[-150%] transition-transform duration-500 bg
