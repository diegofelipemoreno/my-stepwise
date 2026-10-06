import os
import json
import subprocess
import streamlit as st
from dotenv import load_dotenv
from typing import List, Dict, Any
from anthropic import Anthropic

load_dotenv()

# -------------------------------------------------------------------
# Configuración Inicial y Cliente Anthropic
# -------------------------------------------------------------------
st.set_page_config(
    page_title="Stepwise Agent - Human in the Loop",
    layout="wide",
    initial_sidebar_state="expanded"
)

API_KEY = os.environ.get("ANTHROPIC_API_KEY")
if not API_KEY:
    st.error("❌ No se encontró la variable de entorno ANTHROPIC_API_KEY.")
    st.stop()

client = Anthropic(api_key=API_KEY)
MODEL_NAME = "claude-3-5-sonnet-20241022"

# -------------------------------------------------------------------
# Definición e Implementación de Herramientas (Tools)
# -------------------------------------------------------------------
TOOLS = [
    {
        "name": "read_file",
        "description": "Lee el contenido de un archivo local.",
        "input_schema": {
            "type": "object",
            "properties": {"filepath": {"type": "string"}},
            "required": ["filepath"]
        }
    },
    {
        "name": "write_file",
        "description": "Escribe o sobrescribe un archivo local.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["filepath", "content"]
        }
    },
    {
        "name": "execute_terminal",
        "description": "Ejecuta un comando Bash en la terminal y devuelve stdout, stderr y exit code.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"]
        }
    }
]

def tool_read_file(filepath: str) -> str:
    if not os.path.exists(filepath):
        return f"ERROR: El archivo '{filepath}' no existe."
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"ERROR al leer archivo: {str(e)}"

def tool_write_file(filepath: str, content: str) -> str:
    try:
        dirname = os.path.dirname(filepath)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"OK: Archivo '{filepath}' guardado exitosamente."
    except Exception as e:
        return f"ERROR al escribir archivo: {str(e)}"

def tool_execute_terminal(command: str) -> str:
    forbidden = ["rm -rf /", "mkfs", "dd"]
    if any(cmd in command for cmd in forbidden):
        return "ERROR: Comando rechazado por seguridad."
    try:
        res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=120)
        out = f"Exit Code: {res.returncode}\n"
        if res.stdout:
            out += f"STDOUT:\n{res.stdout}\n"
        if res.stderr:
            out += f"STDERR:\n{res.stderr}\n"
        return out
    except Exception as e:
        return f"ERROR ejecutando comando: {str(e)}"

def dispatch_tool(name: str, args: Dict[str, Any]) -> str:
    if name == "read_file":
        return tool_read_file(args["filepath"])
    elif name == "write_file":
        return tool_write_file(args["filepath"], args["content"])
    elif name == "execute_terminal":
        return tool_execute_terminal(args["command"])
    return f"ERROR: Herramienta '{name}' no válida."

# -------------------------------------------------------------------
# Prompts de Sistema
# -------------------------------------------------------------------
SYSTEM_PROMPT_EXECUTION = """
Eres un agente de software autónomo y metódico que opera bajo la metodología STEPWISE.

REGLAS DE OPERACIÓN GENERALES:
1. Tu plan de trabajo aprobado está en 'task-plan.md' y los requerimientos en 'task-description.md'.
2. Ejecuta UN solo paso a la vez.
3. Aplica los cambios de código con 'write_file' y verifica inmediatamente con 'execute_terminal'.
4. Actualiza 'task-plan.md' marcando [x] únicamente cuando el paso esté validado.

REGLAS STRICTAS DE EFICIENCIA Y LECTURA (CONTENCIÓN DE TOKENS):
- RESTRICCIÓN DE ARCHIVOS EXTERNOS: Si hay un repositorio o carpeta de referencia/externa, lee ÚNICAMENTE los archivos especificados de forma explícita en 'task-description.md'.
- PROHIBIDO EXPLORAR EN MASA: Queda estrictamente prohibido usar 'execute_terminal' para ejecutar comandos de inspección masiva o recursivos (ejemplos prohibidos: 'tree', 'find', 'grep -r', 'ls -R', 'dir /s').
- LECTURA PUNTUAL: Usa 'read_file' de forma quirúrgica. No leas archivos completos de más de 500 líneas si solo necesitas entender una función específica; concéntrate únicamente en las rutas relevantes para el paso actual.
- CERO NAVEGACIÓN A CIEGAS: No intentes "adivinar" la estructura abriendo archivo por archivo. Si necesitas ubicar un archivo en el proyecto externo y no está en 'task-description.md', detente y consulta/notifica en tu respuesta.

Al finalizar TODOS los pasos con éxito, concluye con la etiqueta: [COMPLETADO].
"""

# -------------------------------------------------------------------
# Manejo del Estado de la Sesión de Streamlit
# -------------------------------------------------------------------
if "plan_proposed" not in st.session_state:
    st.session_state.plan_proposed = None
if "plan_approved" not in st.session_state:
    st.session_state.plan_approved = False
if "execution_logs" not in st.session_state:
    st.session_state.execution_logs = []
if "messages" not in st.session_state:
    st.session_state.messages = []
if "is_finished" not in st.session_state:
    st.session_state.is_finished = False

# -------------------------------------------------------------------
# Interfaz Gráfica (UI)
# -------------------------------------------------------------------
st.title("🛡️ Stepwise Agent (Visual & Interactive)")
st.caption("Fase 1: Propuesta y Validación Humana ➔ Fase 2: Ejecución Atómica con Herramientas")

