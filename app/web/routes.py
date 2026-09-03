"""FastAPI routes for the web UI."""

from __future__ import annotations

import asyncio
import contextlib
import os
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from app.agent import graph
from app.agent.state import AgentState
from app.config import load_config
from app.input.adapter import load_document
from app.input.test_suite_generator import generate_test_suite_docx
from app.llm.client import LMStudioProvider
from app.llm.openapi_converter import (
    convert_openapi_to_suite,
    load_openapi_content,
    sanitize_cases,
)
from app.llm.schemas import AuthConfig
from app.runner.base import VerdictBuilder
from app.runner.reporter import render_excel
from app.web.jobs import JOBS

router = APIRouter()


def _build_auth(
    auth_type: str,
    username: str | None = None,
    password: str | None = None,
    token: str | None = None,
    api_key_header: str | None = None,
    api_key_value: str | None = None,
) -> AuthConfig:
    """Build an AuthConfig from the form fields supplied by the UI."""
    normalized = (auth_type or "none").lower()
    if normalized == "basic":
        if not username or not password:
            raise HTTPException(status_code=422, detail="Basic auth requires username and password")
        return AuthConfig(type="basic", username=username, password=password)
    if normalized == "bearer":
        if not token:
            raise HTTPException(status_code=422, detail="Bearer auth requires token")
        return AuthConfig(type="bearer", token=token)
    if normalized == "api_key":
        if not api_key_header or not api_key_value:
            raise HTTPException(
                status_code=422, detail="API key auth requires header name and value"
            )
        return AuthConfig(
            type="api_key",
            header_name=api_key_header,
            header_value=api_key_value,
        )
    return AuthConfig(type="none")


def _build_provider_config(
    lm_studio_url: str | None,
    lm_model: str | None,
) -> dict[str, str]:
    """Build provider config from UI inputs, falling back to environment."""
    config = load_config()
    return {
        "base_url": lm_studio_url or config.lm_studio_url,
        "model": lm_model or config.lm_model,
    }


def _run_pipeline(
    job_id: str,
    file_path: str,
    base_url: str,
    auth: AuthConfig,
    provider_config: dict[str, str],
    analyze: bool,
) -> None:
    """Synchronous worker executed in a background thread."""
    config = load_config()
    config.ensure_dirs()
    JOBS.update(job_id, status="running")

    def progress_callback(label: str) -> None:
        JOBS.update(job_id, current_case=label)

    try:
        chunks = load_document(file_path)
        state = AgentState(
            base_url=base_url,
            auth=auth,
            chunks=chunks,
            provider_config=provider_config,
        )
        final_state = graph.run(
            state,
            analyze=analyze,
            progress_callback=progress_callback,
            report_formats=["excel"],
        )

        builder = VerdictBuilder(base_url=final_state.base_url)
        builder.verdicts = final_state.verdicts
        builder.results = final_state.results
        summary = builder.summarize()

        summary_out = {
            "base_url": final_state.base_url,
            "total": len(final_state.verdicts),
            "passed": sum(1 for v in final_state.verdicts if v.status == "PASS"),
            "failed": sum(1 for v in final_state.verdicts if v.status == "FAIL"),
            "skipped": sum(1 for v in final_state.verdicts if v.status == "SKIPPED"),
            "verdicts": summary["verdicts"],
        }
        JOBS.update(
            job_id,
            status="done",
            summary=summary_out,
            current_case=None,
        )
    except Exception as exc:  # noqa: BLE001 - worker must not leak; surface as failed job.
        JOBS.update(
            job_id, status="failed", error=f"{type(exc).__name__}: {exc}", current_case=None
        )
    finally:
        with contextlib.suppress(OSError):
            os.remove(file_path)


def _write_file(path: str, content: bytes) -> None:
    """Synchronous helper to persist uploaded bytes to disk."""
    with open(path, "wb") as fh:
        fh.write(content)


