"""
Filter API — CSV + XLSX upload + processing endpoints.

Endpoints:
  POST /api/filter/upload          Upload CSV/XLSX, run filters, return results
  POST /api/filter/upload-scrape   Upload CSV/XLSX, scrape profiles, filter, return results
  POST /api/filter/download        Download filtered CSV
  POST /api/filter/preview         Preview first N results
  GET  /api/filter/presets         Get available filter configurations
"""
from __future__ import annotations

import csv
import io
import json
import asyncio
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from .filter_engine import (
    parse_uploaded_file,
    run_filter_pipeline,
    scrape_profiles_realtime,
    generate_csv_output,
    generate_json_output,
    FilterStats,
)

router = APIRouter(prefix="/api/filter", tags=["filter"])

ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.xls'}


def _validate_file(file: UploadFile) -> str:
    """Validate uploaded file extension. Returns the lowercase extension."""
    if not file.filename:
        # Try to infer from content_type
        ct = (file.content_type or '').lower()
        if 'csv' in ct:
            return '.csv'
        if 'spreadsheetml' in ct or 'excel' in ct or 'openxmlformats' in ct:
            return '.xlsx'
        raise HTTPException(status_code=400, detail={"code": "NO_FILE", "message": "No file uploaded — could not determine file type"})
    ext = '.' + file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail={
            "code": "INVALID_FILE",
            "message": f"Unsupported file type '{ext}'. Please upload a CSV or Excel (.xlsx) file."
        })
    return ext


async def _read_and_parse(file: UploadFile) -> list[dict]:
    """Read uploaded file, parse it, return records."""
    try:
        raw_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail={"code": "READ_ERROR", "message": f"Could not read file: {e}"})

    if not raw_bytes or len(raw_bytes) < 50:
        raise HTTPException(status_code=400, detail={
            "code": "EMPTY_FILE",
            "message": f"File appears empty or too small ({len(raw_bytes) if raw_bytes else 0} bytes)."
        })

    # Determine filename for parser; fallback to content-type hint
    fname = file.filename or 'data.csv'
    if not any(fname.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        ct = (file.content_type or '').lower()
        if 'spreadsheetml' in ct or 'excel' in ct:
            fname = 'data.xlsx'
        else:
            fname = 'data.csv'

    try:
        records = parse_uploaded_file(fname, raw_bytes)
    except Exception as e:
        raise HTTPException(status_code=400, detail={"code": "PARSE_ERROR", "message": f"Could not parse file: {e}"})

    if not records:
        raise HTTPException(status_code=400, detail={
            "code": "EMPTY_DATA",
            "message": "No valid records found. Ensure the file has email and/or slug columns."
        })

    return records


@router.post("/upload")
async def filter_upload(
    file: UploadFile = File(...),
    date_start: Optional[str] = Form(None),
    date_end: Optional[str] = Form(None),
) -> dict[str, Any]:
    """
    Upload a CSV or XLSX file and run the filtering pipeline.
    Returns JSON with kept accounts, removed accounts, and statistics.
    """
    _validate_file(file)
    records = await _read_and_parse(file)

    date_range = (date_start, date_end) if date_start and date_end else None
    kept, removed, stats = run_filter_pipeline(records=records, date_range=date_range)

    return {
        "status": "ok",
        "filename": file.filename,
        "total_records": stats.total,
        "kept_count": stats.kept,
        "removed_count": stats.removed,
        "cohort1_count": stats.cohort1,
        "cohort2_count": stats.cohort2,
        "removal_reasons": dict(stats.reasons.most_common(20)),
        "kept": kept,
        "removed": removed,
    }


@router.post("/upload-scrape")
async def filter_upload_with_scrape(
    file: UploadFile = File(...),
    date_start: Optional[str] = Form(None),
    date_end: Optional[str] = Form(None),
    scrape: bool = Form(True),
) -> dict[str, Any]:
    """
    Upload CSV/XLSX, optionally scrape external artist profiles in real-time,
    then run the full filtering pipeline with bio-based detection.

    When scrape=True, fetches profile data for each slug/handle
    to enable bio/story-based spam detection and cohort assignment.
    """
    _validate_file(file)
    records = await _read_and_parse(file)

    date_range = (date_start, date_end) if date_start and date_end else None

    scraped_data = None
    scrape_stats = {}

    if scrape:
        # Collect unique slugs from records
        slugs = list({r['slug'] for r in records if r.get('slug')})
        if slugs:
            # Run scraper in a thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            scraped_data = await loop.run_in_executor(
                None,
                lambda: scrape_profiles_realtime(
                    slugs=slugs,
                    max_workers=8,
                    progress_callback=lambda done, total: None,
                )
            )
            scrape_stats = {
                "slugs_scraped": len(slugs),
                "profiles_found": len(scraped_data),
                "success_rate": f"{len(scraped_data)/len(slugs)*100:.1f}%" if slugs else "0%",
            }

    kept, removed, stats = run_filter_pipeline(
        records=records,
        scraped_data=scraped_data,
        date_range=date_range,
    )

    return {
        "status": "ok",
        "filename": file.filename,
        "scraping_enabled": scrape,
        "scrape_stats": scrape_stats,
        "total_records": stats.total,
        "kept_count": stats.kept,
        "removed_count": stats.removed,
        "cohort1_count": stats.cohort1,
        "cohort2_count": stats.cohort2,
        "removal_reasons": dict(stats.reasons.most_common(20)),
        "kept": kept,
        "removed": removed,
    }


