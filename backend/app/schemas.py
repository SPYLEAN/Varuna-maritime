from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class StatusEnum(str, Enum):
    NOT_STARTED = "not_started"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INSUFFICIENT_DATA = "insufficient_data"


class EvidenceType(str, Enum):
    SAR_IMAGE = "sar_image"
    OIL_MASK = "oil_mask"
    OCEAN_CURRENT = "ocean_current"
    WIND = "wind"
    WAVE = "wave"
    MET_OCEAN = "met_ocean"
    AIS = "ais"
    RESEARCH_NOTE = "research_note"
    OTHER = "other"


class AnalysisStatus(BaseModel):
    oil_detection: StatusEnum = StatusEnum.NOT_STARTED
    spill_geometry: StatusEnum = StatusEnum.NOT_STARTED
    hindcast: StatusEnum = StatusEnum.NOT_STARTED
    ais_correlation: StatusEnum = StatusEnum.NOT_STARTED
    attribution: StatusEnum = StatusEnum.NOT_STARTED


class MetOceanMetadata(BaseModel):
    provider: Optional[str] = None
    dataset_name: Optional[str] = None
    detected_variables: List[str] = Field(default_factory=list)
    detected_components: Dict[str, str] = Field(default_factory=dict)
    units: Dict[str, str] = Field(default_factory=dict)
    lat_min: Optional[float] = None
    lat_max: Optional[float] = None
    lon_min: Optional[float] = None
    lon_max: Optional[float] = None
    time_start_utc: Optional[str] = None
    time_end_utc: Optional[str] = None
    time_resolution_hours: Optional[float] = None
    spatial_resolution_deg: Optional[float] = None
    depth_m: Optional[float] = None
    crs: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class Evidence(BaseModel):
    evidence_id: str
    case_id: str
    evidence_type: EvidenceType
    original_filename: str
    stored_path: str
    mime_type: Optional[str] = None
    file_size: int
    sha256: str
    source: Optional[str] = None
    acquisition_timestamp: Optional[str] = None
    uploaded_at: str
    is_synthetic: bool = False
    is_human_verified: bool = False
    notes: Optional[str] = None
    metocean_metadata: Optional[MetOceanMetadata] = None


class AnalysisResult(BaseModel):
    analysis_id: str
    case_id: str
    module: str
    module_version: str = "1.0.0"
    input_evidence_ids: List[str] = Field(default_factory=list)
    input_hashes: List[str] = Field(default_factory=list)
    configuration: Dict[str, Any] = Field(default_factory=dict)
    started_at: str
    completed_at: Optional[str] = None
    status: StatusEnum = StatusEnum.NOT_STARTED
    result: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    uncertainty: Optional[float] = None
    warnings: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class AnalystQuestionCreate(BaseModel):
    question: str
    asked_by: Optional[str] = None


class AnalystQuestion(BaseModel):
    question_id: str
    question: str
    asked_by: Optional[str] = None
    created_at: str


class DataManifest(BaseModel):
    satellite_imagery: List[Any] = Field(default_factory=list)
    oil_masks: List[Any] = Field(default_factory=list)
    ais_data: List[Any] = Field(default_factory=list)
    met_ocean_data: List[Any] = Field(default_factory=list)
    research_notes: List[Any] = Field(default_factory=list)
    analyst_questions: List[AnalystQuestion] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)
    generated_analysis_results: List[AnalysisResult] = Field(default_factory=list)


class CaseCreate(BaseModel):
    name: str
    description: Optional[str] = None
    observation_timestamp: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    source: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class Case(BaseModel):
    case_id: str
    name: str
    description: Optional[str] = None
    observation_timestamp: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    source: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    created_at: str
    analysis_status: AnalysisStatus = Field(default_factory=AnalysisStatus)
    data_manifest: DataManifest = Field(default_factory=DataManifest)


class OilDetectionRequest(BaseModel):
    checkpoint_path: Optional[str] = None
    threshold: float = 0.5
    sar_evidence_id: Optional[str] = None


class SpillGeometryRequest(BaseModel):
    oil_detection_analysis_id: Optional[str] = None
    min_component_size_pixels: int = 1


class HindcastReadinessRequest(BaseModel):
    hindcast_hours: float = Field(default=12.0, gt=0, le=168.0)
    require_waves: bool = False
    spill_geometry_analysis_id: Optional[str] = None
