import os
import gradio as gr
from groq import Groq

# Inicializar cliente de Groq con la variable de entorno de Render
api_key = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=api_key) if api_key else None

# Definición de la personalidad y rol de Aiko
AIKO_SYSTEM_INSTRUCTION = (
    "Eres Aiko, una compañera virtual de anime en 2D dulce, atenta, empática y alegre. "
    "Tus respuestas deben ser expresivas, detalladas y fluidas. Demuestra curiosidad por lo que te cuenta "
    "el usuario, haz preguntas de seguimiento, comparte opiniones y exprésate con un tono cálido y afable, "
    "usando emojis kawaii de forma natural."
)

def respond(message, history):
    if not client:
        return "Error: La clave GROQ_API_KEY no está configurada en Render."
    
    # Modelos principales y alternativos en Groq
    models_to_try = [
        "llama3-8b-8192",
        "llama-3.3-70b-specdec",
        "mixtral-8x7b-32768"
    ]
    
    # Construir el historial de mensajes para Groq
    messages = [{"role": "system", "content": AIKO_SYSTEM_INSTRUCTION}]
    
    if history:
        for user_msg, assistant_msg in history:
            if user_msg:
                messages.append({"role": "user", "content": user_msg})
            if assistant_msg:
                messages.append({"role": "assistant", "content": assistant_msg})
            
    messages.append({"role": "user", "content": message})

    # Intentar llamadas a los modelos soportados
    last_error = ""
    for model in models_to_try:
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
            )
            return completion.choices[0].message.content
        except Exception as e:
            last_error = str(e)
            continue

    return f"Ocurrió un error con los modelos de Groq: {last_error}"

# Interfaz gráfica en tono pastel
theme = gr.themes.Soft(
    primary_hue="indigo",
    secondary_hue="blue",
)

with gr.Blocks(theme=theme, title="Aiko Companion") as demo:
    gr.Markdown("# ✨ Aiko AI Companion")
    
    chatbot = gr.ChatInterface(
        fn=respond
    )

# Configuración del puerto dinámico requerida por Render
port = int(os.environ.get("PORT", 7860))

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=port)