@router.post("/download")
async def filter_download(
    file: UploadFile = File(...),
    date_start: Optional[str] = Form(None),
    date_end: Optional[str] = Form(None),
    format: str = Form("csv"),
    scrape: bool = Form(False),
) -> StreamingResponse:
    """Upload CSV/XLSX, filter, and download the result."""
    _validate_file(file)
    records = await _read_and_parse(file)

    date_range = (date_start, date_end) if date_start and date_end else None

    scraped_data = None
    if scrape:
        slugs = list({r['slug'] for r in records if r.get('slug')})
        if slugs:
            loop = asyncio.get_event_loop()
            scraped_data = await loop.run_in_executor(
                None,
                lambda: scrape_profiles_realtime(slugs=slugs, max_workers=8)
            )

    kept, removed, stats = run_filter_pipeline(
        records=records,
        scraped_data=scraped_data,
        date_range=date_range,
    )

    if format == "json":
        output = json.dumps(generate_json_output(kept, removed, stats), indent=2, ensure_ascii=False)
        return StreamingResponse(
            io.BytesIO(output.encode('utf-8')),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=filtered_results.json"},
        )

    csv_output = generate_csv_output(kept, removed)
    return StreamingResponse(
        io.BytesIO(csv_output.encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=filtered_results.csv"},
    )


@router.post("/preview")
async def filter_preview(
    file: UploadFile = File(...),
    date_start: Optional[str] = Form(None),
    date_end: Optional[str] = Form(None),
    max_preview: int = Form(50),
    scrape: bool = Form(False),
) -> dict[str, Any]:
    """Upload CSV/XLSX, filter, and return a preview (first N kept + removed)."""
    _validate_file(file)
    records = await _read_and_parse(file)

    date_range = (date_start, date_end) if date_start and date_end else None

    scraped_data = None
    if scrape:
        slugs = list({r['slug'] for r in records if r.get('slug')})
        if slugs:
            loop = asyncio.get_event_loop()
            scraped_data = await loop.run_in_executor(
                None,
                lambda: scrape_profiles_realtime(slugs=slugs, max_workers=8)
            )

    kept, removed, stats = run_filter_pipeline(
        records=records,
        scraped_data=scraped_data,
        date_range=date_range,
    )

    return {
        "status": "ok",
        "filename": file.filename,
        "scraping_enabled": scrape,
        "total_records": stats.total,
        "kept_count": stats.kept,
        "removed_count": stats.removed,
        "cohort1_count": stats.cohort1,
        "cohort2_count": stats.cohort2,
        "removal_reasons": dict(stats.reasons.most_common(20)),
        "preview_kept": kept[:max_preview],
        "preview_removed": removed[:max_preview],
        "has_more_kept": len(kept) > max_preview,
        "has_more_removed": len(removed) > max_preview,
    }


@router.post("/upload-scrape-stream")
async def filter_upload_with_scrape_stream(
    file: UploadFile = File(...),
    date_start: Optional[str] = Form(None),
    date_end: Optional[str] = Form(None),
    scrape: bool = Form(True),
) -> StreamingResponse:
    """
    SSE streaming endpoint: uploads CSV/XLSX, scrapes profiles with live progress,
    then returns final filter results.

    SSE events:
      event: phase    {"phase": "uploading"|"scraping"|"filtering"|"done"}
      event: progress {"completed": N, "total": N, "found": N, "elapsed": N}
      event: done     {full JSON result}
      event: error    {"message": "..."}
    """
    import sys as _sys
    print(f"[STREAM] file={file.filename} size={file.size} content_type={file.content_type}", file=_sys.stderr, flush=True)
    try:
        _validate_file(file)
        records = await _read_and_parse(file)
        print(f"[STREAM] parsed {len(records)} records successfully", file=_sys.stderr, flush=True)
    except HTTPException as e:
        print(f"[STREAM] HTTPException: {e.detail}", file=_sys.stderr, flush=True)
        async def error_gen():
            yield _sse_event('error', {'message': e.detail.get('message', str(e.detail)) if isinstance(e.detail, dict) else str(e.detail)})
        return StreamingResponse(error_gen(), media_type='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'X-Accel-Buffering': 'no'})
    except Exception as e:
        print(f"[STREAM] Unexpected error: {type(e).__name__}: {e}", file=_sys.stderr, flush=True)
        async def error_gen2():
            yield _sse_event('error', {'message': f'{type(e).__name__}: {e}'})
        return StreamingResponse(error_gen2(), media_type='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'X-Accel-Buffering': 'no'})

    date_range = (date_start, date_end) if date_start and date_end else None

    async def event_generator():
        import time as _time

        scraped_data = {}
        scrape_stats = {}

        if scrape:
            slugs = list({r['slug'] for r in records if r.get('slug')})
            total = len(slugs)

            if total > 0:
                # Phase: scraping
                yield _sse_event('phase', {'phase': 'scraping', 'total': total})

                start_time = _time.time()
                completed = [0]
                found = [0]

                # Use a queue to send intermediate progress events
                import queue as _queue
                progress_queue = _queue.Queue()

                def progress_cb(done, tot):
                    found_so_far = len(scraped_data_cache[0]) if scraped_data_cache[0] else 0
                    elapsed_so_far = _time.time() - start_time
                    progress_queue.put({
                        'completed': done,
                        'total': tot,
                        'found': found_so_far,
                        'elapsed': round(elapsed_so_far, 1),
                    })

                scraped_data_cache = [{}]

                # Run scraper in thread pool
                loop = asyncio.get_event_loop()
                scrape_task = loop.run_in_executor(
                    None,
                    lambda: scrape_profiles_realtime(
                        slugs=slugs,
                        max_workers=8,
                        progress_callback=progress_cb,
                    )
                )

                # Poll the queue for progress events while scraping runs
                while not scrape_task.done():
                    try:
                        prog = progress_queue.get(timeout=0.3)
                        yield _sse_event('progress', prog)
                    except _queue.Empty:
                        pass
                    await asyncio.sleep(0)

                # Drain remaining queue items
                while not progress_queue.empty():
                    try:
                        prog = progress_queue.get_nowait()
                        yield _sse_event('progress', prog)
                    except _queue.Empty:
                        break

                scraped_data = await scrape_task
                scraped_data_cache[0] = scraped_data
                found[0] = len(scraped_data)
                elapsed = _time.time() - start_time

                scrape_stats = {
                    'slugs_scraped': total,
                    'profiles_found': found[0],
                    'success_rate': f'{found[0]/total*100:.1f}%' if total else '0%',
                    'elapsed_seconds': round(elapsed, 1),
                }

                # Final progress event
                yield _sse_event('progress', {
                    'completed': total,
                    'total': total,
                    'found': found[0],
                    'elapsed': round(elapsed, 1),
                })
        else:
            yield _sse_event('phase', {'phase': 'filtering'})

        # Phase: filtering
        yield _sse_event('phase', {'phase': 'filtering'})

        kept, removed, stats = run_filter_pipeline(
            records=records,
            scraped_data=scraped_data if scraped_data else None,
            date_range=date_range,
        )

        result = {
            'status': 'ok',
            'filename': file.filename,
            'scraping_enabled': scrape,
            'scrape_stats': scrape_stats,
            'total_records': stats.total,
            'kept_count': stats.kept,
            'removed_count': stats.removed,
            'cohort1_count': stats.cohort1,
            'cohort2_count': stats.cohort2,
            'removal_reasons': dict(stats.reasons.most_common(20)),
            'kept': kept,
            'removed': removed,
        }

        # Phase: done
        yield _sse_event('phase', {'phase': 'done'})
        yield _sse_event('done', result)

    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )


def _sse_event(event: str, data: dict) -> str:
    """Format a dict as an SSE event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.get("/presets")
async def filter_presets() -> dict[str, Any]:
    """Get available filter configurations."""
    return {
        "presets": [
            {
                "id": "full",
                "name": "Full Filter (Default)",
                "description": "All tiers: gambling, business, location, bio, slug, profile_name",
            },
            {
                "id": "light",
                "name": "Light Filter",
                "description": "Gambling + obvious business only (no bio/slug analysis)",
            },
            {
                "id": "gambling_only",
                "name": "Gambling Only",
                "description": "Remove only gambling/betting/fantasy accounts",
            },
        ],
    }
