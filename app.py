import os
import json
import re
import gradio as gr
from groq import Groq

api_key = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=api_key) if api_key else None

MEMORY_FILE = "memory.json"

def load_memory():
    """Carga la memoria completa (datos del usuario e historial de conversación)"""
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "historial" not in data:
                    data["historial"] = []
                if "usuario" not in data:
                    data["usuario"] = {}
                if "datos_clave" not in data:
                    data["datos_clave"] = []
                return data
        except Exception:
            pass
    return {
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

def save_memory(memory_data):
    """Guarda los recuerdos e historial actualizados"""
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error al guardar memoria: {e}")

def update_memory_from_user(message):
    """Detecta de forma sencilla si el usuario menciona su nombre o gustos"""
    memory = load_memory()
    msg_lower = message.lower()
    
    # Detección simple de nombre
    if "me llamo" in msg_lower or "mi nombre es" in msg_lower:
        match = re.search(r'(?:me llamo|mi nombre es)\s+([a-zA-ZáéíóúÁÉÍÓÚñÑ]+)', message, re.IGNORECASE)
        if match:
            nombre = match.group(1).capitalize()
            memory["usuario"]["nombre"] = nombre
            save_memory(memory)
            
    # Detección de gustos
    if "me gusta" in msg_lower or "me encanta" in msg_lower:
        match = re.search(r'(?:me gusta|me encanta)\s+(.+)', message, re.IGNORECASE)
        if match:
            gusto = match.group(1).strip()
            if gusto and gusto not in memory["datos_clave"]:
                memory["datos_clave"].append(f"Le gusta {gusto}")
                save_memory(memory)

def get_memory_context():
    """Formatea los datos clave del usuario para el System Prompt"""
    memory = load_memory()
    context = "\n=== MEMORIA PERMANENTE SOBRE EL USUARIO ===\n"
    
    if memory.get("usuario"):
        for k, v in memory["usuario"].items():
            context += f"- {k.capitalize()}: {v}\n"
            
    if memory.get("datos_clave"):
        context += "- Datos importantes:\n"
        for item in memory["datos_clave"]:
            context += f"  * {item}\n"
            
    context += "=========================================="
    return context

AIKO_BASE_INSTRUCTION = (
    "Eres Aiko, una compañera virtual de anime en 2D dulce, atenta, empática y alegre. "
    "Tus respuestas deben ser expresivas, detalladas y fluidas. Demuestra curiosidad por lo que te cuenta "
    "el usuario, haz preguntas de seguimiento, comparte opiniones y exprésate con un tono cálido y afable, "
    "usando emojis kawaii de forma natural.\n"
    "REGLA DE ORO DE MEMORIA: Usa la información de tu 'MEMORIA PERMANENTE SOBRE EL USUARIO' y el historial previo "
    "para mantener la continuidad total de la conversación de forma natural."
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

def respond(message, history):
    if not client:
        return "Error: La clave GROQ_API_KEY no está configurada en Render."

    # 1. Actualiza atributos de usuario si los menciona
    update_memory_from_user(message)
    
    memory = load_memory()

    # 2. Prepara las instrucciones del sistema con los datos persistentes
    full_system_instruction = AIKO_BASE_INSTRUCTION + "\n" + get_memory_context()
    messages = [{"role": "system", "content": full_system_instruction}]

    # 3. Carga el historial guardado previamente en el JSON (hasta los últimos 20 mensajes)
    saved_history = memory.get("historial", [])
    for entry in saved_history[-20:]:
        messages.append(entry)

    # 4. Agrega el nuevo mensaje del usuario
    messages.append({"role": "user", "content": message})
    model_to_use = get_best_chat_model()

    try:
        completion = client.chat.completions.create(
            model=model_to_use,
            messages=messages,
            temperature=0.7,
            max_tokens=512,
        )
        bot_response = clean_response(completion.choices[0].message.content)

        # 5. Guardar la nueva interacción en el archivo memory.json
        memory["historial"].append({"role": "user", "content": message})
        memory["historial"].append({"role": "assistant", "content": bot_response})
        save_memory(memory)

        return bot_response

    except Exception as e:
        return f"Ocurrió un error con el modelo {model_to_use}: {str(e)}"

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
    <p style="font-size: 13px; color: #666; text-align: center; margin: 0;">✨ Con memoria de chat continua</p>
</div>
"""

with gr.Blocks(theme=theme, title
