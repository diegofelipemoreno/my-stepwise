import os
import json
import subprocess
import streamlit as st
from typing import List, Dict, Any
import boto3
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# -------------------------------------------------------------------
# Configuración Inicial y Cliente AWS Bedrock
# -------------------------------------------------------------------
st.set_page_config(
    page_title="Stepwise Agent (AWS Bedrock)",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Carpeta de Contextos Persistentes
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTEXTS_DIR = os.path.join(BASE_DIR, "contexts")
os.makedirs(CONTEXTS_DIR, exist_ok=True)

AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

try:
    bedrock = boto3.client(
        service_name="bedrock-runtime",
        region_name=AWS_REGION,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
    )
except Exception as e:
    st.error(f"❌ Error al inicializar cliente de AWS Bedrock: {str(e)}")
    st.stop()

MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-opus-4-5-20251101-v1:0")

# -------------------------------------------------------------------
# Helper: Gestión Dinámica y Agnóstica de Proyectos
# -------------------------------------------------------------------
def discover_projects() -> List[str]:
    """Escanea contexts/ y devuelve la lista de nombres de proyectos encontrados."""
    if not os.path.exists(CONTEXTS_DIR):
        return []
    
    projects = set()
    for file in os.listdir(CONTEXTS_DIR):
        if file.endswith(".md"):
            clean_name = file.replace("-memory.md", "").replace(".md", "").strip()
            if clean_name:
                projects.add(clean_name)
    
    return sorted(list(projects))

def get_current_repo_name() -> str:
    """Obtiene el proyecto activo sin asumir ningún nombre fijo."""
    return st.session_state.get("repo_name", "")

def get_project_file_paths(repo_id: str) -> tuple[str, str]:
    """Genera las rutas dinámicas de contexto y memoria para cualquier ID de proyecto."""
    if not repo_id:
        return "", ""
    safe_repo_id = "".join([c if c.isalnum() or c in ("-", "_") else "_" for c in repo_id])
    context_filepath = os.path.join(CONTEXTS_DIR, f"{safe_repo_id}.md")
    memory_filepath = os.path.join(CONTEXTS_DIR, f"{safe_repo_id}-memory.md")
    return context_filepath, memory_filepath

# -------------------------------------------------------------------
# Definición e Implementación de Herramientas (Tools)
# -------------------------------------------------------------------
BEDROCK_TOOLS = [
    {
        "toolSpec": {
            "name": "read_file",
            "description": "Lee el contenido de un archivo local.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {"filepath": {"type": "string"}},
                    "required": ["filepath"]
                }
            }
        }
    },
    {
        "toolSpec": {
            "name": "write_file",
            "description": "Escribe o sobrescribe un archivo local.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "filepath": {"type": "string"},
                        "content": {"type": "string"}
                    },
                    "required": ["filepath", "content"]
                }
            }
        }
    },
    {
        "toolSpec": {
            "name": "execute_terminal",
            "description": "Ejecuta un comando Bash en la terminal y devuelve stdout, stderr y exit code.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"]
                }
            }
        }
    },
    {
        "toolSpec": {
            "name": "save_repo_context",
            "description": "Guarda o actualiza el documento de análisis del proyecto activo en su memoria persistente (-memory.md).",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "analysis_markdown": {
                            "type": "string",
                            "description": "Resumen técnico detallado, arquitectura, hallazgos y convenciones del proyecto."
                        }
                    },
                    "required": ["analysis_markdown"]
                }
            }
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

def tool_save_repo_context(analysis_markdown: str) -> str:
    repo_name = get_current_repo_name()
    if not repo_name:
        return "ERROR: No hay un proyecto seleccionado para guardar la memoria."
    
    _, memory_filepath = get_project_file_paths(repo_name)
    res = tool_write_file(memory_filepath, analysis_markdown)
    if "OK:" in res:
        return f"OK: Memoria persistente guardada en '{memory_filepath}'."
    return res

def dispatch_tool(name: str, args: Dict[str, Any]) -> str:
    if name == "read_file":
        return tool_read_file(args["filepath"])
    elif name == "write_file":
        return tool_write_file(args["filepath"], args["content"])
    elif name == "execute_terminal":
        return tool_execute_terminal(args["command"])
    elif name == "save_repo_context":
        return tool_save_repo_context(args["analysis_markdown"])
    return f"ERROR: Herramienta '{name}' no válida."

