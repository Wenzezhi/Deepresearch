"""Read-only HTTP API for the report quality gate.

Nothing here writes to the database or to disk: the audit is derived on demand
from the run's stored events and task snapshot.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from quality import engine, parse, render
from storage import now


class QualityReportInput(BaseModel):
    run_id: str = Field(min_length=1, max_length=64)
    style: Literal["plain", "gbt7714-lite"] = "plain"
    include_uncited: bool = True


def _load_events(store, run_id: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    cursor = 0
    while True:
        batch = store.events(run_id, cursor)
        if not batch:
            break
        events.extend(item["event"] for item in batch)
        cursor = batch[-1]["seq"]
        if len(batch) < 1000:
            break
    return events


def _assemble(store, jobs, run_id: str):
    try:
        record = store.run(run_id)
    except KeyError as exc:
        raise HTTPException(404, "研究记录不存在") from exc

    report = ""
    sources: list[parse.Source] = []
    for event in _load_events(store, run_id):
        kind = event.get("type")
        if kind == "reset":
            report = ""
            sources = []
        elif kind == "final_report":
            report = event.get("report") or ""
        elif kind == "sources":
            sources.extend(
                parse.parse_sources(
                    event.get("latest_sources") or "", event.get("task_id")
                )
            )

    tasks: list[dict[str, Any]] = []
    if jobs is not None:
        try:
            tasks = jobs.snapshot(run_id)
        except Exception:  # snapshot must never break the audit
            tasks = []
    for task in tasks:
        summary = task.get("sources_summary")
        if summary:
            sources.extend(parse.parse_sources(summary, task.get("id")))

    known_document_ids = {document["id"] for document in store.documents()}
    merged = parse.merge_sources(sources)
    topic = record.get("title") or record.get("topic") or ""
    return record, topic, report, merged, tasks, known_document_ids


def _audit_payload(store, jobs, run_id: str) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    _record, topic, report, sources, tasks, known = _assemble(store, jobs, run_id)
    result = engine.audit(report, sources, tasks, known)
    result["run_id"] = run_id
    result["topic"] = topic
    result["generated_at"] = now()
    return result, topic, result["sources"]


def router(store, jobs=None):
    api = APIRouter(prefix="/quality", tags=["report-quality"])

    @api.get("/audit/{run_id}")
    def audit_run(run_id: str) -> dict[str, Any]:
        result, _topic, _sources = _audit_payload(store, jobs, run_id)
        return result

    @api.post("/report")
    def quality_report(payload: QualityReportInput) -> dict[str, Any]:
        result, topic, sources = _audit_payload(store, jobs, payload.run_id)
        markdown = render.render_quality_report(
            result, topic=topic, generated_at=result["generated_at"]
        )
        references = render.render_references(
            sources,
            style=payload.style,
            include_uncited=payload.include_uncited,
        )
        return {
            "run_id": payload.run_id,
            "markdown": markdown,
            "references_markdown": references,
            "score": result["score"],
            "grade": result["grade"],
        }

    return api
