# Adobe Stock AI Image Studio: Architecture & Technical Blueprint

## 1. Executive Summary & Vision

The **Adobe Stock AI Image Studio** is a localized, human-in-the-loop desktop web application engineered to streamline the end-to-end commercialization of generative AI raster images. 

Rather than relying on brittle vector-tracing algorithms or completely unmonitored mass-upload bots, this platform pairs **automated pre-flight quality control** and **multimodal metadata generation** with a **high-throughput manual inspection UI**.

```
┌───────────────────────────┐
│ Gemini / Midjourney / SD  │ (High-res / 2x-4x Upscaled Images)
└─────────────┬─────────────┘
              │ 1. Drag-and-Drop Batch Upload
              ▼
┌───────────────────────────┐
│ Next.js Local Frontend    │ ◄─── Real-time status, confidence badges,
└─────────────┬─────────────┘      reasoning breakdown, 1-click approvals
              │ 2. Multipart POST
              ▼
┌────────────────────────────────────────────────────────────────────────┐
│ FastAPI Local Backend                                                  │
│                                                                        │
│  [ Stage 1: Deterministic QC ]                                         │
│    • Resolution / Megapixel check ($MP \ge 4.0$, target $15-25\text{ MP}$)│
│    • Color space normalization (sRGB)                                  │
│    • Edge sharpness (Laplacian variance $\sigma^2 \ge 120$)            │
│    • OCR text scan (flags garbled AI pseudo-lettering)                 │
│                                                                        │
│  [ Stage 2: Multimodal Semantic QC (Gemini Flash) ]                    │
│    • Visual artifact audit (limbs, melted geometries, blur)           │
│    • IP & trademark blacklisting (logos, protected vehicles)           │
│    • Confidence score ($0.0 - 1.0$) assignment                        │
└─────────────────────┬──────────────────────────────────────────────────┘
                      │
                      │ 3. User Reviews & Clicks "Approve"
                      ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Packaging & Tagging Engine                                             │
│                                                                        │
│  [ Stage 3: Metadata Generation (Gemini Flash) ]                       │
│    • Commercial title generation ($\le 150$ characters, natural syntax)│
│    • 25–35 sorted, prioritized keywords (No spam, no format tags)      │
│                                                                        │
│  [ Stage 4: Metadata Injection (ExifTool) ]                            │
│    • Direct IPTC:ObjectName, IPTC:Caption, IPTC:Keywords injection    │
│    • Direct XMP:Title, XMP:Description, XMP:Subject embedding          │
│                                                                        │
│  [ Stage 5: Ready-to-Upload Pool ]                                     │
│    • Moved to `/storage/ready_to_upload/`                              │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Adobe Stock Commercial & Technical Baselines

To ensure near-$100\%$ acceptance and avoid contributor queue penalties, submissions must adhere to the following thresholds:

| Criterion | Adobe Stock Specification | Studio Enforcement Metric |
| :--- | :--- | :--- |
| **File Format** | JPEG (`.jpg`, `.jpeg`) | Strictly baseline RGB JPEG |
| **Minimum Resolution** | 4.0 Megapixels ($MP$) | $\ge 4.0\text{ MP}$ hard gate; $\ge 12.0\text{ MP}$ recommended |
| **Maximum File Size** | 45 MB | Compression quality adjusted to keep between 5 MB and 35 MB |
| **Color Space** | sRGB | Auto-converted if AdobeRGB or Display P3 |
| **Sharpness** | 100% zoom inspection standard | Laplacian variance filter $\sigma^2 \ge 120.0$ |
| **Text & Gibberish** | Unreadable text rejected immediately | OCR detection; reject if unindexed gibberish is present |
| **Generative AI Tagging** | Mandatory portal checkbox | Metadata flagged; batch ready for manual check in portal |
| **Queue Limit** | $\sim 50$ pending files for newer accounts | Batch packaging throttled to user-selected chunks (e.g., 50 files) |

---

## 3. System Architecture & Directory Structure

```
stock-studio/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── endpoints.py        # REST routes for upload, review, approval
│   │   ├── core/
│   │   │   ├── config.py           # Environment variables, file paths, thresholds
│   │   │   └── database.py         # SQLite engine and session factory
│   │   ├── models/
│   │   │   └── image_record.py     # SQLAlchemy ORM entity
│   │   ├── schemas/
│   │   │   └── payload.py          # Pydantic request/response schemas
│   │   └── services/
│   │       ├── qc_engine.py        # Heuristics (Laplacian, Pillow, OCR)
│   │       ├── gemini_service.py   # Gemini API client (Audit & Metadata)
│   │       └── exif_service.py     # ExifTool wrapper for IPTC embedding
│   ├── storage/
│   │   ├── inbox/                  # Newly uploaded raw AI images
│   │   ├── thumbnails/             # Web-optimized thumbnails for the Next.js UI
│   │   └── ready_to_upload/        # Final IPTC-tagged, verified JPEGs
│   ├── main.py                     # ASGI entry point
│   └── requirements.txt
│
└── frontend/
    ├── src/
    │   ├── app/
    │   │   ├── layout.tsx
    │   │   └── page.tsx            # Main review dashboard
    │   ├── components/
    │   │   ├── Dropzone.tsx        # File drag-and-drop uploader
    │   │   ├── ImageGrid.tsx       # Filterable candidate list (Passed/Flagged)
    │   │   ├── InspectionModal.tsx # 100% zoom inspector & failure audit list
    │   │   └── StatsBar.tsx        # Ingest queue counter and health metrics
    │   └── lib/
    │       └── api.ts              # Axios/Fetch client for FastAPI backend
    ├── package.json
    └── tailwind.config.js
