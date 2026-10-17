import os
import gradio as gr
from google import genai
from google.genai import types
from PIL import Image

# Inicializar cliente de Gemini usando la variable de entorno de Render
api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key) if api_key else None

# Definición de la personalidad y rol de Aiko
AIKO_SYSTEM_INSTRUCTION = (
    "Eres Aiko, una compañera virtual de anime de 2D dulce, atenta, empática y alegre. "
    "Te encanta conversar con el usuario, apoyarlo en su día a día y responder con un tono cálido, "
    "usando expresividad suave y emojis kawaii ocasionales. Siempre mantienes tu papel de compañera."
)

def respond(message, history, image_input):
    if not client:
        return "Error: La clave GEMINI_API_KEY no está configurada en Render."
    
    try:
        # Configurar la personalidad en la llamada de Gemini
        config = types.GenerateContentConfig(
            system_instruction=AIKO_SYSTEM_INSTRUCTION
        )
        
        # Si el usuario adjunta una imagen en el chat
        if image_input is not None:
            img = Image.open(image_input)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[img, message if message else "Describe esta imagen"],
                config=config
            )
        else:
            # Chat de texto normal con gemini-2.5-flash
            response = client.models.generate_content(
                model = genai.GenerativeModel('gemini-3.8-flash'),
                contents=message,
                config=config
            )
        return response.text
    except Exception as e:
        return f"Ocurrió un error: {str(e)}"

# Interfaz gráfica con temas suaves en tono pastel
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

# Configuración del puerto dinámico requerida por Render
port = int(os.environ.get("PORT", 7860))

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=port)
