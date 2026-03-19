# StudyGuru Concept Visual Backend

The concept-visual backend is a dedicated FastAPI microservice that generates educational concept visuals for the main StudyGuru platform. It accepts structured concept-learning payloads, builds pedagogically guided prompts, renders image candidates through a Hugging Face-backed provider, and writes full-size and thumbnail PNG assets.

## Responsibilities

- Receive internal render requests from the main backend
- Interpret concept metadata, learning content, and optional admin prompts
- Build prompt variants tuned for teaching clarity
- Render concept visuals through a configured Hugging Face provider
- Save image and thumbnail assets to the configured output directory
- Expose readiness and liveness endpoints for Cloud Run

## API Contract

### Readiness

- `GET /health/`
- `GET /health/live`

### Render endpoint

- `POST /v1/concept-visuals/render`

### Authentication

This service is internal-only by design. Requests to the render endpoint must include:

```http
X-StudyGuru-Service-Token: <shared-internal-token>
```

## Request Flow

1. The main backend sends concept context and learning content.
2. This service derives a visual blueprint and prompt variants.
3. The image provider renders one or more candidates.
4. The service stores:
   - full-size PNG
   - thumbnail PNG
   - metadata such as prompt, style, dimensions, and fingerprint
5. The response returns relative asset paths and render metadata.

## Local Development

### Run with Docker Compose

From the repository root:

```bash
docker compose up --build concept-visual-service
```

### Run the service directly

```bash
cd StudyGuru_ConceptVisualBackend

# Install uv (if not already installed)
pip install uv

# Create virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt

# Run the FastAPI server
uvicorn src.main:app --host 0.0.0.0 --port 8002 --reload
```

## Required Configuration

Minimum configuration:

| Variable | Purpose |
| --- | --- |
| `CONCEPT_VISUAL_SERVICE_TOKEN` | Shared internal token required by callers |
| `HF_TOKEN` | Hugging Face access token |
| `CONCEPT_VISUAL_IMAGE_MODEL` | Model identifier used for rendering |
| `CONCEPT_VISUAL_OUTPUT_DIR` | Output directory for generated assets |

Commonly tuned variables:

| Variable | Purpose |
| --- | --- |
| `CONCEPT_VISUAL_IMAGE_PROVIDER` | Routed provider name |
| `CONCEPT_VISUAL_PROVIDER_TIMEOUT_SECONDS` | Provider timeout |
| `CONCEPT_VISUAL_MAX_VARIANTS` | Maximum variants returned per request |
| `CONCEPT_VISUAL_IMAGE_WIDTH` | Output width |
| `CONCEPT_VISUAL_IMAGE_HEIGHT` | Output height |
| `CONCEPT_VISUAL_NEGATIVE_PROMPT` | Default negative prompt |
| `CORS_ALLOW_ORIGINS` | Allowed browser origins |
| `LOG_LEVEL` | Application log level |

## Example Request

```bash
curl -X POST "http://localhost:8002/v1/concept-visuals/render" \
  -H "Content-Type: application/json" \
  -H "X-StudyGuru-Service-Token: ${CONCEPT_VISUAL_SERVICE_TOKEN}" \
  -d '{
    "subject_id": "subject_1",
    "subject_name": "Physics",
    "grade_level": "Grade 10",
    "concept_id": "concept_1",
    "concept_name": "Electric Current",
    "concept_description": "Movement of charge through a conductor",
    "concept_material_id": "material_1",
    "prompt": "Focus on charge flow and circuit intuition",
    "max_variants": 2,
    "content": {
      "metadata": {},
      "highlights": ["Current is charge per unit time"],
      "sections": []
    }
  }'
```

## Output

The service stores generated files under the configured output directory using a structure based on:

```text
<output_dir>/<subject_id>/<concept_material_id>/
```

Returned payloads include:

- image path
- thumbnail path
- visual style
- focus area
- complexity level
- pedagogical score
- prompt and render metadata

## Health and Observability

Readiness validates:

- internal service token configuration
- image provider configuration
- access to the configured Hugging Face model

The service emits structured JSON logs to support Cloud Run operations.

## Production Deployment Notes

Recommended production posture:

- Deploy as a private Cloud Run service
- Restrict ingress to internal callers where possible
- Inject `CONCEPT_VISUAL_SERVICE_TOKEN` and `HF_TOKEN` through Secret Manager
- Treat local disk as ephemeral

Important note:

- In Docker Compose, generated assets are visible to the main backend because both services share a mounted volume.
- In separate Cloud Run deployments, local filesystem sharing does not exist. If downstream services need durable access to generated assets, persist them to shared object storage.

## Verification

Useful local check:

```bash
python3 -m compileall src
```

For end-to-end verification, call `/health/` and then exercise `/v1/concept-visuals/render` using a valid service token and provider token.
