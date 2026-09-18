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


class SatelliteObservation(BaseModel):
    observation_id: str
    provider: str = "Copernicus Data Space Ecosystem"
    collection: str = "sentinel-1-grd"
    stac_item_id: str
    platform: Optional[str] = None
    constellation: Optional[str] = None
    datetime: Optional[str] = None
    start_datetime: Optional[str] = None
    end_datetime: Optional[str] = None
    instrument_mode: Optional[str] = None
    polarizations: List[str] = Field(default_factory=list)
    orbit_state: Optional[str] = None
    relative_orbit: Optional[int] = None
    absolute_orbit: Optional[int] = None
    product_type: Optional[str] = None
    geometry: Optional[Dict[str, Any]] = None
    bbox: Optional[List[float]] = None
    assets: Dict[str, Any] = Field(default_factory=dict)
    thumbnail_url: Optional[str] = None
    metadata_url: Optional[str] = None
    coverage_fraction: Optional[float] = None
    coverage_percent: Optional[float] = None
    attached_at: Optional[str] = None
    provenance: Optional[Dict[str, Any]] = None
    raw_properties: Dict[str, Any] = Field(default_factory=dict)


class SatelliteSearchRequest(BaseModel):
    start_datetime: str
    end_datetime: str
    limit: int = Field(default=20, ge=1, le=100)
    instrument_mode: Optional[str] = "IW"


class SatelliteSearchResponse(BaseModel):
    case_id: str
    provider: str = "Copernicus Data Space Ecosystem"
    collection: str = "sentinel-1-grd"
    query: Dict[str, Any]
    count: int
    results: List[SatelliteObservation]


class SatelliteAttachRequest(BaseModel):
    stac_item_id: str


class DataManifest(BaseModel):
    satellite_imagery: List[Any] = Field(default_factory=list)
    satellite_observations: List[SatelliteObservation] = Field(default_factory=list)
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
    region: Optional[str] = None
    incident_type: Optional[str] = None
    priority: Optional[str] = "NORMAL"
    aoi_geojson: Optional[Dict[str, Any]] = None


class Case(BaseModel):
    case_id: str
    name: str
    description: Optional[str] = None
    observation_timestamp: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    source: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    region: Optional[str] = None
    incident_type: Optional[str] = None
    priority: Optional[str] = "NORMAL"
    aoi_geojson: Optional[Dict[str, Any]] = None
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
