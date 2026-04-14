# Docker

## Build the Image

```bash
docker build -t pdf-pipeline .
```

The image is a 3-stage build based on `python:3.12-slim` with `poppler-utils`
and `tesseract-ocr` installed. It runs as a non-root `pipeline` user (uid 1000).

## Run the Pipeline

```bash
docker run --rm \
  -v "$PWD/data:/app/data" \
  -v "$PWD/outputs:/app/outputs" \
  -v "$PWD/configs:/app/configs" \
  pdf-pipeline
```

## Docker Compose

### Full pipeline

```bash
docker compose up pipeline
```

### Analysis only

```bash
docker compose run --rm analyze
```

### Run tests in Docker

```bash
docker compose --profile test run --rm test
```

### Lint check

```bash
docker compose --profile lint run --rm lint
```

## GPU Support

For GPU-accelerated Docling, mount the CUDA runtime:

```bash
docker run --rm --gpus all \
  -v "$PWD/data:/app/data" \
  -v "$PWD/outputs:/app/outputs" \
  pdf-pipeline --engine docling
```

## Health Check

The image includes a built-in health check:

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --retries=2 \
  CMD ["python", "-c", "import cortexmark; print('ok')"]
```

Check health status:

```bash
docker inspect --format='{{.State.Health.Status}}' <container_id>
```

## Security

- Non-root `pipeline` user (uid/gid 1000)
- No elevated capabilities
- `restart: "no"` policy (no auto-restart loops)
