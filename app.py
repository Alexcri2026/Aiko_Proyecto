import os
import gradio as gr
from groq import Groq

# Inicializar cliente de Groq
api_key = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=api_key) if api_key else None

# Personalidad de Aiko
AIKO_SYSTEM_INSTRUCTION = (
    "Eres Aiko, una compañera virtual de anime en 2D dulce, atenta, empática y alegre. "
    "Tus respuestas deben ser expresivas, detalladas y fluidas. Demuestra curiosidad por lo que te cuenta "
    "el usuario, haz preguntas de seguimiento, comparte opiniones y exprésate con un tono cálido y afable, "
    "usando emojis kawaii de forma natural."
)

def respond(message, history):
    if not client:
        return "Error: La clave GROQ_API_KEY no está configurada en Render."

    messages = [{"role": "system", "content": AIKO_SYSTEM_INSTRUCTION}]

    # Conversión flexible del historial
    if history:
        for entry in history:
            if isinstance(entry, dict):
                messages.append({
                    "role": entry.get("role", "user"),
                    "content": str(entry.get("content", ""))
                })
            elif isinstance(entry, (list, tuple)):
                if len(entry) >= 2:
                    user_text = entry[0]
                    bot_text = entry[1]
                    if user_text:
                        messages.append({"role": "user", "content": str(user_text)})
                    if bot_text:
                        messages.append({"role": "assistant", "content": str(bot_text)})

    messages.append({"role": "user", "content": message})

    try:
        # Llamada directa al modelo principal y activo de Groq
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"Ocurrió un error con Groq: {str(e)}"

theme = gr.themes.Soft(
    primary_hue="indigo",
    secondary_hue="blue",
)

with gr.Blocks(theme=theme, title="Aiko Companion") as demo:
    gr.Markdown("# ✨ Aiko AI Companion")
    
    gr.ChatInterface(
        fn=respond
    )

port = int(os.environ.get("PORT", 7860))

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=port)
