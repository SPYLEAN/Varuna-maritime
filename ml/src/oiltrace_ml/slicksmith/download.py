"""
VARUNA — Slicksmith Dataset Downloader
Adapted from: Halyjo/slicksmith-ttom (src/slicksmith_ttom/download.py)
License: MIT (Copyright (c) 2025 Harald Lykke Joakimsen)
Commit SHA: 9ccd35df53568c7e64121a2ae7c855f4545396ba
"""

import os
from pathlib import Path
from typing import Optional
import requests

def download_file(url: str, dst_dir: str | Path, filename: Optional[str] = None, chunk_size: int = 8192) -> str:
    """Download a remote file into target directory with streaming chunks."""
    os.makedirs(dst_dir, exist_ok=True)
    if filename is None:
        filename = url.split("/")[-1]

    dst_path = os.path.join(dst_dir, filename)

    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dst_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)

    return dst_path