```

---

## 4. Backend Implementation Details

### 4.1 Database Model (`backend/app/models/image_record.py`)

```python
from sqlalchemy import Column, Integer, String, Float, JSON, DateTime
from datetime import datetime
from app.core.database import Base

class ImageRecord(Base):
    __tablename__ = "image_records"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, unique=True, index=True)
    original_path = Column(String, nullable=False)
    thumbnail_path = Column(String, nullable=False)
    
    # State: PENDING -> AUDITING -> PASSED / FLAGGED -> APPROVED -> READY
    status = Column(String, default="PENDING", index=True)
    
    # Quantitative Scores
    megapixels = Column(Float, default=0.0)
    laplacian_variance = Column(Float, default=0.0)
    semantic_confidence = Column(Float, default=0.0)
    
    # Quality Control Diagnostics
    heuristic_breakdown = Column(JSON, default=dict)
    failure_reasons = Column(JSON, default=list)
    
    # Generated Metadata
    title = Column(String, nullable=True)
    keywords = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

---

### 4.2 Deterministic Quality Control Heuristics (`backend/app/services/qc_engine.py`)

Fast, zero-cost local heuristics run first to eliminate broken, blurry, or low-resolution renders before calling paid or rate-limited multimodal APIs.

$$\text{Laplacian Variance: } \sigma^2 = \frac{1}{N}\sum_{x,y} \left( \nabla^2 I(x, y) - \bar{\mu} \right)^2$$