# -------------------------------------------------------------------
# Construcción Dinámica de Prompts de Sistema
# -------------------------------------------------------------------
def get_system_prompt_execution() -> str:
    repo_id = get_current_repo_name()
    context_filepath, memory_filepath = get_project_file_paths(repo_id)
    
    context_str = ""
    if context_filepath and os.path.exists(context_filepath):
        with open(context_filepath, "r", encoding="utf-8") as f:
            context_str += f"\n\n--- CONTEXTO GENERAL DEL PROYECTO ({repo_id}) ---\n" + f.read()

    memory_str = ""
    if memory_filepath and os.path.exists(memory_filepath):
        with open(memory_filepath, "r", encoding="utf-8") as f:
            memory_str += f"\n\n--- MEMORIA PERSISTENTE DEL REPOSITORIO ({repo_id}-memory.md) ---\n" + f.read()

    return f"""
Eres un agente de software autónomo y metódico que opera bajo la metodología STEPWISE.

REGLAS DE OPERACIÓN GENERALES:
1. Tu plan de trabajo aprobado está en 'task-plan.md' y los requerimientos en 'task-description.md'.
2. Ejecuta UN solo paso a la vez.
3. Aplica los cambios de código con 'write_file' y verifica inmediatamente con 'execute_terminal'.
4. Actualiza 'task-plan.md' marcando [x] únicamente cuando el paso esté validado.
5. MEMORIA PERSISTENTE: Tienes a tu disposición el análisis previo y la memoria del proyecto activo ({repo_id if repo_id else 'General'}). Consulta la memoria antes de analizar desde cero. Para actualizar aprendizajes, invoca la herramienta 'save_repo_context'.

REGLAS ESTRITAS DE EFICIENCIA Y LECTURA:
- Lectura puntual mediante 'read_file'. Prohibida la navegación recursiva a ciegas en la terminal.

Al finalizar TODOS los pasos con éxito, guarda el contexto actualizado si aplica y concluye con la etiqueta: [COMPLETADO].
{context_str}
{memory_str}
"""

# -------------------------------------------------------------------
# Inicialización del Estado de Sesión
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
st.title("☁️ Stepwise Agent (AWS Bedrock + Dynamic Memory)")
st.caption("Arquitectura Multi-Proyecto Autónoma con Memoria Persistente Desacoplada")

