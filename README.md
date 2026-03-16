# Nutritional Chatbot for Chronic Kidney Disease

AI-powered nutritional assistant for patients with chronic kidney disease (CKD), built for [Alba Dialysis & Transplants](https://albadialisis.com) — a nephrology clinic network in Guanajuato, Mexico.

The chatbot helps patients manage their renal diet, understand lab values, monitor symptoms, and receive personalized meal plans — all in Mexican Spanish with a warm, empathetic tone.

## Architecture

```
Client (SSE / JSON)
    │
    ├── POST /chat          → Lambda (handler.py)         → JSON response
    ├── POST /chat-stream   → Lambda (streaming_handler.py) → SSE stream
    └── GET  /health        → inline health check
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Orchestrator Agent                                  │
│  Routes patient queries, collects context naturally  │
│                                                      │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Education │  │  Monitoring  │  │ Nutrition    │  │
│  │ (tool)   │  │  (tool)      │  │ Plan (handoff)│  │
│  └──────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────┬───────────────────────────────┘
                      │
                      ▼
              Safety Post-Processor
              (validates every response)
                      │
                      ▼
              DynamoDB (sessions, messages, analytics, feedback)
```

### Multi-Agent System

| Agent | Role | Integration |
|-------|------|-------------|
| **Orchestrator** | Routes queries, collects patient context, answers simple questions | Main entry point |
| **Nutrition Plan** | Creates personalized meal plans based on CKD stage, weight, restrictions | Handoff (multi-turn) |
| **Education** | Explains kidney disease concepts, lab values, dietary restrictions | Tool (single-turn) |
| **Monitoring** | Evaluates reported symptoms, contextualizes lab results, flags emergencies | Tool (single-turn) |
| **Input Guardrail** | Detects prompt injection attempts before the orchestrator processes the message | Runs in parallel on all inputs |

Education and Monitoring agents are integrated as tools (`as_tool`) so the orchestrator reformulates their responses in a unified voice. The Nutrition Plan agent uses a handoff because it needs multi-turn follow-up for meal plan generation. The Input Guardrail runs in parallel with the orchestrator to detect prompt injection with zero added latency for legitimate requests.

All agents use `gpt-5-nano-2025-08-07`. The Education agent has `WebSearchTool` for PubMed/kidney.org lookups.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI Framework | [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) (Python) |
| Compute | AWS Lambda (Python 3.11) |
| Streaming | FastAPI + Lambda Web Adapter (SSE) |
| Database | DynamoDB (4 tables, pay-per-request) |
| Infrastructure | AWS CDK (TypeScript) |
| Secrets | AWS Secrets Manager |
| CI/CD | GitHub Actions → `cdk deploy` |

## Project Structure

```
nutritional-chatbot/
├── bin/                            # CDK app entry point
├── lib/                            # CDK infrastructure
│   ├── nutritional-chatbot-stack.ts
│   └── constructs/
│       ├── dynamoDb/               # DynamoDB table definitions
│       └── lambda/                 # Lambda function builder
├── lambda/chatbot/                 # Python Lambda code
│   ├── handler.py                  # Non-streaming handler
│   ├── streaming_handler.py        # FastAPI streaming handler
│   ├── requirements.txt
│   ├── nutritional_agents/
│   │   ├── orchestrator.py         # Main routing agent
│   │   ├── nutrition_plan.py       # Meal plan generation
│   │   ├── education.py            # CKD education + web search
│   │   ├── monitoring.py           # Symptom tracking
│   │   ├── safety.py               # Input guardrail (prompt injection detection)
│   │   └── alba_knowledge.py       # Clinic-specific information
│   └── utils/
│       └── dynamodb_client.py      # DynamoDB operations
├── .github/workflows/
│   └── deploy.yml                  # CI/CD pipeline
├── cdk.json
├── package.json
└── tsconfig.json
```

## API

### `POST /chat` — Complete Response

```json
// Request
{
  "message": "Que alimentos debo evitar con potasio alto?",
  "session_id": "uuid (optional, creates new session if omitted)"
}

// Response
{
  "response": "Para potasio alto, es importante limitar...",
  "session_id": "abc-123-...",
  "title": "Que alimentos debo evitar..."
}
```

### `POST /chat-stream` — Server-Sent Events

Same request body. Response is an SSE stream with these event types:

| Event Type | Payload | Description |
|-----------|---------|-------------|
| `start` | `session_id`, `title` | Session created |
| `chunk` | `content` | Text delta from the model |
| `end` | `agent_used` | Stream complete |
| `error` | `content` | Error message |

## DynamoDB Schema

| Table | PK | SK | GSI | Purpose |
|-------|----|----|-----|---------|
| `nutritional-chatbot-sessions` | `session_id` | — | — | Conversation sessions |
| `nutritional-chatbot-messages` | `session_id` | `sequence_number` (N) | `by_message_id` | Message history |
| `nutritional-chatbot-analytics` | `session_id` | `created_at` | `by_date` | Agent performance metrics |
| `nutritional-chatbot-feedback` | `session_id` | `created_at` | `by_date` | User satisfaction ratings |

## Prerequisites

- Node.js 18+
- Python 3.11+
- AWS CLI configured with appropriate credentials
- AWS CDK CLI (`npm install -g aws-cdk`)

## Setup

```bash
# Install CDK dependencies
npm install

# Install Python dependencies (for local development)
cd lambda/chatbot
pip install -r requirements.txt
cd ../..

# Store your OpenAI API key in Secrets Manager
aws secretsmanager create-secret \
  --name kidney-nutritional-chatbot/secrets \
  --secret-string '{"OPENAI_API_KEY":"sk-..."}'

# Bootstrap CDK (first time only)
npx cdk bootstrap

# Deploy
npx cdk deploy
```

## Development

```bash
# Compile TypeScript
npm run build

# Watch mode
npm run watch

# Run tests
npm run test

# Preview infrastructure changes
npx cdk diff

# Synthesize CloudFormation template
npx cdk synth
```

## CI/CD

Pushes to `main` trigger automatic deployment via GitHub Actions. The workflow:

1. Installs Node.js 18 + Python 3.11 dependencies
2. Synthesizes and diffs the CDK stack
3. Deploys with `cdk deploy --require-approval never`

**Required GitHub Secrets:** `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ACCOUNT_ID`

## Security — Prompt Injection Prevention

Three layers of defense prevent prompt injection attacks:

1. **Message length limit** (2000 chars) — Rejects oversized payloads before any processing. Enforced at the handler level (`handler.py`) and Pydantic validation (`streaming_handler.py`)

2. **`InputGuardrail`** (SDK-native) — A lightweight `gpt-5-nano` agent classifies every input as injection or legitimate **in parallel** with the orchestrator (zero added latency for normal requests). If triggered, raises `InputGuardrailTripwireTriggered` and returns a safe fallback without the orchestrator ever processing the malicious input

3. **Anti-injection system prompt** — The orchestrator prompt explicitly instructs the model to treat user content as data (not instructions), refuse to reveal internal prompts, and stay within the kidney nutrition domain

Medical safety (dangerous advice, missing disclaimers, emergency escalation) is handled by the agent prompts themselves — each specialized agent has detailed safety constraints built into its instructions.

## Key Design Decisions

- **Unified voice:** Education and Monitoring agents run as tools (`as_tool`) so the orchestrator reformulates their output — the patient always feels they're talking to one assistant
- **Nutrition Plan as handoff:** Meal plan generation requires multi-turn data collection (CKD stage, weight, height, restrictions), so it uses a full handoff for conversational flow
- **Microsecond sort keys:** Message ordering uses `int(time.time() * 1_000_000)` instead of read-then-increment sequences to avoid race conditions under concurrent writes
- **Lambda-safe async:** All DynamoDB writes use `await asyncio.gather()` instead of `asyncio.create_task()` to prevent data loss when the Lambda event loop tears down
- **Mexican Spanish:** All patient-facing content uses formal-friendly "usted", Mexican food terminology (papa, ejote, aguacate), and avoids anglicisms
