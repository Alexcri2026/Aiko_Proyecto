import os
import gradio as gr
import requests

# Clave de API de Hugging Face desde Render
hf_token = os.environ.get("HF_TOKEN")

# Personalidad y rol de Aiko
AIKO_SYSTEM_INSTRUCTION = (
    "Eres Aiko, una compañera virtual de anime en 2D dulce, atenta, empática y alegre. "
    "Tus respuestas deben ser expresivas, detalladas y fluidas. Demuestra curiosidad por lo que te cuenta "
    "el usuario, haz preguntas de seguimiento, comparte opiniones y exprésate con un tono cálido y afable, "
    "usando emojis kawaii de forma natural."
)

# Modelo gratuito alojado en Hugging Face Serverless
MODEL_URL = "https://api-inference.huggingface.co/models/HuggingFaceH4/zephyr-7b-beta"

def respond(message, history):
    if not hf_token:
        return "Error: La clave HF_TOKEN no está configurada en Render."
    
    headers = {
        "Authorization": f"Bearer {hf_token}",
        "Content-Type": "application/json"
    }

    # Formatear la conversación completa
    prompt = f"<|system|>\n{AIKO_SYSTEM_INSTRUCTION}</s>\n"
    
    if history:
        for user_msg, assistant_msg in history:
            if user_msg:
                prompt += f"<|user|>\n{user_msg}</s>\n"
            if assistant_msg:
                prompt += f"<|assistant|>\n{assistant_msg}</s>\n"
                
    prompt += f"<|user|>\n{message}</s>\n<|assistant|>\n"

    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 500,
            "temperature": 0.7,
            "top_p": 0.9,
            "return_full_text": False
        }
    }

    try:
        response = requests.post(MODEL_URL, headers=headers, json=payload, timeout=30)
        result = response.json()

        if response.status_code == 200 and isinstance(result, list) and len(result) > 0:
            return result[0].get("generated_text", "").strip()
        elif "error" in result:
            return f"Error de Hugging Face: {result['error']}"
        else:
            return "No se pudo obtener una respuesta válida en este momento."

    except Exception as e:
        return f"Ocurrió un error en la conexión: {str(e)}"

# Diseño en tono pastel
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
