import os
import tempfile
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from groq import Groq
from supabase import create_client, Client
from elevenlabs import ElevenLabs
from duckduckgo_search import DDGS

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
    
    # 1. Ver notas guardadas
    keywords_ver = ["mis notas", "ver notas", "mis recordatorios", "ver recordatorios", "qué tengo anotado", "que tengo anotado"]
    if any(kw in msg_lower for kw in keywords_ver):
        memory = load_memory()
        recs = memory.get("recordatorios", [])
        if recs:
            lista_recs = "\n".join([f"- {r}" for r in recs])
            return f"\n[ACCIÓN REALIZADA]: Notas y recordatorios activos:\n{lista_recs}\n"
        return "\n[ACCIÓN REALIZADA]: No hay notas o recordatorios guardados.\n"

    # 2. Borrar notas
    keywords_borrar = ["borra notas", "borra recordatorios", "limpia notas", "borrar notas", "elimina notas"]
    if any(kw in msg_lower for kw in keywords_borrar):
        memory = load_memory()
        memory["recordatorios"] = []
        save_memory(memory)
        return "\n[ACCIÓN REALIZADA]: Has borrado todas las notas cotidianas.\n"

    # 3. Guardar nueva nota o alarma
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
                        return f"\n[ACCIÓN REALIZADA]: Guardada nota personal o recordatorio: \"{texto_nota}\".\n"
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
    
    reminder_context = handle_reminders_tool(user_message)
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

        return {
            "user_message": user_message,
            "bot_response": bot_response
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# --- NUEVO ENDPOINT PARA CONSULTAR RECORDATORIOS EN VIVO ---
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

    <!-- Notificación Flotante de Alarma / Recordatorio -->
    <div id="alarmBanner" class="fixed top-5 right-5 z-50 transform translate-y-[-150%] transition-transform duration-500 bg-white/90 backdrop-blur-md border border-pink-300 p-4 rounded-2xl shadow-xl flex items-center space-x-3 max-w-sm">
        <span class="text-2xl">⏰</span>
        <div>
            <h4 class="font-bold text-slate-800 text-sm">¡Alarma de Aiko! 🌸</h4>
            <p id="alarmText" class="text-xs text-slate-600">Tienes un recordatorio pendiente.</p>
        </div>
        <button onclick="dismissAlarm()" class="text-slate-400 hover:text-slate-600 text-sm font-bold ml-auto">✕</button>
    </div>

    <!-- Header / Navbar -->
    <header class="bg-white/80 backdrop-blur-md border-b border-pink-100 py-3 px-6 flex items-center justify-between shadow-sm">
        <div class="flex items-center space-x-3">
            <img src="https://raw.githubusercontent.com/Alexcri2026/Aiko_Proyecto/main/aiko.jpg" class="w-10 h-10 rounded-full object-cover border-2 border-pink-400 shadow-sm" alt="Aiko">
            <div>
                <h1 class="font-bold text-slate-800 text-sm">Aiko 🌸</h1>
                <span class="text-xs text-emerald-600 font-medium flex items-center gap-1"><span class="w-2 h-2 bg-emerald-500 rounded-full inline-block"></span> En línea</span>
            </div>
        </div>
        <label class="flex items-center space-x-2 text-xs font-medium text-slate-600 cursor-pointer">
            <input type="checkbox" id="voiceToggle" class="rounded text-pink-500 focus:ring-pink-400">
            <span>🔊 Voz activa</span>
        </label>
    </header>

    <!-- Contenedor Principal -->
    <main class="flex-1 max-w-5xl w-full mx-auto p-4 grid grid-cols-1 md:grid-cols-3 gap-6 overflow-hidden">
        
        <!-- Tarjeta Orgánica de Aiko -->
        <div class="hidden md:flex flex-col items-center justify-center bg-white/60 backdrop-blur-md p-6 rounded-3xl border border-white/80 shadow-xl shadow-pink-500/5">
            <img src="https://raw.githubusercontent.com/Alexcri2026/Aiko_Proyecto/main/aiko.jpg" class="w-48 h-64 rounded-2xl object-cover object-top shadow-lg shadow-pink-500/20 animate-float" alt="Aiko 2D">
            <h2 class="mt-4 font-bold text-slate-700 text-lg">Aiko 🌸</h2>
            <p class="text-xs text-slate-500">Tu compañera virtual inteligente</p>
        </div>

        <!-- Área del Chat -->
        <div class="md:col-span-2 flex flex-col justify-between bg-white/40 backdrop-blur-sm rounded-3xl border border-white/60 shadow-lg p-4 overflow-hidden">
            
            <!-- Historial de mensajes -->
            <div id="chatContainer" class="flex-1 overflow-y-auto space-y-4 pr-2">
                <div class="flex items-start space-x-2">
                    <img src="https://raw.githubusercontent.com/Alexcri2026/Aiko_Proyecto/main/aiko.jpg" class="w-8 h-8 rounded-full object-cover border border-pink-300">
                    <div class="bg-white p-4 rounded-2xl rounded-tl-none shadow-sm border border-slate-100 text-slate-700 text-sm max-w-[80%]">
                        ¡Hola Alex! 🌸 ¿De qué te gustaría hablar hoy?
                    </div>
                </div>
            </div>

            <!-- 🎯 CÁPSULA ESTILO GEMINI -->
            <div class="mt-4 bg-white border border-slate-200 rounded-full py-2 px-4 shadow-lg shadow-slate-200/50 flex items-center gap-3 transition-all focus-within:border-pink-400 focus-within:shadow-pink-500/10">
                <span class="text-slate-400 text-xl cursor-pointer hover:text-slate-600">＋</span>
                
                <input type="text" id="userInput" placeholder="Pregúntá..." class="flex-1 border-none outline-none text-slate-700 text-sm bg-transparent">

                <!-- Botón de Micrófono -->
                <button id="micBtn" class="text-slate-500 hover:text-pink-500 transition-colors p-1.5 rounded-full hover:bg-pink-50" title="Grabar audio">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"></path>
                    </svg>
                </button>

                <!-- Botón Enviar -->
                <button id="sendBtn" class="bg-gradient-to-r from-pink-400 to-pink-500 text-white w-9 h-9 rounded-full flex items-center justify-center shadow-md hover:scale-105 active:scale-95 transition-transform" title="Enviar">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M5 12h14M12 5l7 7-7 7"></path>
                    </svg>
                </button>
            </div>

        </div>
    </main>

    <script>
        const chatContainer = document.getElementById('chatContainer');
        const userInput = document.getElementById('userInput');
        const sendBtn = document.getElementById('sendBtn');
        const micBtn = document.getElementById('micBtn');
        const voiceToggle = document.getElementById('voiceToggle');
        const alarmBanner = document.getElementById('alarmBanner');
        const alarmText = document.getElementById('alarmText');

        let mediaRecorder;
        let audioChunks = [];
        let isRecording = false;

        async function sendMessage(text = null, audioFile = null) {
            const messageText = text || userInput.value.trim();
            if (!messageText && !audioFile) return;

            if (messageText) {
                chatContainer.innerHTML += `
                    <div class="flex justify-end">
                        <div class="bg-gradient-to-r from-pink-400 to-rose-400 text-white p-4 rounded-2xl rounded-tr-none shadow-md text-sm max-w-[80%]">
                            ${messageText}
                        </div>
                    </div>`;
            }
            userInput.value = '';
            chatContainer.scrollTop = chatContainer.scrollHeight;

            const formData = new FormData();
            if (messageText) formData.append('message', messageText);
            if (audioFile) formData.append('audio', audioFile);
            formData.append('voice_enabled', voiceToggle.checked);

            try {
                const response = await fetch('/api/chat', { method: 'POST', body: formData });
                const data = await response.json();

                if (data.bot_response) {
                    chatContainer.innerHTML += `
                        <div class="flex items-start space-x-2">
                            <img src="https://raw.githubusercontent.com/Alexcri2026/Aiko_Proyecto/main/aiko.jpg" class="w-8 h-8 rounded-full object-cover border border-pink-300">
                            <div class="bg-white p-4 rounded-2xl rounded-tl-none shadow-sm border border-slate-100 text-slate-700 text-sm max-w-[80%]">
                                ${data.bot_response}
                            </div>
                        </div>`;
                    chatContainer.scrollTop = chatContainer.scrollHeight;
                }
            } catch (err) {
                console.log("Error:", err);
            }
        }

        sendBtn.addEventListener('click', () => sendMessage());
        userInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });

        // Grabación de voz
        micBtn.addEventListener('click', async () => {
            if (!isRecording) {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    mediaRecorder = new MediaRecorder(stream);
                    audioChunks = [];

                    mediaRecorder.ondataavailable = event => audioChunks.push(event.data);
                    mediaRecorder.onstop = () => {
                        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                        sendMessage(null, audioBlob);
                        stream.getTracks().forEach(track => track.stop());
                    };

                    mediaRecorder.start();
                    isRecording = true;
                    micBtn.classList.add('text-red-500', 'bg-red-50', 'animate-pulse');
                    micBtn.title = "Grabando... Clic para enviar";
                } catch (e) {
                    alert("No se pudo acceder al micrófono.");
                }
            } else {
                mediaRecorder.stop();
                isRecording = false;
                micBtn.classList.remove('text-red-500', 'bg-red-50', 'animate-pulse');
                micBtn.title = "Grabar audio";
            }
        });

        // --- SISTEMA DE ALARMAS Y DETECCIÓN DE HORA ---
        function checkAlarms() {
            fetch('/api/reminders')
                .then(res => res.json())
                .then(data => {
                    const recs = data.recordatorios || [];
                    const now = new Date();
                    const currentTimeStr = String(now.getHours()).padStart(2, '0') + ":" + String(now.getMinutes()).padStart(2, '0');

                    recs.forEach(rec => {
                        // Buscar patrones de hora tipo "14:30" o "5:00 pm" en el texto de la nota
                        if (rec.includes(currentTimeStr) || rec.toLowerCase().includes(now.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', hour12: false}))) {
                            showAlarm(rec);
                        }
                    });
                }).catch(err => console.log(err));
        }

        function showAlarm(text) {
            alarmText.innerText = text;
            alarmBanner.classList.remove('translate-y-[-150%]');
            alarmBanner.classList.add('translate-y-0');
            
            // Sonido suave de alerta web
            try {
                const ctx = new (window.AudioContext || window.webkitAudioContext)();
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'sine';
                osc.frequency.setValueAtTime(587.33, ctx.currentTime); // Nota D5
                gain.gain.setValueAtTime(0.1, ctx.currentTime);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start();
                osc.stop(ctx.currentTime + 0.3);
            } catch(e) {}
        }

        function dismissAlarm() {
            alarmBanner.classList.remove('translate-y-0');
            alarmBanner.classList.add('translate-y-[-150%]');
        }

        // Revisar alarmas cada 30 segundos de forma automática
        setInterval(checkAlarms, 30000);
    </script>
</body>
</html>
    """

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