```python
import cv2
from PIL import Image
from pathlib import Path
import pytesseract

def audit_technical_specs(image_path: Path) -> dict:
    reasons = []
    
    # 1. Dimension and Megapixel Audit
    with Image.open(image_path) as img:
        width, height = img.size
        color_mode = img.mode
        mp = (width * height) / 1_000_000.0
        
        if mp < 4.0:
            reasons.append(f"Resolution failed: {mp:.2f} MP is below the 4.0 MP minimum.")
        
        if color_mode not in ["RGB", "RGBA"]:
            reasons.append(f"Color mode failed: Expected RGB, encountered {color_mode}.")

    # 2. Laplacian Edge Sharpness Audit
    cv_img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if cv_img is None:
        return {"passed": False, "reasons": ["Unreadable image buffer."], "mp": 0, "variance": 0}
        
    variance = float(cv2.Laplacian(cv_img, cv2.CV_64F).var())
    if variance < 120.0:
        reasons.append(f"High-frequency sharpness low: Score {variance:.1f} (Threshold: 120.0). Image appears soft or poorly upscaled.")

    # 3. Gibberish Text Scan
    # Downscale for fast OCR reading
    small_cv = cv2.resize(cv_img, (1024, int(1024 * (height / width))))
    detected_text = pytesseract.image_to_string(small_cv, config="--psm 11").strip()
    
    # If text is detected, verify character structure
    if len(detected_text) > 4:
        # Check if words look like hallucinated gibberish (high consonant clumps or nonsensical tokens)
        words = [w for w in detected_text.split() if len(w) > 2]
        if words and any(len(set(w)) < len(w) * 0.4 for w in words):
            reasons.append("Gibberish or distorted AI pseudo-text detected in background.")

    return {
        "passed": len(reasons) == 0,
        "megapixels": round(mp, 2),
        "laplacian_variance": round(variance, 1),
        "reasons": reasons
    }
```

---

### 4.3 Semantic AI Auditor & Metadata Engine (`backend/app/services/gemini_service.py`)

Using **Gemini 2.5 Flash** for rapid image comprehension:

```python
import json
from pathlib import Path
from google import genai
from google.genai import types

client = genai.Client()

SEMANTIC_AUDIT_PROMPT = """
You are an expert commercial image reviewer for Adobe Stock.
Inspect this generative AI illustration/photo for rejection triggers.
Evaluate strictly on:
1. Anatomy defects: Extra/fused fingers, asymmetrical pupils, melting skin, unnatural joints.
2. AI artifacts: Disconnected geometry, nonsensical floating objects, smudged background patterns.
3. IP/Trademark: Famous logos (Apple, Nike, BMW), identifiable automotive signatures, or recognizable celebrity likenesses.

Output strict JSON:
{
  "pass": boolean,
  "confidence": float,  // 0.0 (unusable) to 1.0 (pristine stock quality)
  "issues": string[]    // Empty if pass is true, otherwise list specific reasons
}
"""

METADATA_GENERATION_PROMPT = """
You are a stock metadata and SEO specialist for Adobe Stock.
Analyze this image and return a JSON object:
{
  "title": "A natural, descriptive English sentence under 140 characters describing the subject and setting. Do not keyword-stuff.",
  "keywords": ["array of 25 to 35 concise, highly relevant keywords ordered from most important to least important"]
}

Strict Rules:
- Top 5 keywords MUST define the direct subject, action, and color palette.
- Do NOT include forbidden tags: 'AI', 'generative', 'stock', 'midjourney', 'illustration', 'image', 'nobody', 'copyspace'.
- No trademarked terms.
"""

def evaluate_semantics(image_path: Path) -> dict:
    with open(image_path, "rb") as f:
        image_bytes = f.read()

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            SEMANTIC_AUDIT_PROMPT,
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1
        )
    )
    return json.loads(response.text)

def generate_metadata(image_path: Path) -> dict:
    with open(image_path, "rb") as f:
        image_bytes = f.read()

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            METADATA_GENERATION_PROMPT,
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2
        )
    )
    return json.loads(response.text)
```

---

### 4.4 ExifTool IPTC Embedder (`backend/app/services/exif_service.py`)

Embedding tags directly into IPTC/XMP structures ensures Adobe Stock automatically indexes titles and keywords during manual drag-and-drop web uploads:

```python
import subprocess
from pathlib import Path

def embed_stock_metadata(target_image: Path, title: str, keywords: list[str]) -> bool:
    """
    Embeds metadata into the JPEG using ExifTool.
    Writes simultaneously to IPTC, XMP, and EXIF containers.
    """
    keyword_flags = []
    # Adobe Stock accepts up to 49 keywords; cap safely at 35
    for kw in keywords[:35]:
        keyword_flags.extend([
            f"-IPTC:Keywords={kw}",
            f"-XMP:Subject={kw}"
        ])

    cmd = [
        "exiftool",
        "-overwrite_original",
        f"-IPTC:ObjectName={title}",
        f"-IPTC:Caption-Abstract={title}",
        f"-XMP:Title={title}",
        f"-XMP:Description={title}",
        *keyword_flags,
        str(target_image.resolve())
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.returncode == 0
```

