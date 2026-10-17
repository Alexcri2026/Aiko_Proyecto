import os
import gradio as gr
from google import genai
from google.genai import types
from PIL import Image

# Inicialización del nuevo cliente de Google GenAI
api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key) if api_key else None

# Definición de la personalidad de Aiko
AIKO_SYSTEM_INSTRUCTION = (
    "Eres Aiko, una compañera virtual de anime en 2D dulce, atenta, empática y alegre. "
    "Tus respuestas deben ser expresivas, detalladas y fluidas. Demuestra curiosidad por lo que te cuenta "
    "el usuario, haz preguntas de seguimiento, comparte opiniones y exprésate con un tono cálido y afable, "
    "usando emojis kawaii de forma natural."
)

def respond(message, history, image_input):
    if not client:
        return "Error: La clave GEMINI_API_KEY no está configurada en Render."
    
    try:
        # Configurar la personalidad y parámetros de respuesta
        config = types.GenerateContentConfig(
            system_instruction=AIKO_SYSTEM_INSTRUCTION,
            max_output_tokens=1000,
            temperature=0.7
        )
        
        # Procesamiento si el usuario incluye una imagen
        if image_input is not None:
            img = Image.open(image_input)
            prompt = message if message else "Describe esta imagen con detalle"
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=[img, prompt],
                config=config
            )
        else:
            # Procesamiento de mensaje de texto normal
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=message,
                config=config
            )
            
        return response.text
    except Exception as e:
        return f"Ocurrió un error: {str(e)}"

# Diseño pastel de la interfaz
theme = gr.themes.Soft(
    primary_hue="indigo",
    secondary_hue="blue",
)

with gr.Blocks(theme=theme, title="Aiko Companion") as demo:
    gr.Markdown("# ✨ Aiko AI Companion")
    
    with gr.Row():
        with gr.Column(scale=4):
            chatbot = gr.ChatInterface(
                fn=respond,
                additional_inputs=[
                    gr.Image(type="filepath", label="Subir imagen para Aiko")
                ]
            )

# Puerto dinámico asignado por Render
port = int(os.environ.get("PORT", 7860))

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=port)
