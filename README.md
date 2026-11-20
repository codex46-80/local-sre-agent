# 🤖 Pixel SRE Agent & GitOps Infrastructure

A local-first **AI Software & SRE Engineering Agent** powered by **Ollama** (`qwen2.5-coder:14b`) with an animated **2D Pixel AI Employee** interface in Gradio, paired with hardened **Kubernetes**, **Terraform**, and **Argo CD** configurations for Minikube.

---

## ✨ Key Features

### 🧠 Local AI Code Agent (`code_agent.py`)
- **100% Local Execution:** Runs against local Ollama (`http://localhost:11434/v1`) with zero cloud API costs.
- **Animated 2D Pixel AI Employee:** Real-time HTML5 `<canvas>` office avatar that paces while thinking, types with code particles during tool calls, and celebrates task completion.
- **Built-In Safety Guardrails:**
  - Never modifies files, creates branches, or commits without explicit user confirmation.
  - Automatic `.bak` backups on file overwrites (excluded from `git commit`).
  - Duplicate tool-call loop protection, chunked large-file reading, and non-interactive shell execution.
- **Full Developer Workflow:** Project structure inspection, linting (`ruff` / `eslint`), test execution, diff previews, `.patch` exports, branch creation, and GitHub PR creation (`gh`).

### ☸️ Infrastructure & GitOps (`environments/`)
- **Terraform (`environments/argocd/argocd.tf`):** Provisions the `argocd` namespace (with `lifecycle { prevent_destroy = true }`) and deploys Argo CD via Helm (`version = "7.7.0"`).
- **Hardened Kubernetes Workloads (`environments/nginx/nginx.yaml`):** Production-style Nginx Deployment & Service configured with non-root `securityContext`, resource requests/limits, readiness/liveness probes, and standard labels.

---

## 📁 Project Structure

```text
.
├── code_agent.py                 # Local AI code agent (CLI + Gradio 6 Pixel Employee UI)
├── environments/
│   ├── argocd/
│   │   └── argocd.tf             # Terraform bootstrap for Argo CD namespace & Helm release
│   └── nginx/
│       └── nginx.yaml            # Hardened Kubernetes Deployment & ClusterIP Service
├── .gitignore
└── README.md
```

---

## 🛠️ Prerequisites

- **Python 3.10+**
- **Ollama** installed and running locally (`ollama serve`)
- **Local Coding Model:** e.g., `qwen2.5-coder:14b`
- *(Optional for Infrastructure)* **Minikube**, **kubectl**, **Terraform**, and **GitHub CLI (`gh`)**

---

## 🚀 Quick Start (From Scratch to Running)

### 1. Clone the Repository
```bash
git clone https://github.com/<your-username>/pixel-sre-agent.git
cd pixel-sre-agent
```

### 2. Start Ollama & Pull the Model
```bash
ollama serve
ollama pull qwen2.5-coder:14b
```

### 3. Set Up Python Environment & Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install openai gradio
```

### 4. Launch the Agent

**Web UI Mode (with Animated 2D Pixel AI Employee):**
```bash
python code_agent.py --ui
```
Open **http://127.0.0.1:7860** in your browser.

**CLI Mode:**
```bash
python code_agent.py
```

**Dry-Run Mode (Inspect & Propose Only, Zero File Writes):**
```bash
python code_agent.py --ui --dry-run
```

---

## 💬 Example Prompts

- **Read-Only Audit:**
  > *"Call `get_git_status` once and `get_project_structure` once, then read `environments/argocd/argocd.tf` and `environments/nginx/nginx.yaml`. Summarize current status and propose improvements without writing files."*
- **Safe Branch & Harden Workflow:**
  > *"Create branch `fix/hardening`, apply the proposed improvements to `environments/nginx/nginx.yaml`, show the diff, and commit the changes."*
- **Export Patch for Review:**
  > *"Export current changes to `changes.patch`."*

---

## ☸️ Infrastructure Setup (Minikube + Terraform + Argo CD)

### 1. Start Minikube
```bash
minikube start
```

### 2. Bootstrap Argo CD with Terraform
```bash
terraform -chdir=environments/argocd init
terraform -chdir=environments/argocd validate
terraform -chdir=environments/argocd plan
terraform -chdir=environments/argocd apply
```

### 3. Validate & Apply Nginx Manifest
```bash
kubectl apply --dry-run=client -f environments/nginx/nginx.yaml
kubectl apply -f environments/nginx/nginx.yaml
```

---

## 🔒 Security & Repo Hygiene

- **No Secrets Committed:** Ensure `.env`, `*.tfstate`, `*.tfstate.*`, `.terraform/`, `*.bak`, and `*.patch` remain in `.gitignore` before pushing to a public repository.
- **Explicit Approval Required:** The agent enforces human-in-the-loop confirmation before writing files, switching branches, committing, or opening pull requests.

---

## 📄 License

MIT License — feel free to fork, adapt, and extend for your local AI workflows.