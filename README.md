# 🛡️ Stepwise Agent

**Human-in-the-Loop AI Software Agent with Persistent Memory**

A visual, interactive AI coding agent built with Streamlit that executes tasks step-by-step with human validation. Supports both Anthropic API and AWS Bedrock as LLM backends.

---

## 📑 Table of Contents

- [Features](#-features)
- [Architecture](#-architecture)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Usage](#-usage)
- [Project Structure](#-project-structure)
- [How It Works](#-how-it-works)
- [Available Tools](#-available-tools)
- [License](#-license)

---

## ✨ Features

- **Human-in-the-Loop Workflow**: Every execution plan requires human approval before the agent proceeds
- **Step-by-Step Execution**: Atomic task execution with real-time validation
- **Dual Backend Support**: 
  - `app.py` — Anthropic Claude API (Direct)
  - `app_bedrock.py` — AWS Bedrock (Claude models)
- **Persistent Memory System**: Project-specific memory files that persist across sessions
- **Multi-Project Management**: Dynamic project switching with isolated contexts
- **Real-Time Execution Logs**: Visual console showing all tool calls and outputs
- **Live Plan Editing**: Modify the execution plan on-the-fly during agent runtime
- **Security Guards**: Forbidden command detection to prevent destructive operations

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit Web UI                         │
├─────────────────────────────────────────────────────────────┤
│  Phase 1: Planning          │  Phase 2: Execution           │
│  ┌─────────────────────┐    │  ┌─────────────────────────┐  │
│  │ task-description.md │────┼─▶│ Approved task-plan.md   │  │
│  │ (Requirements)      │    │  │ (Step-by-step checklist)│  │
│  └─────────────────────┘    │  └───────────┬─────────────┘  │
│            │                │              │                │
│            ▼                │              ▼                │
│  ┌─────────────────────┐    │  ┌─────────────────────────┐  │
│  │   LLM Proposal      │    │  │   Tool Dispatch Loop    │  │
│  │   + Human Review    │    │  │   (read/write/execute)  │  │
│  └─────────────────────┘    │  └─────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                  Persistent Memory Layer                    │
│         contexts/{project}.md + {project}-memory.md         │
└─────────────────────────────────────────────────────────────┘
```

---

## 📋 Prerequisites

- **Python**: 3.10+
- **API Access** (one of the following):
  - Anthropic API Key
  - AWS Account with Bedrock access (Claude models enabled)

---

## 🚀 Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd my-stepwise
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install streamlit anthropic boto3 python-dotenv
   ```

---

## ⚙️ Configuration

Create a `.env` file in the root directory:

### For Anthropic API (`app.py`)
```env
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxx
```
---

## 🎮 Usage

### Start the Agent

**Using Anthropic API:**
```bash
streamlit run app.py
```

**Using AWS Bedrock:**
```bash
streamlit run app_bedrock.py
```

### Workflow

1. **Create a Task Description**  
   Write your requirements in `task-description.md`:
   ```markdown
   # Task: Build a REST API
   
   ## Requirements
   - Create Express.js server
   - Add CRUD endpoints for /users
   - Include input validation
   ```

2. **Generate & Approve Plan**  
   Click "🔍 Analizar y Proponer Approach" to generate a step-by-step plan. Review it, provide feedback if needed, then approve.

3. **Execute Steps**  
   Click "▶️ Ejecutar Siguiente Paso" to run each step. The agent will:
   - Read/write files as needed
   - Execute terminal commands
   - Update the plan with `[x]` checkmarks
   - Report completion with `[COMPLETADO]`

---

## 📁 Project Structure

```
my-stepwise/
├── app.py                    # Main agent (Anthropic API)
├── app_bedrock.py            # Main agent (AWS Bedrock)
├── task-description.md       # Your task requirements (gitignored)
├── task-plan.md              # Generated execution plan (gitignored)
├── contexts/                 # Persistent memory storage
│   ├── {project}.md          # Project-specific context/rules
│   └── {project}-memory.md   # Accumulated learnings & analysis
├── .env                      # API credentials (gitignored)
├── .gitignore
└── notes.txt                 # Quick reference commands
```

---

## ⚙️ How It Works

### Phase 1: Planning
1. Agent reads `task-description.md`
2. Loads persistent memory for the active project
3. Proposes a detailed step-by-step plan with checkboxes
4. Human reviews, provides feedback, or approves

### Phase 2: Execution
1. Agent reads `task-plan.md` and identifies the next pending step
2. Executes ONE step at a time using available tools
3. Validates the result (e.g., runs tests, checks file creation)
4. Marks the step as `[x]` complete in the plan
5. Repeats until all steps are done → outputs `[COMPLETADO]`

### Memory System (Bedrock version)
- **Context File** (`{project}.md`): Static rules and project specifications
- **Memory File** (`{project}-memory.md`): Dynamic learnings, architecture notes, and discoveries accumulated by the agent

---

## 🛠️ Available Tools

| Tool | Description |
|------|-------------|
| `read_file` | Reads content from a local file |
| `write_file` | Creates or overwrites a local file |
| `execute_terminal` | Runs bash commands with timeout (120s) |
| `save_repo_context` | Persists analysis to project memory file |

### Security Restrictions
The following commands are blocked for safety:
- `rm -rf /`
- `mkfs`
- `dd`

---

## 📜 License

This project is provided as-is for educational and development purposes.

---

## 🤝 Contributing

Contributions are welcome! Please ensure any changes maintain the human-in-the-loop philosophy and step-by-step validation approach.

---

<p align="center">
  Built with ❤️ using Streamlit, Anthropic Claude & AWS Bedrock
</p>
