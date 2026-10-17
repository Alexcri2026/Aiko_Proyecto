!pip install -q gradio

import gradio as gr
from google import genai
from google.genai import types
from datetime import datetime
from PIL import Image

# Tu API Key
api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

# Personalidad de Aiko
instrucciones_personaje = """
Eres Aiko, una chica anime alegre, curiosa y llena de energía.
Hablas de forma entusiasta, usas expresiones amigables y siempre buscas animar al usuario.
Si el usuario te envía una imagen, analízala con atención, comenta qué ves de forma simpática y responde a lo que te pregunte sobre ella.
Tus respuestas deben ser cortas (máximo 3 oraciones).
"""

chat_ia = client.chats.create(
    model="gemini-3.8-flash",
    config=types.GenerateContentConfig(
        system_instruction=instrucciones_personaje,
        temperature=0.7,
    )
)

# Lista en memoria para guardar las imágenes que el usuario suba a la Galería
galeria_imagenes = []

def responder_aiko(mensaje_usuario, historial):
    try:
        ahora = datetime.now()
        fecha_hora_actual = ahora.strftime("%A, %d de %B de %Y - %H:%M")

        texto_prompt = mensaje_usuario.get("text", "")
        archivos = mensaje_usuario.get("files", [])

        contenido_para_gemini = []

        if archivos:
            ruta_imagen = archivos[0]
            imagen_pil = Image.open(ruta_imagen)
            contenido_para_gemini.append(imagen_pil)

            # Guardamos la imagen en nuestra galería interactiva
            if ruta_imagen not in galeria_imagenes:
                galeria_imagenes.append(ruta_imagen)

        prompt_completo = f"[Contexto de tiempo actual: {fecha_hora_actual}]\n\n{texto_prompt}"
        contenido_para_gemini.append(prompt_completo)

        respuesta = chat_ia.send_message(contenido_para_gemini)
        return respuesta.text

    except Exception as e:
        return f"Ups, ocurrió un error: {e}"

# Función para actualizar la Galería en pantalla
def cargar_galeria():
    return galeria_imagenes

# CSS Avanzado para eliminar TODO fondo negro y personalizar la entrada de texto
custom_css = """
/* Fondo general de la aplicación */
.gradio-container, body {
    background: linear-gradient(135deg, #E3F2FD 0%, #EDE7F6 100%) !important;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    min-height: 100vh;
}

/* Forzar temas claros e eliminar sombras negras predeterminadas de Gradio */
*, .dark, .dark * {
    background-color: transparent !important;
    color: #2C3E50 !important;
}

/* Panel del personaje */
.character-panel {
    background: rgba(255, 255, 255, 0.85) !important;
    border-radius: 20px !important;
    padding: 20px !important;
    box-shadow: 0 8px 20px rgba(92, 107, 192, 0.12) !important;
    border: 1px solid #C5CAE9 !important;
}

/* Cajas de texto y entrada de chat integradas al fondo claro */
textarea, input[type="text"], .form, fieldset {
    background-color: #FFFFFF !important;
    color: #333333 !important;
    border: 1.5px solid #C5CAE9 !important;
    border-radius: 16px !important;
    box-shadow: none !important;
}

textarea:focus, input[type="text"]:focus {
    border-color: #5C6BC0 !important;
}

/* Botón del menú lateral */
.menu-btn {
    background-color: #FFFFFF !important;
    color: #3F51B5 !important;
    border-radius: 12px !important;
    border: 1px solid #C5CAE9 !important;
    font-weight: bold;
}

footer {display: none !important;}
"""

with gr.Blocks(css=custom_css) as demo:

    # Barra Superior
    with gr.Row():
        menu_btn = gr.Button("☰ Menú", elem_classes="menu-btn", scale=0, min_width=100)
        gr.Markdown("<h2 style='color: #3F51B5; margin: auto 0; text-align: left;'>✨ Aiko Companion ✨</h2>", scale=10)

    # Menú Lateral Desplegable (Sidebar)
    with gr.Sidebar(visible=False) as sidebar:
        gr.Markdown("### ⚙️ **Opciones y Biblioteca**")
        with gr.Tabs():
            with gr.TabItem("📜 Historial"):
                gr.Markdown("*Tus conversaciones recientes se organizarán aquí.*")
                gr.Radio(["Conversación Actual"], label="Sesiones", value="Conversación Actual")

            with gr.TabItem("🖼️ Galería"):
                gr.Markdown("*Imágenes analizadas y guardadas:*")
                btn_refrescar = gr.Button("🔄 Actualizar Galería", size="sm")
                galeria_display = gr.Gallery(label="Mis Fotos", columns=2, height=300)
                btn_refrescar.click(cargar_galeria, outputs=galeria_display)

    # Conectar el botón ☰ para mostrar u ocultar el menú lateral
    def alternar_sidebar(estado_actual):
        return not estado_actual

    menu_btn.click(alternar_sidebar, inputs=sidebar, outputs=sidebar)

    # Cuerpo principal de la pantalla de navegador
    with gr.Row():

        # Columna Izquierda: Aiko y Burbuja de Diálogo
        with gr.Column(scale=1, elem_classes="character-panel"):
            gr.Markdown(
                """
                <div style='background-color: #ffffff; padding: 12px 18px; border-radius: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); text-align: center; margin-bottom: 15px; border: 2px solid #C5CAE9;'>
                    <span style='font-size: 15px; color: #3F51B5; font-weight: bold;'>💬 ¡Hola! Haz clic en ☰ Menú para ver tu galería. ✨</span>
                </div>
                """
            )
            gr.Image(
                value="1001439943.jpg",
                label="",
                interactive=False,
                height=380,
                show_label=False,
                container=False
            )

        # Columna Derecha: Chat Multimodal completamente claro y suave
        with gr.Column(scale=2):
            gr.ChatInterface(
                fn=responder_aiko,
                multimodal=True,
                submit_btn="Enviar 💌"
            )

demo.launch(inline=True, share=False)
