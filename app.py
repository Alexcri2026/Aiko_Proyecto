import os
import gradio as gr
from huggingface_hub import InferenceClient

# Inicializar cliente oficial de Hugging Face
hf_token = os.environ.get("HF_TOKEN")
client = InferenceClient(token=hf_token) if hf_token else None

# Personalidad de Aiko
AIKO_SYSTEM_INSTRUCTION = (
    "Eres Aiko, una compañera virtual de anime en 2D dulce, atenta, empática y alegre. "
    "Tus respuestas deben ser expresivas, detalladas y fluidas. Demuestra curiosidad por lo que te cuenta "
    "el usuario, haz preguntas de seguimiento, comparte opiniones y exprésate con un tono cálido y afable, "
    "usando emojis kawaii de forma natural."
)

def respond(message, history):
    if not client:
        return "Error: La clave HF_TOKEN no está configurada en Render."
    
    try:
        # Estructura de mensajes para el formato Chat
        messages = [{"role": "system", "content": AIKO_SYSTEM_INSTRUCTION}]
        
        # Cargar el historial previo
        if history:
            for user_msg, assistant_msg in history:
                if user_msg:
                    messages.append({"role": "user", "content": user_msg})
                if assistant_msg:
                    messages.append({"role": "assistant", "content": assistant_msg})
                
        # Mensaje actual del usuario
        messages.append({"role": "user", "content": message})

        # Llamada al modelo gratuito Serverless Qwen 2.5 72B
        response = client.chat.completions.create(
            model="Qwen/Qwen2.5-72B-Instruct",
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )
        
        return response.choices[0].message.content

    except Exception as e:
        return f"Ocurrió un error: {str(e)}"

# Interfaz pastel de Gradio
theme = gr.themes.Soft(
    primary_hue="indigo",
    secondary_hue="blue",
)

with gr.Blocks(theme=theme, title="Aiko Companion") as demo:
    gr.Markdown("# ✨ Aiko AI Companion")
    
    chatbot = gr.ChatInterface(
        fn=respond
    )

# Puerto dinámico para Render
port = int(os.environ.get("PORT", 7860))

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=port)
