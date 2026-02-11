# Repository Audit & Cleanup Guide

## Objective
This document maps the **actual runtime architecture** of the repository and identifies likely cleanup targets so you can remove low-value code safely.

---

## 1) What is the real product in this repo?

### Runtime entrypoint
- The backend starts from `backend/main.py`, builds a FastAPI app, configures logging, and mounts routers for auth/campaign/generate/assets/billing and ad-agent endpoints.
- Startup also initializes Secret Manager loading, optional Firestore/GCS clients, and enforces ffmpeg availability.

### Core ad-creation flow
- The production ad flow is the `AdCreationPipeline` in `backend/app/ad_agent/pipelines/ad_creation_pipeline.py`.
- Despite historical references to larger workflows, current execution path is the simplified 5-step path:
  1. prompt generation,
  2. Veo clip generation with continuity,
  3. clip merge,
  4. voice enhancement,
  5. finalize/upload.
- The primary API surface for this pipeline is in `backend/app/routes/ad_agent.py` (`/create`, `/jobs/{id}`, `/download`, streaming endpoints).

### Supporting platform modules
- `backend/app/database/firestore_db.py` and `backend/app/database/gcs_storage.py` handle persistence/storage integration.
- `backend/app/middleware/auth.py` + `backend/app/secrets.py` define auth and key loading behavior.
- `backend/app/routes/generate.py` still supports generic Unified API image/video generation jobs and polling.

---

## 2) High-confidence “keep” areas (business-critical)

These should be treated as core and refactored incrementally (not deleted):

1. `backend/main.py`
2. `backend/app/routes/ad_agent.py`
3. `backend/app/ad_agent/**` (agents, clients, pipeline, interfaces, utils)
4. `backend/app/database/**`
5. `backend/app/middleware/**`
6. `backend/app/services/unified_api_client.py`
7. Deployment/runtime files:
   - `Dockerfile`
   - `backend/startup.sh`
   - `backend/requirements.txt`

---

## 3) Strong cleanup candidates (likely clutter / non-product files)

### A) Root-level ad-hoc scripts
The repository previously had many one-off scripts (`test_*.py`, `monitor_*.py`, `check_*.py`, `kill_*.py`, etc.) at root. They have now been consolidated under `tools/manual/`.

A reference scan found **no in-repo references** from product runtime files to these scripts. This suggests they are manual/debug utilities rather than integrated product code.

Examples:
- `test_stream_ad.py`
- `test_upload_ad.py`
- `test_cloud_run_ad.py`
- `monitor_job_live.py`
- `check_job_logs.py`
- `kill_all_servers.py`
- `create_fresh_ad_job.py`
- `parse_job_logs.py`

**Cleanup recommendation:**
- Move these into a dedicated folder like `tools/manual/` or `scripts/manual/`.
- Keep only scripts still used in day-to-day operations.
- Delete duplicates after confirming owner usage.

### B) Documentation drift / stale docs
The docs include historical notes from previous cleanup and architecture transitions. Some docs still describe older step counts/workflows and may conflict with current code behavior.

**Cleanup recommendation:**
- Keep one source-of-truth architecture doc (current flow).
- Archive outdated docs in `docs/archive/`.
- Add “Last validated against commit” metadata to major docs.

### C) Potentially unused instantiated components
In `AdCreationPipeline.__init__`, `creative_agent` and `clip_verifier` are instantiated.
Current simplified execution path appears to run steps 1–5 and does not obviously call those components in the active flow.

**Cleanup recommendation:**
- Confirm whether verification/suggestions are intentionally disabled.
- If inactive, either:
  - remove instantiation now, or
  - gate behind feature flags with explicit TODO and telemetry.

---

## 4) Main architecture problems to address during cleanup

1. **Mixed concerns in one repository root**
   - Product backend + operational scripts + investigation scripts are mixed at top-level.

2. **Workflow/documentation mismatch risk**
   - Comments and docs mention older workflows while active code uses simplified flow.

3. **Hard-to-assess script value**
   - Many scripts are useful only for incident/debug contexts but are unlabeled and ungrouped.

4. **No clear test boundary**
   - Root `test_*.py` scripts appear to be manual integration runners, not structured automated tests.

---

## 5) Safe cleanup plan (recommended order)

### Phase 1: Non-breaking organization
- Create folders:
  - `tools/manual/` for ad-hoc operational scripts
  - `docs/archive/` for outdated docs
- ✅ Completed: moved root scripts into `tools/manual/` without changing logic.
- Add a short README in `tools/manual/` describing each script and when to use it.

### Phase 2: Remove obvious dead code/docs
- Delete scripts unused for N days (owner-confirmed).
- Remove duplicate docs and old reports that are superseded.
- Keep one authoritative “Current Architecture” doc.

### Phase 3: Code-level cleanup
- Remove or feature-flag inactive pipeline components.
- Split very large modules (`ad_agent.py`, pipeline) into smaller files by responsibility.
- Add structured tests for:
  - pipeline step transitions,
  - storage checkpoint/recovery,
  - streaming SSE output contract.

### Phase 4: Governance
- Add CI checks:
  - lint + formatting,
  - import dead-code detection,
  - docs freshness check (optional).
- Add `CONTRIBUTING.md` conventions for where scripts/docs should live.

---

## 6) Practical “do not break prod” guardrails

Before deleting anything, require:
1. Search for references in code and docs.
2. Verify deployment files do not depend on target files.
3. Run a smoke test:
   - app startup,
   - `/health`,
   - `/api/ad-agent/health`,
   - one dry-run ad creation request (or mocked equivalent).
4. Keep a short-lived branch for rollback.

---

## 7) Bottom line

You are **not wrong**: there is meaningful cleanup opportunity here, especially in root-level script sprawl and doc drift. The core backend/ad-agent implementation is real and should be preserved, but the repository would benefit significantly from organizing/removing non-product files in a controlled pass.
