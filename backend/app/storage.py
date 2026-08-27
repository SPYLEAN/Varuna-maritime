from __future__ import annotations
import hashlib
import json
from pathlib import Path
import uuid
from typing import List, Optional, Tuple


class JSONCaseStorage:
    def __init__(self, storage_dir: str | Path = "data/cases"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_case_path(self, case_id: str) -> Path:
        safe_id = Path(case_id).name
        return self.storage_dir / f"{safe_id}.json"

    def get_case_dir(self, case_id: str) -> Path:
        safe_id = Path(case_id).name
        c_dir = self.storage_dir / safe_id
        c_dir.mkdir(parents=True, exist_ok=True)
        return c_dir

    def get_case_evidence_dir(self, case_id: str) -> Path:
        e_dir = self.get_case_dir(case_id) / "evidence"
        e_dir.mkdir(parents=True, exist_ok=True)
        return e_dir

    def get_case_outputs_dir(self, case_id: str) -> Path:
        o_dir = self.get_case_dir(case_id) / "outputs"
        o_dir.mkdir(parents=True, exist_ok=True)
        return o_dir

    def save_case(self, case_dict: dict) -> dict:
        case_id = case_dict["case_id"]
        filepath = self._get_case_path(case_id)
        filepath.write_text(json.dumps(case_dict, indent=2), encoding="utf-8")
        return case_dict

    def get_case(self, case_id: str) -> Optional[dict]:
        filepath = self._get_case_path(case_id)
        if not filepath.exists() or not filepath.is_file():
            return None
        try:
            return json.loads(filepath.read_text(encoding="utf-8"))
        except Exception:
            return None

    def list_cases(self) -> List[dict]:
        cases = []
        for filepath in self.storage_dir.glob("*.json"):
            try:
                data = json.loads(filepath.read_text(encoding="utf-8"))
                cases.append(data)
            except Exception:
                continue
        cases.sort(key=lambda c: c.get("created_at", ""), reverse=True)
        return cases

    def save_evidence_file(self, case_id: str, original_filename: str, content_bytes: bytes) -> Tuple[str, int, str]:
        if not original_filename or not original_filename.strip():
            raise ValueError("Original filename cannot be empty")

        # Sanitize filename
        raw_name = Path(original_filename.strip()).name
        if not raw_name or raw_name in (".", "..") or "\x00" in raw_name:
            raise ValueError(f"Invalid or unsafe filename: {original_filename}")

        evidence_dir = self.get_case_evidence_dir(case_id)
        target_path = (evidence_dir / raw_name).resolve()

        # Strict path traversal check
        if not str(target_path).startswith(str(evidence_dir.resolve())):
            raise ValueError(f"Unsafe path traversal attempt in filename: {original_filename}")

        # Provenance protection: never overwrite existing evidence silently
        if target_path.exists():
            stem = target_path.stem
            suffix = target_path.suffix
            short_id = uuid.uuid4().hex[:6]
            target_path = evidence_dir / f"{stem}_{short_id}{suffix}"

        target_path.write_bytes(content_bytes)

        file_size = len(content_bytes)
        sha256_hex = hashlib.sha256(content_bytes).hexdigest()

        return str(target_path), file_size, sha256_hex


# Global default storage instance
storage = JSONCaseStorage()
