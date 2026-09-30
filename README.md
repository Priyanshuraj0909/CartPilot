# CartPilot 🛒🧭

**CartPilot** is an autonomous AI management layer for e-commerce storefronts. It coordinates specialized agents for pricing, restocking, promotions, and product listings under a central Master Orchestrator, adhering strictly to merchant-defined guardrails.

---

## Operating Loop

$$\text{SENSE} \longrightarrow \text{DECIDE} \longrightarrow \text{ACT} \longrightarrow \text{LEARN}$$

1. **Sense**: Ingest storefront inventory, sales velocity, order history, and margins.
2. **Decide**: Specialized agents evaluate opportunities and propose structured recommendations.
3. **Act**: Master orchestrator resolves cross-agent conflicts, validates merchant policies, and prompts human approval for high-risk actions before simulated execution.
4. **Learn**: Historical outcomes inform future confidence scores and recommendation thresholds.

---

## Phase 1 — Foundation

Phase 1 provides the core development environment, API health probe, responsive merchant dashboard, container orchestration, and testing framework.

### Architecture Components

| Component | Technology | Role |
| :--- | :--- | :--- |
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS | Dashboard UI (`/dashboard`) with 4 core metric cards |
| **Backend** | FastAPI, Python 3.12, Pydantic, SQLAlchemy 2.0 | Async REST API, CORS middleware, Health probes |
| **Database** | PostgreSQL 16 (asyncpg driver) | Relational persistence layer |
| **Cache/State** | Redis 7 | State store, rate-limiting, and agent locks |
| **Infra** | Docker & Docker Compose | Containerized local orchestration |

---

## Getting Started

### 1. Environment Configuration

Copy the example environment configuration:
```bash
cp .env.example .env
```

### 2. Infrastructure (Docker Compose)

Start PostgreSQL and Redis services:
```bash
docker compose up -d postgres redis
```

### 3. Backend Setup

```bash
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run test suite
pytest -v

# Start development server (Port 8000)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Health endpoint verification:
```bash
curl http://localhost:8000/health
# Response: {"status":"ok"}

curl http://localhost:8000/api/v1/health/detailed
# Response: {"status":"ok","app":"CartPilot",...}
```

### 4. Frontend Setup

```bash
cd frontend
npm install

# Run unit tests
npm run test:run

# Build bundle
npm run build

# Start dev server (Port 5173)
npm run dev
```

Dashboard is accessible at:
- `http://localhost:5173/dashboard`
- `http://localhost:5173/`

---

## Testing & Verification

Run the unified verification script from project root:
```bash
./scripts/verify_foundation.sh
```

---

## Safety & AI Guardrails

- **Zero Direct LLM Database Access**: LLMs produce structured outputs only; business logic and database updates are strictly handled by application code.
- **Human-in-the-Loop**: High-risk actions require merchant approval before execution.
- **Policy Enforcement**: Automated limit checks prevent price gouging, excessive discounting, and catastrophic stockouts.