# -------------------------------------------------------------------
# Barra Lateral: Gestor de Proyectos & Memoria
# -------------------------------------------------------------------
with st.sidebar:
    st.header("🧠 Gestor de Proyectos & Memoria")
    
    available_projects = discover_projects()

    # 1. Selector de Proyectos Existentes
    if available_projects:
        # Asegurar que el estado inicial exista
        if "repo_name" not in st.session_state or st.session_state.repo_name not in available_projects:
            st.session_state.repo_name = available_projects[0]

        selected_proj = st.selectbox(
            "Seleccionar proyecto existente:",
            options=available_projects,
            index=available_projects.index(st.session_state.repo_name),
            key="sb_project_select"
        )
        
        # Si cambia el selectbox, actualizar el proyecto activo
        if selected_proj != st.session_state.repo_name:
            st.session_state.repo_name = selected_proj
            st.rerun()
    else:
        st.info("No hay proyectos previos en `contexts/`.")

    st.divider()

    # 2. Formulario para Crear / Cargar Nuevo Proyecto
    st.subheader("➕ Nuevo Proyecto")
    with st.form(key="new_project_form"):
        new_proj_input = st.text_input(
            "Nombre del nuevo proyecto:",
            placeholder="ej. app-carrito-compras",
            help="Escribe el nombre y presiona 'Cargar / Crear'"
        )
        submit_btn = st.form_submit_button("🚀 Cargar / Crear Proyecto", use_container_width=True)

    if submit_btn and new_proj_input.strip():
        clean_new_proj = new_proj_input.strip().lower().replace(" ", "-")
        ctx_path, mem_path = get_project_file_paths(clean_new_proj)

        # Crear archivos base si no existen aún
        if not os.path.exists(ctx_path):
            tool_write_file(ctx_path, f"# Contexto: {clean_new_proj}\n\nEspecificaciones del proyecto.")
        if not os.path.exists(mem_path):
            tool_write_file(mem_path, f"# Persistent Memory - {clean_new_proj}\n\n## Data Recopilada\n- Contexto inicial creado.")

        st.session_state.repo_name = clean_new_proj
        st.toast(f"✅ Proyecto '{clean_new_proj}' activado correctamente.")
        st.rerun()

    st.divider()

    # 3. Visualización y Edición de la Memoria del Proyecto Activo
    current_repo = get_current_repo_name()
    if current_repo:
        st.markdown(f"📌 **Proyecto Activo:** `{current_repo}`")
        context_filepath, memory_filepath = get_project_file_paths(current_repo)

        if os.path.exists(memory_filepath):
            st.success(f"✅ Memoria cargada:\n`{os.path.basename(memory_filepath)}`")
            with st.expander("📄 Ver / Editar Memoria Recopilada", expanded=True):
                with open(memory_filepath, "r", encoding="utf-8") as f:
                    memory_data = f.read()
                
                # FIX: Claves dinámicas asociadas al proyecto activo
                dynamic_key = f"txt_memory_editor_{current_repo}"
                edited_memory = st.text_area("Contenido:", value=memory_data, height=200, key=dynamic_key)
                if st.button("💾 Guardar Cambios en Memoria", key=f"btn_save_mem_{current_repo}"):
                    tool_write_file(memory_filepath, edited_memory)
                    st.toast("Memoria actualizada exitosamente.")
                    st.rerun()
        else:
            st.warning(f"⚠️ No existe memoria para `{current_repo}`")
            if st.button("➕ Crear Archivo de Memoria", key=f"btn_create_mem_{current_repo}"):
                default_mem = f"# Persistent Memory - {current_repo}\n\n## Contexto Inicial\n- Memoria creada manualmente."
                tool_write_file(memory_filepath, default_mem)
                st.toast("Archivo de memoria creado.")
                st.rerun()


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

    # FASE 1: Propuesta y Aprobación
    if not st.session_state.plan_approved:
        
        def generate_plan(feedback=None):
            repo_id = get_current_repo_name()
            _, memory_filepath = get_project_file_paths(repo_id)
            memory_prompt = ""
            if memory_filepath and os.path.exists(memory_filepath):
                with open(memory_filepath, "r", encoding="utf-8") as f:
                    memory_prompt = f"\n\nUsa la MEMORIA PERSISTENTE de {repo_id} como base para tu plan:\n{f.read()}"

            prompt = f"Lee esta descripción de tarea y propone un plan paso a paso detallado (con casillas [ ]) para resolverla:\n\n{task_desc}{memory_prompt}"
            if feedback:
                prompt += f"\n\nAjusta el plan según esta observación del usuario:\n'{feedback}'"
            
            response = bedrock.converse(
                modelId=MODEL_ID,
                messages=[{"role": "user", "content": [{"text": prompt}]}]
            )
            return response["output"]["message"]["content"][0]["text"]

        if st.session_state.plan_proposed is None:
            if st.button("🔍 Analizar y Proponer Approach", type="primary"):
                with st.spinner("Conectando con AWS Bedrock y leyendo memoria del proyecto..."):
                    st.session_state.plan_proposed = generate_plan()
                    st.rerun()
        else:
            st.markdown(st.session_state.plan_proposed)
            st.divider()
            
            user_feedback = st.text_area(
                "Feedback para ajustar la propuesta:",
                placeholder="Ejemplo: No modifiques el módulo X según la memoria."
            )
            
            btn_col1, btn_col2 = st.columns(2)
            
            with btn_col1:
                if st.button("✅ Aprobar e Iniciar Agente", type="primary"):
                    st.session_state.plan_approved = True
                    with open("task-plan.md", "w", encoding="utf-8") as f:
                        f.write(st.session_state.plan_proposed)
                    
                    st.session_state.messages = [{
                        "role": "user",
                        "content": [{"text": "El plan en 'task-plan.md' fue APROBADO. Inicia la ejecución apoyándote en la memoria."}]
                    }]
                    st.rerun()

            with btn_col2:
                if st.button("🔄 Regenerar con Feedback"):
                    if user_feedback.strip():
                        with st.spinner("Reajustando propuesta..."):
                            st.session_state.plan_proposed = generate_plan(user_feedback)
                            st.rerun()
                    else:
                        st.warning("Escribe una observación antes de regenerar.")

    # FASE 2: Bucle de Ejecución
    else:
        st.success(f"🟢 Ejecutando sobre el proyecto: `{get_current_repo_name() or 'Sin Nombre'}`")
        
        with st.expander("🛠️ Editar Plan en Caliente", expanded=False):
            current_plan = ""
            if os.path.exists("task-plan.md"):
                with open("task-plan.md", "r", encoding="utf-8") as f:
                    current_plan = f.read()

            edited_plan = st.text_area("Editar `task-plan.md`:", value=current_plan, height=200)
            if st.button("💾 Guardar Cambios"):
                with open("task-plan.md", "w", encoding="utf-8") as f:
                    f.write(edited_plan)
                st.success("Plan actualizado.")
                st.rerun()

        st.divider()

        if not st.session_state.is_finished:
            if st.button("▶️ Ejecutar Siguiente Paso", type="primary"):
                with st.spinner("Ejecutando y validando..."):
                    response = bedrock.converse(
                        modelId=MODEL_ID,
                        messages=st.session_state.messages,
                        system=[{"text": get_system_prompt_execution()}],
                        toolConfig={"tools": BEDROCK_TOOLS}
                    )
                    
                    output_message = response["output"]["message"]
                    st.session_state.messages.append(output_message)
                    
                    has_tools = False
                    tool_results_blocks = []

                    for content_block in output_message["content"]:
                        if "text" in content_block:
                            text_content = content_block["text"]
                            st.session_state.execution_logs.append(f"🤖 **IA:** {text_content}")
                            if "[COMPLETADO]" in text_content:
                                st.session_state.is_finished = True

                        elif "toolUse" in content_block:
                            has_tools = True
                            tool_use = content_block["toolUse"]
                            tool_use_id = tool_use["toolUseId"]
                            tool_name = tool_use["name"]
                            tool_args = tool_use["input"]
                            
                            st.session_state.execution_logs.append(
                                f"🛠️ **Tool Call:** `{tool_name}`\n```json\n{json.dumps(tool_args, indent=2)}\n```"
                            )
                            
                            output_str = dispatch_tool(tool_name, tool_args)
                            
                            st.session_state.execution_logs.append(
                                f"📥 **Tool Output:**\n```text\n{output_str}\n```"
                            )
                            
                            tool_results_blocks.append({
                                "toolResult": {
                                    "toolUseId": tool_use_id,
                                    "content": [{"text": output_str}]
                                }
                            })

                    if has_tools:
                        st.session_state.messages.append({
                            "role": "user",
                            "content": tool_results_blocks
                        })
                    else:
                        st.session_state.messages.append({
                            "role": "user",
                            "content": [{"text": "Continúa con el siguiente paso pendiente de 'task-plan.md'."}]
                        })
                    
                    st.rerun()

        if st.session_state.is_finished:
            st.balloons()
            st.success("🎉 Tarea completada y memoria persistente actualizada.")

# -------------------------------------------------------------------
# Panel Inferior: Consola y Memoria
# -------------------------------------------------------------------
st.divider()
st.subheader("🖥️ Logs de Ejecución & Memoria")

tab_logs, tab_plan, tab_memory = st.tabs([
    "📋 Consola de la IA", 
    "📝 Plan Actualizado (`task-plan.md`)",
    f"🧠 Memoria Recopilada ({get_current_repo_name() or 'Sin Proyecto'}-memory.md)"
])

with tab_logs:
    for log in st.session_state.execution_logs:
        st.markdown(log)

with tab_plan:
    if os.path.exists("task-plan.md"):
        with open("task-plan.md", "r", encoding="utf-8") as f:
            st.markdown(f.read())

with tab_memory:
    repo_name = get_current_repo_name()
    if repo_name:
        _, current_mem_file = get_project_file_paths(repo_name)
        if current_mem_file and os.path.exists(current_mem_file):
            with open(current_mem_file, "r", encoding="utf-8") as f:
                st.markdown(f.read())
        else:
            st.info(f"No hay archivo de memoria para `{repo_name}`.")
    else:
        st.info("Selecciona o ingresa un proyecto para ver su memoria.")