---

### 4.5 Orchestrator & Endpoints (`backend/app/api/endpoints.py`)

```python
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from pathlib import Path
import shutil
from PIL import Image

from app.core.database import get_db
from app.models.image_record import ImageRecord
from app.services.qc_engine import audit_technical_specs
from app.services.gemini_service import evaluate_semantics, generate_metadata
from app.services.exif_service import embed_stock_metadata

router = APIRouter()

INBOX_DIR = Path("./storage/inbox")
THUMB_DIR = Path("./storage/thumbnails")
READY_DIR = Path("./storage/ready_to_upload")

def generate_thumbnail(source: Path, dest: Path):
    with Image.open(source) as img:
        img.thumbnail((400, 400))
        img.save(dest, "JPEG", quality=80)

def run_background_audit(record_id: int, db_factory):
    db: Session = db_factory()
    record = db.query(ImageRecord).get(record_id)
    if not record:
        return

    record.status = "AUDITING"
    db.commit()

    # Step 1: Technical Heuristics
    file_path = Path(record.original_path)
    tech_results = audit_technical_specs(file_path)
    
    record.megapixels = tech_results["megapixels"]
    record.laplacian_variance = tech_results["laplacian_variance"]
    record.heuristic_breakdown = tech_results

    if not tech_results["passed"]:
        record.status = "FLAGGED"
        record.failure_reasons = tech_results["reasons"]
        record.semantic_confidence = 0.2
        db.commit()
        db.close()
        return

    # Step 2: Semantic Vision Audit
    try:
        sem_results = evaluate_semantics(file_path)
        record.semantic_confidence = sem_results.get("confidence", 0.0)
        
        if sem_results.get("pass") and sem_results.get("confidence", 0) >= 0.75:
            record.status = "PASSED"
            record.failure_reasons = []
        else:
            record.status = "FLAGGED"
            record.failure_reasons = sem_results.get("issues", ["Low semantic confidence score."])
    except Exception as e:
        record.status = "FLAGGED"
        record.failure_reasons = [f"Vision audit error: {str(e)}"]

    db.commit()
    db.close()

@router.post("/upload")
async def upload_batch(
    background_tasks: BackgroundTasks, 
    files: list[UploadFile] = File(...), 
    db: Session = Depends(get_db)
):
    created_records = []
    for file in files:
        file_path = INBOX_DIR / file.filename
        thumb_path = THUMB_DIR / f"thumb_{file.filename}"

        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        generate_thumbnail(file_path, thumb_path)

        record = ImageRecord(
            filename=file.filename,
            original_path=str(file_path.resolve()),
            thumbnail_path=str(thumb_path.resolve()),
            status="PENDING"
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        
        # Dispatch QC worker
        background_tasks.add_task(run_background_audit, record.id, get_db)
        created_records.append(record.id)

    return {"uploaded_count": len(created_records), "record_ids": created_records}

@router.post("/records/{record_id}/approve")
def approve_and_finalize(record_id: int, db: Session = Depends(get_db)):
    record = db.query(ImageRecord).get(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    source_path = Path(record.original_path)
    dest_path = READY_DIR / source_path.name

    # 1. Generate Metadata via Gemini
    meta = generate_metadata(source_path)
    record.title = meta["title"]
    record.keywords = meta["keywords"]

    # 2. Move file to Ready directory
    shutil.copyfile(source_path, dest_path)

    # 3. Embed IPTC/XMP tags directly
    success = embed_stock_metadata(dest_path, meta["title"], meta["keywords"])
    if not success:
        raise HTTPException(status_code=500, detail="Failed to embed IPTC metadata.")

    record.status = "READY"
    db.commit()
    return {"status": "READY", "title": record.title, "keywords_count": len(record.keywords)}
```

