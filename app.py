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

def get_best_available_model():
    """Busca dinámicamente un modelo de chat válido en Groq, excluyendo audio, seguridad y embeddings"""
    if not client:
        return "llama-3.3-70b-versatile"
    try:
        models_response = client.models.list()
        
        chat_models = []
        for m in models_response.data:
            mid = m.id.lower()
            # Excluir modelos que no sean de chat de texto
            if any(term in mid for term in ["guard", "embed", "whisper", "tts", "audio", "vision-preview"]):
                continue
            chat_models.append(m.id)
        
        # Priorizar modelos de chat oficiales de Llama
        for preferred in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama3-70b-8192", "llama3-8b-8192"]:
            if preferred in chat_models:
                return preferred
                
        # Si hay otro modelo de texto disponible, tomar el primero
        if chat_models:
            return chat_models[0]
    except Exception:
        pass
    
    return "llama-3.3-70b-versatile"

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

    # Obtener un modelo de chat estrictamente de texto
    model_to_use = get_best_available_model()

    try:
        completion = client.chat.completions.create(
            model=model_to_use,
            messages=messages,
            temperature=0.7,
            max_tokens=512,
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"Ocurrió un error con el modelo {model_to_use}: {str(e)}"

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
