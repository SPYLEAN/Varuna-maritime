"""
SAMUDRANETRA — JOB MANAGER SERVICE
Thread-safe background job tracking engine for orchestrating live operational tasks:
SAR slick detection, OpenDrift hindcasts, OpenDrift forecasts, AIS ingestion, and vessel correlation.
"""

import time
import uuid
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

class JobState:
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"

class Job:
    def __init__(self, job_type: str, case_id: str, payload: Optional[Dict[str, Any]] = None):
        self.job_id = f"JOB_{uuid.uuid4().hex[:12].upper()}"
        self.job_type = job_type
        self.case_id = case_id
        self.status = JobState.QUEUED
        self.progress_pct = 0.0
        self.current_step = "INITIALIZING"
        self.logs: List[Dict[str, Any]] = []
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.created_at_utc = datetime.now(timezone.utc).isoformat() + "Z"
        self.updated_at_utc = self.created_at_utc
        self.payload = payload or {}

    def update_progress(self, pct: float, step: str, message: Optional[str] = None):
        self.progress_pct = min(100.0, max(0.0, pct))
        self.current_step = step
        self.updated_at_utc = datetime.now(timezone.utc).isoformat() + "Z"
        log_entry = {
            "timestamp_utc": self.updated_at_utc,
            "progress_pct": self.progress_pct,
            "step": step,
            "message": message or f"Step {step} in progress..."
        }
        self.logs.append(log_entry)

    def mark_complete(self, result: Dict[str, Any]):
        self.status = JobState.COMPLETE
        self.progress_pct = 100.0
        self.current_step = "COMPLETE"
        self.result = result
        self.updated_at_utc = datetime.now(timezone.utc).isoformat() + "Z"
        self.logs.append({
            "timestamp_utc": self.updated_at_utc,
            "progress_pct": 100.0,
            "step": "COMPLETE",
            "message": "Job finished successfully."
        })

    def mark_failed(self, error_message: str):
        self.status = JobState.FAILED
        self.error = error_message
        self.current_step = "FAILED"
        self.updated_at_utc = datetime.now(timezone.utc).isoformat() + "Z"
        self.logs.append({
            "timestamp_utc": self.updated_at_utc,
            "progress_pct": self.progress_pct,
            "step": "FAILED",
            "message": f"Error: {error_message}"
        })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "case_id": self.case_id,
            "status": self.status,
            "progress_pct": self.progress_pct,
            "current_step": self.current_step,
            "logs": self.logs,
            "result": self.result,
            "error": self.error,
            "created_at_utc": self.created_at_utc,
            "updated_at_utc": self.updated_at_utc
        }

class JobManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(JobManager, cls).__new__(cls)
                cls._instance.jobs = {}
            return cls._instance

    def create_job(self, job_type: str, case_id: str, payload: Optional[Dict[str, Any]] = None) -> Job:
        job = Job(job_type, case_id, payload)
        with self._lock:
            self.jobs[job.job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self.jobs.get(job_id)

    def list_jobs_for_case(self, case_id: str) -> List[Job]:
        with self._lock:
            return [j for j in self.jobs.values() if j.case_id == case_id]

job_manager = JobManager()
