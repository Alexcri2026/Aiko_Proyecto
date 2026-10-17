import os
import gradio as gr
from huggingface_hub import InferenceClient

# Inicializar cliente de Hugging Face con la variable de entorno
hf_token = os.environ.get("HF_TOKEN")
client = InferenceClient(api_key=hf_token) if hf_token else None

# Definición de la personalidad de Aiko
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
        # Construir el historial de mensajes
        messages = [{"role": "system", "content": AIKO_SYSTEM_INSTRUCTION}]
        
        # Cargar historial previo
        if history:
            for user_msg, assistant_msg in history:
                if user_msg:
                    messages.append({"role": "user", "content": user_msg})
                if assistant_msg:
                    messages.append({"role": "assistant", "content": assistant_msg})
                
        # Añadir mensaje actual
        messages.append({"role": "user", "content": message})

        # Generar respuesta usando Llama-3.2 a través de Hugging Face
        response = client.chat.completions.create(
            model="meta-llama/Llama-3.2-3B-Instruct",
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )
        
        return response.choices[0].message.content
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

# Puerto dinámico para Render
port = int(os.environ.get("PORT", 7860))

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=port)