# Cargar Requerimiento
if not os.path.exists("task-description.md"):
    st.error("❌ No se encontró el archivo `task-description.md` en la raíz del proyecto.")
    st.stop()

with open("task-description.md", "r", encoding="utf-8") as f:
    task_desc = f.read()

col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("📄 Requerimientos (`task-description.md`)")
    st.markdown(task_desc)

with col_right:
    st.subheader("🎯 Plan de Ejecución (Approach)")

    # ---------------------------------------------------------------
    # FASE 1: Propuesta y Aprobación Humana
    # ---------------------------------------------------------------
    if not st.session_state.plan_approved:
        
        def generate_plan(feedback=None):
            prompt = f"Lee esta descripción de tarea y propone un plan paso a paso detallado (con casillas [ ]) para resolverla:\n\n{task_desc}"
            if feedback:
                prompt += f"\n\nEl usuario revisó tu propuesta previa y solicita los siguientes ajustes/correcciones:\n'{feedback}'\nAjusta el plan según esta observación."
            res = client.messages.create(
                model=MODEL_NAME,
                max_tokens=2500,
                messages=[{"role": "user", "content": prompt}]
            )
            return res.content[0].text

        if st.session_state.plan_proposed is None:
            if st.button("🔍 Analizar y Proponer Approach", type="primary"):
                with st.spinner("La IA está generando la propuesta..."):
                    st.session_state.plan_proposed = generate_plan()
                    st.rerun()
        else:
            st.markdown(st.session_state.plan_proposed)
            st.divider()
            
            st.write("💬 **¿Es correcto el approach o detectas alguna alucinación?**")
            user_feedback = st.text_area(
                "Feedback para la IA:",
                placeholder="Ejemplo: No uses Axios, usa la API nativa fetch. El archivo index.js debe estar en src/ y no en la raíz."
            )
            
            btn_col1, btn_col2 = st.columns(2)
            
            with btn_col1:
                if st.button("✅ Aprobar e Iniciar Agente", type="primary"):
                    st.session_state.plan_approved = True
                    # Guardar el plan aprobado en el disco
                    with open("task-plan.md", "w", encoding="utf-8") as f:
                        f.write(st.session_state.plan_proposed)
                    
                    # Inicializar conversación para la Fase de Ejecución
                    st.session_state.messages = [{
                        "role": "user",
                        "content": "El plan en 'task-plan.md' fue APROBADO. Comienza la ejecución paso a paso usando tus herramientas de archivos y terminal."
                    }]
                    st.rerun()

            with btn_col2:
                if st.button("🔄 Regenerar con Feedback"):
                    if user_feedback.strip():
                        with st.spinner("Reajustando plan según tus observaciones..."):
                            st.session_state.plan_proposed = generate_plan(user_feedback)
                            st.rerun()
                    else:
                        st.warning("Escribe una observación antes de solicitar ajustes.")

    # ---------------------------------------------------------------
    # FASE 2: Bucle de Ejecución Autónoma
    # ---------------------------------------------------------------
    else:
        st.success("🟢 Approach Aprobado. El agente está listo para trabajar.")
        
        # Botón para disparar iteraciones
        if not st.session_state.is_finished:
            if st.button("▶️ Ejecutar Siguiente Paso / Iteración", type="primary"):
                with st.spinner("Ejecutando cambios y validando en la terminal..."):
                    
                    response = client.messages.create(
                        model=MODEL_NAME,
                        max_tokens=4000,
                        system=SYSTEM_PROMPT_EXECUTION,
                        tools=TOOLS,
                        messages=st.session_state.messages
                    )
                    
                    st.session_state.messages.append({"role": "assistant", "content": response.content})
                    has_tools = False
                    tool_results = []

                    for block in response.content:
                        if block.type == "text":
                            st.session_state.execution_logs.append(f"🤖 **IA:** {block.text}")
                            if "[COMPLETADO]" in block.text:
                                st.session_state.is_finished = True

                        elif block.type == "tool_use":
                            has_tools = True
                            tool_name = block.name
                            tool_args = block.input
                            
                            # Log visual de la llamada
                            st.session_state.execution_logs.append(
                                f"🛠️ **Tool Call:** `{tool_name}`\n```json\n{json.dumps(tool_args, indent=2)}\n```"
                            )
                            
                            # Ejecución real
                            output = dispatch_tool(tool_name, tool_args)
                            
                            # Log visual de la salida
                            st.session_state.execution_logs.append(
                                f"📥 **Tool Output:**\n```text\n{output}\n```"
                            )
                            
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": output
                            })

                    if has_tools:
                        st.session_state.messages.append({"role": "user", "content": tool_results})
                    else:
                        st.session_state.messages.append({"role": "user", "content": "Continúa con el siguiente paso pendiente de 'task-plan.md'."})
                    
                    st.rerun()

        if st.session_state.is_finished:
            st.balloons()
            st.success("🎉 ¡La tarea ha sido completada y verificada exitosamente!")

# -------------------------------------------------------------------
# Panel Inferior: Consola en vivo y Visor de Estado
# -------------------------------------------------------------------
st.divider()
st.subheader("🖥️ Logs de Ejecución en Vivo & Archivos")

tab_logs, tab_plan = st.tabs(["📋 Consola de la IA", "📝 Plan Actualizado (`task-plan.md`)"])

with tab_logs:
    for log in st.session_state.execution_logs:
        st.markdown(log)

with tab_plan:
    if os.path.exists("task-plan.md"):
        with open("task-plan.md", "r", encoding="utf-8") as f:
            st.markdown(f.read())