# Deploying InstructVid

## One container

```powershell
docker build -t instructvid .
docker run -p 8000:8000 --env-file .env `
  -v "$env:APPDATA\gcloud:/root/.config/gcloud:ro" `
  -v instructvid-data:/app/data instructvid
```

The image serves the API and the built web UI on port 8000 and contains ffmpeg, Node, the render
worker and the Chromium libraries Remotion needs. Project data (uploads, versions, Chroma, the
checkpoint and metrics databases) lives in `/app/data` — mount a volume.

## Credentials

Vertex AI is reached through **Application Default Credentials**:

- locally: `gcloud auth application-default login`, then mount the gcloud config folder (above);
- on a server: attach a service account (Cloud Run / GCE) or mount a key file and set
  `GOOGLE_APPLICATION_CREDENTIALS`. The service account needs `roles/aiplatform.user`.

Never put credentials in the image or the repository. `.env` sets the project, the location (`eu`)
and the spend caps (`MAX_RUN_COST_USD`, `MAX_TOTAL_SPEND_USD`).

## Sizing

Rendering is CPU-bound (headless Chromium): a 60 s 1080×1920 video takes about one minute on 8
fast cores with 16 GB RAM. Remotion encodes in parallel with rendering only when free RAM exceeds
~2 GB + its frame-buffer estimate, so give the container ≥ 8 GB. One render runs per project at a
time; concurrent projects queue on CPU.

## Quotas

Gemini Flash may return `429 RESOURCE_EXHAUSTED` on new projects. The router retries with backoff
and then falls back to the `fallback_reasoning` role (Argon) for five minutes. Request a quota
increase for `gemini-3.8-flash` in the region you use to keep costs down.

## Licence

Commercial deployments with more than three people need a Remotion company licence — set
`REMOTION_LICENSE_KEY` ([ADR 0002](adr/0002-remotion-licence.md)).