---

## 5. Frontend Implementation (Next.js Dashboard)

The Next.js client presents an operator review station designed to process 50 images in under 3 minutes.

### 5.1 Main Review Interface (`frontend/src/app/page.tsx`)

```tsx
'use client';

import React, { useState, useEffect } from 'react';
import axios from 'axios';
import Dropzone from '@/components/Dropzone';
import { CheckCircle2, AlertTriangle, ShieldCheck, XCircle, Sparkles } from 'lucide-react';

interface AssetRecord {
  id: number;
  filename: string;
  thumbnail_path: string;
  status: 'PENDING' | 'AUDITING' | 'PASSED' | 'FLAGGED' | 'READY';
  megapixels: number;
  laplacian_variance: number;
  semantic_confidence: number;
  failure_reasons: string[];
}

export default function Dashboard() {
  const [records, setRecords] = useState<AssetRecord[]>([]);
  const [activeFilter, setActiveFilter] = useState<'ALL' | 'FLAGGED' | 'PASSED' | 'READY'>('ALL');
  const [loading, setLoading] = useState(false);

  const fetchRecords = async () => {
    const res = await axios.get('http://localhost:8000/api/records');
    setRecords(res.data);
  };

  useEffect(() => {
    fetchRecords();
    const interval = setInterval(fetchRecords, 3000); // 3-second polling
    return () => clearInterval(interval);
  }, []);

  const handleApprove = async (id: number) => {
    setLoading(true);
    await axios.post(`http://localhost:8000/api/records/${id}/approve`);
    await fetchRecords();
    setLoading(false);
  };

  const handleApproveAllPassed = async () => {
    const passed = records.filter(r => r.status === 'PASSED');
    for (const item of passed) {
      await axios.post(`http://localhost:8000/api/records/${item.id}/approve`);
    }
    fetchRecords();
  };

  const filteredRecords = records.filter(r => {
    if (activeFilter === 'ALL') return true;
    return r.status === activeFilter;
  });

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100 p-8">
      {/* Header & Controls */}
      <header className="flex justify-between items-center pb-8 border-b border-zinc-800">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Adobe Stock AI Studio</h1>
          <p className="text-sm text-zinc-400">Automated QC, IPTC Embedding & Staging Gate</p>
        </div>

        <div className="flex items-center gap-4">
          <button 
            onClick={handleApproveAllPassed}
            className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm font-semibold transition"
          >
            <Sparkles className="w-4 h-4" />
            Batch Approve Passed ({records.filter(r => r.status === 'PASSED').length})
          </button>
        </div>
      </header>

      {/* Upload Zone */}
      <section className="my-8">
        <Dropzone onUploadComplete={fetchRecords} />
      </section>

      {/* Filter Tabs */}
      <div className="flex gap-4 mb-6">
        {(['ALL', 'PASSED', 'FLAGGED', 'READY'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveFilter(tab)}
            className={`px-3 py-1.5 rounded-md text-xs font-semibold uppercase tracking-wider transition ${
              activeFilter === tab ? 'bg-zinc-100 text-zinc-900' : 'bg-zinc-900 text-zinc-400 hover:text-zinc-200'
            }`}
          >
            {tab} ({records.filter(r => tab === 'ALL' ? true : r.status === tab).length})
          </button>
        ))}
      </div>

      {/* Inspection Card Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {filteredRecords.map(asset => (
          <div 
            key={asset.id} 
            className={`flex flex-col bg-zinc-900 border rounded-xl overflow-hidden transition ${
              asset.status === 'FLAGGED' ? 'border-amber-500/40 bg-amber-950/10' :
              asset.status === 'PASSED' ? 'border-emerald-500/30' : 
              asset.status === 'READY' ? 'border-blue-500/30' : 'border-zinc-800'
            }`}
          >
            <div className="relative aspect-square w-full bg-zinc-950">
              <img 
                src={`http://localhost:8000/thumbnails/thumb_${asset.filename}`} 
                alt={asset.filename}
                className="w-full h-full object-cover"
              />
              
              {/* Confidence Badge */}
              <div className="absolute top-2 right-2 flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold backdrop-blur-md bg-zinc-900/80 border border-zinc-700">
                {asset.status === 'PASSED' && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />}
                {asset.status === 'FLAGGED' && <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />}
                {asset.status === 'READY' && <ShieldCheck className="w-3.5 h-3.5 text-blue-400" />}
                <span>{Math.round(asset.semantic_confidence * 100)}%</span>
              </div>
            </div>

            <div className="p-4 flex-1 flex flex-col justify-between space-y-4">
              <div>
                <p className="text-xs font-mono text-zinc-400 truncate">{asset.filename}</p>
                <div className="flex gap-3 text-xs text-zinc-500 mt-1 font-mono">
                  <span>{asset.megapixels} MP</span>
                  <span>Var: {asset.laplacian_variance}</span>
                </div>
              </div>

              {/* Reasons list for Flagged Items */}
              {asset.failure_reasons && asset.failure_reasons.length > 0 && (
                <div className="bg-amber-950/30 border border-amber-800/40 rounded p-2.5 space-y-1">
                  <p className="text-[10px] font-bold text-amber-400 uppercase tracking-wider">QC Flags:</p>
                  <ul className="text-xs text-amber-200 list-disc pl-3.5 space-y-0.5">
                    {asset.failure_reasons.map((issue, idx) => (
                      <li key={idx}>{issue}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Action Buttons */}
              <div className="pt-2 border-t border-zinc-800 flex gap-2">
                {asset.status !== 'READY' ? (
                  <>
                    <button 
                      onClick={() => handleApprove(asset.id)}
                      disabled={loading}
                      className="flex-1 bg-zinc-100 hover:bg-white text-zinc-900 py-1.5 rounded-lg text-xs font-bold transition"
                    >
                      Approve & Tag
                    </button>
                  </>
                ) : (
                  <div className="w-full text-center py-1.5 text-xs font-semibold text-blue-400 bg-blue-950/20 rounded-lg">
                    Staged in Ready Pool
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
```

---

## 6. Execution & Deployment Workflow

### 6.1 Prerequisites
* **Python 3.11+**
* **Node.js 20+**
* **ExifTool** installed on system PATH (`brew install exiftool` or Windows binary)
* **Tesseract OCR** installed on system PATH
* **Gemini API Key** (`export GEMINI_API_KEY="your-key-here"`)

### 6.2 Starting the Environment

**Terminal 1: Backend**
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install fastapi uvicorn pillow opencv-python pytesseract google-genai sqlalchemy
uvicorn main:app --reload --port 8000
```

**Terminal 2: Frontend**
```bash
cd frontend
npm install
npm run dev
```

### 6.3 Daily Production Protocol

1. **Generation:** Download 50 high-resolution ($2\text{k}-4\text{k}$) images from Gemini Pro.
2. **Ingest:** Open `http://localhost:3000` and drag the 50 images into the Dropzone.
3. **Automated QC:** The Python backend runs Laplacian, OCR, and Gemini Flash audits concurrently in the background.
4. **Triage:**
   - Scan the **FLAGGED** tab. Discard images with distorted hands or messy artifacts.
   - For images that look visually great despite low Laplacian scores (e.g., intentional soft fog or bokeh), click **Approve & Tag** to override.
   - Click **Batch Approve Passed** to finalize all clean images.
5. **Auto-Tagging:** Gemini Flash creates contextual titles and prioritized tags, which ExifTool injects directly into the image files in `/storage/ready_to_upload/`.
6. **Stock Ingest:** Open Adobe Stock Contributor, drag the files from `ready_to_upload`, confirm the **Generative AI** checkbox, and submit.