@router.post("/run")
async def run_suite(
    file: UploadFile = File(...),  # noqa: B008 - FastAPI idiom for required UploadFile
    base_url: str = Form(...),
    auth_type: str = Form("none"),
    username: str | None = Form(None),
    password: str | None = Form(None),
    token: str | None = Form(None),
    api_key_header: str | None = Form(None),
    api_key_value: str | None = Form(None),
    lm_studio_url: str | None = Form(None),
    lm_model: str | None = Form(None),
    analyze: bool = Form(False),
) -> JSONResponse:
    """Upload a test suite and start the pipeline asynchronously."""
    config = load_config()
    config.ensure_dirs()

    auth = _build_auth(auth_type, username, password, token, api_key_header, api_key_value)
    provider_config = _build_provider_config(lm_studio_url, lm_model)

    job_id = JOBS.create()
    upload_dir = Path(config.temp_upload_dir) / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = file.filename or "suite.docx"
    file_path = str(upload_dir / filename)

    content = await file.read()
    await asyncio.to_thread(_write_file, file_path, content)

    asyncio.create_task(
        asyncio.to_thread(
            _run_pipeline, job_id, file_path, base_url, auth, provider_config, analyze
        )
    )
    return JSONResponse({"job_id": job_id})


@router.get("/result/{job_id}")
async def get_result(job_id: str) -> JSONResponse:
    """Return the current status and summary for a job."""
    try:
        job = JOBS.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    return JSONResponse(job.model_dump())


@router.get("/reports/{job_id}.xlsx")
async def get_report_excel(job_id: str) -> StreamingResponse:
    """Generate and serve the Excel report for a completed job on the fly."""
    try:
        job = JOBS.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc

    if job.summary is None:
        raise HTTPException(status_code=404, detail="Report not available yet")

    try:
        excel_bytes = render_excel(job.summary)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {exc}") from exc

    filename = f"qa-report-{job_id}.xlsx"
    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/test-connection")
async def test_connection(
    lm_studio_url: str = Form(...),
    lm_model: str = Form(...),
) -> JSONResponse:
    """Test whether the LM Studio server is reachable and lists the model."""
    provider = LMStudioProvider(base_url=lm_studio_url, model=lm_model)
    try:
        provider.chat(
            [
                {"role": "system", "content": "Respond with OK only."},
                {"role": "user", "content": "OK?"},
            ],
            temperature=0.0,
        )
        return JSONResponse({"status": "ok", "message": "LM Studio is reachable"})
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot reach LM Studio: {type(exc).__name__}: {exc}",
        ) from exc


@router.post("/convert-openapi")
async def convert_openapi(
    file: UploadFile = File(...),  # noqa: B008 - FastAPI idiom for required UploadFile.
    lm_studio_url: str = Form(...),
    lm_model: str = Form(...),
) -> StreamingResponse:
    """Convert an uploaded OpenAPI spec into a test suite DOCX."""
    provider = LMStudioProvider(base_url=lm_studio_url, model=lm_model)

    try:
        raw = await file.read()
        openapi_content = load_openapi_content(raw)
        result = await asyncio.to_thread(convert_openapi_to_suite, provider, openapi_content)
        result.cases = sanitize_cases(result.cases)

        output_path = str(Path(load_config().temp_upload_dir) / f"{file.filename or 'suite'}.docx")
        Path(load_config().temp_upload_dir).mkdir(parents=True, exist_ok=True)
        generate_test_suite_docx(
            result.cases, title="Test Suite from OpenAPI", output_path=output_path
        )

        safe_name = (file.filename or "openapi").rsplit(".", 1)[0] + "-test-suite.docx"
        file_bytes = await asyncio.to_thread(Path(output_path).read_bytes)
        return StreamingResponse(
            BytesIO(file_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={safe_name}"},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gagal mengkonversi OpenAPI: {exc}") from exc
