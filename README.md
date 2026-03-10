# StudyGuru Concept Visual Backend

This service is a standalone FastAPI backend that generates AI-backed educational concept visuals for StudyGuru.

## Responsibilities

- Analyze concept complexity from the learning content payload
- Interpret the admin focus prompt
- Build pedagogically guided prompts that do more than mirror the admin text
- Generate high-clarity visuals through a Hugging Face free-tier compatible provider
- Export full-size and thumbnail PNG assets for the main backend

## Run locally

```powershell
cd ConceptVisualBackend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
# Create .env from .env.example and set HF_TOKEN before starting the server.
uvicorn src.main:app --host 0.0.0.0 --port 8002
```

## Service contract

- Health check: `GET /health/`
- Render visuals: `POST /v1/concept-visuals/render`

The service expects an internal service token in `X-StudyGuru-Service-Token`.

## Provider defaults

- Hugging Face token source: `HF_TOKEN`
- Routed provider: `replicate`
- Default model: `black-forest-labs/FLUX.1-schnell`
- Default FLUX.1-schnell sampling: `4` inference steps and `0.0` guidance scale
- Free-tier note: routed requests use the Hugging Face account credits, so generation stops once the free monthly credits are exhausted.
