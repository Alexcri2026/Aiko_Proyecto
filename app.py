import os
import gradio as gr
from groq import Groq

# Inicializar cliente de Groq con la variable de entorno
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
    
    try:
        # Construir el historial de mensajes
        messages = [{"role": "system", "content": AIKO_SYSTEM_INSTRUCTION}]
        
        if history:
            for user_msg, assistant_msg in history:
                if user_msg:
                    messages.append({"role": "user", "content": user_msg})
                if assistant_msg:
                    messages.append({"role": "assistant", "content": assistant_msg})
                
        messages.append({"role": "user", "content": message})

        # Llamada a la API de Groq con el modelo activo correcto
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
        )
        
        return completion.choices[0].message.content
    except Exception as e:
        return f"Ocurrió un error: {str(e)}"

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

# Configuración del puerto dinámico para Render
port = int(os.environ.get("PORT", 7860))

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=port)
