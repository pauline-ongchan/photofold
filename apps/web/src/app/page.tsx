"use client";

import type { PrototypeAnalysis } from "@photofold/contracts/prototype-analysis";
import type { ErrorEnvelope } from "@photofold/contracts/prototype-error";
import type { PrototypeResult } from "@photofold/contracts/prototype-result";
import { useEffect, useMemo, useRef, useState } from "react";

type UploadItem = {
  id: string;
  file: File;
  previewUrl: string;
  width: number | null;
  height: number | null;
  decodeError: boolean;
};

type ViewMode = "compare" | "original" | "reconstruction" | "difference";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes.toLocaleString()} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = units[0];
  for (let index = 1; index < units.length && value >= 1024; index += 1) {
    value /= 1024;
    unit = units[index];
  }
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${unit}`;
}

function formatPercent(value: number): string {
  return `${Math.abs(value).toFixed(1)}%`;
}

function friendlyFallbackReason(reason: string | null | undefined): string {
  if (!reason) return "This photo did not match the rest closely enough, so it stays whole.";
  const normalized = reason.toLowerCase();
  if (normalized.includes("alignment") || normalized.includes("inlier") || normalized.includes("overlap")) {
    return "This photo did not line up closely enough with the others, so it stays whole to protect quality.";
  }
  return "This photo was not a close enough match, so it stays whole to protect quality.";
}

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  return Boolean(
    value &&
      typeof value === "object" &&
      "error" in value &&
      value.error &&
      typeof value.error === "object" &&
      "message" in value.error,
  );
}

async function responseError(response: Response): Promise<ErrorEnvelope> {
  try {
    const payload: unknown = await response.json();
    if (isErrorEnvelope(payload)) return payload;
  } catch {
    // Fall through to the stable browser-side transport error.
  }
  return {
    error: {
      code: "PROCESSOR_FAILED",
      message: `The local processor returned HTTP ${response.status}.`,
      stage: "service",
      frame_indices: [],
      retryable: false,
      debug: null,
    },
  };
}

function probeImage(item: UploadItem, update: (item: UploadItem) => void) {
  const image = new Image();
  image.onload = () => {
    update({ ...item, width: image.naturalWidth, height: image.naturalHeight, decodeError: false });
  };
  image.onerror = () => update({ ...item, decodeError: true });
  image.src = item.previewUrl;
}

export default function Home() {
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [analysis, setAnalysis] = useState<PrototypeAnalysis | null>(null);
  const [result, setResult] = useState<PrototypeResult | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [busy, setBusy] = useState<"analyzing" | "folding" | null>(null);
  const [error, setError] = useState<ErrorEnvelope | null>(null);
  const [dragging, setDragging] = useState(false);
  const [selectedFrame, setSelectedFrame] = useState(0);
  const [viewMode, setViewMode] = useState<ViewMode>("compare");
  const [comparison, setComparison] = useState(50);
  const [zoom, setZoom] = useState(1);
  const inputRef = useRef<HTMLInputElement>(null);
  const uploadRef = useRef<UploadItem[]>([]);

  useEffect(() => {
    uploadRef.current = uploads;
  }, [uploads]);

  useEffect(
    () => () => {
      uploadRef.current.forEach((item) => URL.revokeObjectURL(item.previewUrl));
    },
    [],
  );

  const originalTotal = useMemo(
    () => uploads.reduce((total, item) => total + item.file.size, 0),
    [uploads],
  );
  const dimensionsReady = uploads.every((item) => item.decodeError || item.width !== null);
  const canAnalyze = uploads.length >= 5 && uploads.length <= 20 && dimensionsReady && !busy;

  function addFiles(files: File[]) {
    if (analysis || result || busy) return;
    const available = Math.max(0, 20 - uploads.length);
    const items = files.slice(0, available).map((file) => ({
      id: crypto.randomUUID(),
      file,
      previewUrl: URL.createObjectURL(file),
      width: null,
      height: null,
      decodeError: false,
    }));
    setUploads((current) => [...current, ...items]);
    for (const item of items) {
      probeImage(item, (updated) =>
        setUploads((current) => current.map((candidate) => (candidate.id === item.id ? updated : candidate))),
      );
    }
  }

  function removeUpload(id: string) {
    setUploads((current) => {
      const item = current.find((candidate) => candidate.id === id);
      if (item) URL.revokeObjectURL(item.previewUrl);
      return current.filter((candidate) => candidate.id !== id);
    });
  }

  function reset() {
    uploads.forEach((item) => URL.revokeObjectURL(item.previewUrl));
    setUploads([]);
    setAnalysis(null);
    setResult(null);
    setRunId(null);
    setBusy(null);
    setError(null);
    setSelectedFrame(0);
    setViewMode("compare");
    setComparison(50);
    setZoom(1);
    if (inputRef.current) inputRef.current.value = "";
  }

  async function analyze() {
    if (!canAnalyze) return;
    setError(null);
    setBusy("analyzing");
    const form = new FormData();
    uploads.forEach((item) => form.append("files", item.file));
    try {
      const response = await fetch("/api/prototype/analyze", { method: "POST", body: form });
      if (!response.ok) throw await responseError(response);
      const payload = (await response.json()) as { runId: string; analysis: PrototypeAnalysis };
      setRunId(payload.runId);
      setAnalysis(payload.analysis);
    } catch (caught) {
      setError(isErrorEnvelope(caught) ? caught : {
        error: {
          code: "PROCESSOR_FAILED",
          message: caught instanceof Error ? caught.message : "The analysis request failed.",
          stage: "service",
          frame_indices: [],
          retryable: false,
          debug: null,
        },
      });
    } finally {
      setBusy(null);
    }
  }

  async function fold() {
    if (!runId || analysis?.status !== "analyzed_foldable") return;
    setError(null);
    setBusy("folding");
    try {
      const response = await fetch(`/api/prototype/runs/${runId}/fold`, { method: "POST" });
      if (!response.ok) throw await responseError(response);
      const payload = (await response.json()) as { runId: string; result: PrototypeResult };
      setResult(payload.result);
      setSelectedFrame(payload.result.reference_frame_index ?? 0);
    } catch (caught) {
      setError(isErrorEnvelope(caught) ? caught : {
        error: {
          code: "PROCESSOR_FAILED",
          message: caught instanceof Error ? caught.message : "The fold request failed.",
          stage: "service",
          frame_indices: [],
          retryable: false,
          debug: null,
        },
      });
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="min-h-screen bg-[#f3f0e8] px-4 py-6 text-[#17211b] sm:px-8 sm:py-10">
      <div className="mx-auto max-w-7xl">
        <Header onReset={reset} hasRun={uploads.length > 0} />

        <div className="mt-7 grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
          <div className="min-w-0 space-y-5">
            {!analysis && !result && (
              <UploadStep
                uploads={uploads}
                total={originalTotal}
                dragging={dragging}
                busy={busy === "analyzing"}
                canAnalyze={canAnalyze}
                inputRef={inputRef}
                onFiles={addFiles}
                onRemove={removeUpload}
                onAnalyze={analyze}
                setDragging={setDragging}
              />
            )}

            {analysis && !result && (
              <AnalysisStep analysis={analysis} busy={busy === "folding"} onFold={fold} />
            )}

            {result && runId && (
              <ResultsStep
                result={result}
                runId={runId}
                selectedFrame={selectedFrame}
                setSelectedFrame={setSelectedFrame}
                viewMode={viewMode}
                setViewMode={setViewMode}
                comparison={comparison}
                setComparison={setComparison}
                zoom={zoom}
                setZoom={setZoom}
              />
            )}

            {error && <ErrorPanel error={error} />}
          </div>

          <WorkflowRail analysis={analysis} result={result} busy={busy} uploadCount={uploads.length} />
        </div>
      </div>
    </main>
  );
}

function Header({ onReset, hasRun }: { onReset: () => void; hasRun: boolean }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-5 border-b border-[#17211b]/15 pb-6">
      <div className="max-w-3xl">
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.22em] text-[#496151]">
          Private preview · Photos stay on this computer
        </p>
        <h1 className="mt-3 text-5xl font-semibold tracking-[-0.055em] sm:text-7xl">PhotoFold</h1>
        <p className="mt-3 text-xl font-medium text-[#35483b]">Keep every shot. Use less space.</p>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-[#607066]">
          PhotoFold stores the shared scene once while keeping every photo.
        </p>
      </div>
      {hasRun && (
        <button className="button-secondary" type="button" onClick={onReset}>
          Start a new moment
        </button>
      )}
    </header>
  );
}

type UploadStepProps = {
  uploads: UploadItem[];
  total: number;
  dragging: boolean;
  busy: boolean;
  canAnalyze: boolean;
  inputRef: React.RefObject<HTMLInputElement | null>;
  onFiles: (files: File[]) => void;
  onRemove: (id: string) => void;
  onAnalyze: () => void;
  setDragging: (value: boolean) => void;
};

function UploadStep({
  uploads,
  total,
  dragging,
  busy,
  canAnalyze,
  inputRef,
  onFiles,
  onRemove,
  onAnalyze,
  setDragging,
}: UploadStepProps) {
  return (
    <section className="panel" aria-labelledby="upload-heading">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Step 1 of 4 · Choose</p>
          <h2 id="upload-heading" className="section-title">Choose photos from one moment</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[#607066]">
            Choose 5–20 photos of the same scene. Bursts work best.
          </p>
        </div>
        <div className="text-right">
          <p className="font-mono text-xs text-[#607066]">{uploads.length} / 20 photos</p>
          <p className="mt-1 text-lg font-semibold">{formatBytes(total)}</p>
        </div>
      </div>

      <div
        className={`drop-zone ${dragging ? "drop-zone-active" : ""}`}
        onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => { if (event.currentTarget === event.target) setDragging(false); }}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          onFiles(Array.from(event.dataTransfer.files));
        }}
      >
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-[#dfe9df] text-2xl">＋</div>
        <p className="mt-4 font-semibold">Drop your photos here</p>
        <p className="mt-1 text-sm text-[#607066]">JPEG, PNG, or WebP</p>
        <p className="mt-1 text-xs text-[#738077]">Different sizes are safe, but may save less space.</p>
        <button className="button-secondary mt-5" type="button" onClick={() => inputRef.current?.click()}>
          Choose photos
        </button>
        <input
          ref={inputRef}
          className="sr-only"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          onChange={(event) => onFiles(Array.from(event.target.files ?? []))}
        />
      </div>

      {uploads.length > 0 && (
        <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid="upload-list">
          {uploads.map((item, index) => (
            <article className="overflow-hidden rounded-2xl border border-[#17211b]/10 bg-white" key={item.id}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img className="h-40 w-full bg-[#e7e3d8] object-cover" src={item.previewUrl} alt="" />
              <div className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-[#728077]">PHOTO {String(index + 1).padStart(2, "0")}</p>
                    <p className="mt-1 truncate font-medium" title={item.file.name}>{item.file.name}</p>
                  </div>
                  <button className="remove-button" type="button" onClick={() => onRemove(item.id)} aria-label={`Remove ${item.file.name}`}>×</button>
                </div>
                <div className="mt-3 flex justify-between font-mono text-xs text-[#607066]">
                  <span>{formatBytes(item.file.size)}</span>
                  <span>{item.decodeError ? "Unreadable" : item.width ? `${item.width}×${item.height}` : "Reading…"}</span>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}

      <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-[#17211b]/10 pt-5">
        <p className="text-sm text-[#607066]">
          {uploads.length < 5 ? `${5 - uploads.length} more photo${5 - uploads.length === 1 ? "" : "s"} needed` : "Ready to check this set"}
        </p>
        <button className="button-primary" type="button" disabled={!canAnalyze} onClick={onAnalyze}>
          {busy ? "Checking your photos…" : "Check these photos"}
        </button>
      </div>
    </section>
  );
}

function AnalysisStep({ analysis, busy, onFold }: { analysis: PrototypeAnalysis; busy: boolean; onFold: () => void }) {
  const reference = analysis.source_frames.find((frame) => frame.index === analysis.reference_frame_index);
  const nonIdentity = analysis.alignment.filter(
    (item) => item.type !== null && item.type !== "identity" && item.inlier_ratio !== null,
  );
  const meanInlier = nonIdentity.length
    ? nonIdentity.reduce((sum, item) => sum + (item.inlier_ratio ?? 0), 0) / nonIdentity.length
    : 1;
  const measuredOverlap = nonIdentity.flatMap((item) => item.valid_overlap == null ? [] : [item.valid_overlap]);
  const minimumOverlap = measuredOverlap.length ? Math.min(...measuredOverlap) : 1;
  const strategyMessage = analysis.strategy === "shared_scene"
    ? `All ${analysis.shared_frame_count} photos can share space.`
    : analysis.strategy === "hybrid"
      ? `${analysis.shared_frame_count} photos can share space; ${analysis.fallback_frame_count} will stay whole.`
      : "These photos are too different to share safely, so each will stay whole.";
  const analysisTitle = analysis.strategy === "shared_scene"
    ? "These photos are a strong match"
    : analysis.strategy === "hybrid"
      ? "Most of these photos can share space"
      : "These photos are safer kept whole";
  return (
    <section className="panel" aria-labelledby="analysis-heading">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Step 2 of 4 · Check</p>
          <h2 id="analysis-heading" className="section-title">{analysisTitle}</h2>
        </div>
        <StatusBadge status={analysis.strategy} label="Ready to create" />
      </div>

      <p className="mb-5 rounded-2xl bg-[#eef2e9] px-5 py-4 font-semibold">{strategyMessage}</p>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Metric label="Photos selected" value={`${analysis.source_frames.length}`} description="Files ready to process." />
        <Metric label="Photos that can share space" value={`${analysis.shared_frame_count}`} description="Reuse one copy of the scene." />
        <Metric label="Photos kept whole" value={`${analysis.fallback_frame_count}`} description="Stored separately for quality." />
        <Metric label="Current size" value={formatBytes(analysis.original_total_bytes)} description="Combined upload size." />
        <Metric label="Working image size" value={analysis.normalized_dimensions ? `${analysis.normalized_dimensions.width}×${analysis.normalized_dimensions.height}` : "Original size"} description="Shared working dimensions." />
        <Metric label="Base photo" value={reference ? `${reference.index + 1} · ${reference.original_filename}` : "None needed"} description="Starting point for shared photos." />
      </div>

      <div className="mt-5 rounded-2xl border border-[#17211b]/10 p-5">
        <p className="font-semibold">How each photo will be stored</p>
        <p className="mt-1 text-sm leading-6 text-[#607066]">Shared photos reuse the scene; others stay whole.</p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {analysis.source_frames.map((source) => {
            const disposition = analysis.frame_dispositions[source.index];
            const fallback = disposition.storage_mode === "independent_source";
            return (
              <div className="rounded-xl bg-[#f7f5ef] p-3 text-sm" key={source.index}>
                <div className="flex items-center justify-between gap-3">
                  <span className="truncate font-medium">{source.index + 1} · {source.original_filename}</span>
                  <span className={`status-pill ${fallback ? "status-warning" : "status-positive"}`}>
                    {fallback ? "Kept whole" : "Shares space"}
                  </span>
                </div>
                <p className="mt-1 text-xs text-[#607066]">
                  {fallback ? friendlyFallbackReason(disposition.fallback_reason) : "Stores only what changed."} · {source.width}×{source.height}
                </p>
              </div>
            );
          })}
        </div>
      </div>

      <details className="explanation-details mt-5">
        <summary>See how PhotoFold made this decision</summary>
        <p className="mt-3 text-sm leading-6 text-[#607066]">PhotoFold looks for the same visual details in each photo and checks how much of the scene overlaps. These measurements help it avoid forcing unlike photos together.</p>
        <dl className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <DataTerm label="Base photo fit" value={analysis.reference_score?.toFixed(3) ?? "Not available"} description="How suitable the chosen base photo is for the full set; higher is better." />
          <DataTerm label="Matching-detail confidence" value={`${(meanInlier * 100).toFixed(1)}%`} description="The average share of matched details that agree on how the camera moved." />
          <DataTerm label="Smallest shared area" value={`${(minimumOverlap * 100).toFixed(1)}%`} description="The least scene overlap found among photos that will share space." />
          <DataTerm label="Positioning tolerance" value={`${analysis.alignment_measurement.max_median_reprojection_error.toFixed(2)} pixels`} description="The maximum allowed mismatch on the smaller checking image." />
          <DataTerm label="Checking image size" value={`Up to ${analysis.alignment_measurement.analysis_max_dimension}px`} description="Photos are temporarily scaled down to make this first check faster." />
        </dl>
      </details>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-[#17211b]/10 pt-5">
        <p className="max-w-xl text-sm leading-6 text-[#607066]">Next, PhotoFold rebuilds every photo and checks size and quality.</p>
        <button className="button-primary" disabled={analysis.status !== "analyzed_foldable" || busy} type="button" onClick={onFold}>
          {busy ? "Creating and checking your collection…" : "Create PhotoFold collection"}
        </button>
      </div>
    </section>
  );
}

type ResultsStepProps = {
  result: PrototypeResult;
  runId: string;
  selectedFrame: number;
  setSelectedFrame: (value: number) => void;
  viewMode: ViewMode;
  setViewMode: (value: ViewMode) => void;
  comparison: number;
  setComparison: (value: number) => void;
  zoom: number;
  setZoom: (value: number) => void;
};

function ResultsStep(props: ResultsStepProps) {
  const { result, runId } = props;
  const frame = result.frames[props.selectedFrame] ?? result.frames[0];
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [panning, setPanning] = useState(false);
  const canvasRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);
  const base = `/api/prototype/runs/${runId}/frames/${frame.index}`;
  const successful = result.status === "complete";
  const statusTitle = result.status === "complete"
    ? "Your smaller photo collection is ready"
    : result.status === "complete_no_savings"
      ? "Your collection is ready, but it is not smaller"
      : result.status === "failed_quality"
        ? "Your photos were rebuilt, but quality was below our target"
        : "We could not finish this collection";
  const statusMessage = result.status === "complete"
    ? "Every photo passed the quality check and the collection is smaller."
    : result.status === "complete_no_savings"
      ? "Quality passed, but this collection is larger than your uploads."
      : result.status === "failed_quality"
        ? "At least one photo missed the quality target. Compare it before downloading."
        : "PhotoFold could not finish. See the error below.";

  function resetPan() {
    setPan({ x: 0, y: 0 });
    dragRef.current = null;
    setPanning(false);
  }

  function setViewerZoom(value: number) {
    resetPan();
    props.setZoom(value);
  }

  function constrainPan(x: number, y: number) {
    const canvas = canvasRef.current;
    if (!canvas || props.zoom <= 1) return { x: 0, y: 0 };

    const viewportWidth = canvas.clientWidth;
    const viewportHeight = canvas.clientHeight;
    const imageAspect = frame.width / frame.height;
    const viewportAspect = viewportWidth / viewportHeight;
    const fittedWidth = viewportAspect > imageAspect ? viewportHeight * imageAspect : viewportWidth;
    const fittedHeight = viewportAspect > imageAspect ? viewportHeight : viewportWidth / imageAspect;
    const maxX = Math.max(0, (fittedWidth * props.zoom - viewportWidth) / 2);
    const maxY = Math.max(0, (fittedHeight * props.zoom - viewportHeight) / 2);

    return {
      x: Math.max(-maxX, Math.min(maxX, x)),
      y: Math.max(-maxY, Math.min(maxY, y)),
    };
  }

  function beginPan(event: React.PointerEvent<HTMLDivElement>) {
    if (props.zoom <= 1) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: pan.x,
      originY: pan.y,
    };
    setPanning(true);
  }

  function movePan(event: React.PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    setPan(constrainPan(
      drag.originX + event.clientX - drag.startX,
      drag.originY + event.clientY - drag.startY,
    ));
  }

  function endPan(event: React.PointerEvent<HTMLDivElement>) {
    if (dragRef.current?.pointerId !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    dragRef.current = null;
    setPanning(false);
  }

  return (
    <div className="space-y-5">
      <section className="panel" aria-labelledby="results-heading">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Step 3 of 4 · Results</p>
            <h2 id="results-heading" className="section-title">{statusTitle}</h2>
          </div>
          <StatusBadge status={result.status} />
        </div>

        <p className="mb-5 max-w-3xl text-sm leading-6 text-[#607066]">{statusMessage}</p>

        {result.storage && result.quality && result.package_contents ? (
          <>
            <p className="mb-5 rounded-2xl bg-[#eef2e9] px-5 py-4 text-sm leading-6 text-[#526258]">
              <strong className="text-[#17211b]">How it was stored:</strong> {result.shared_frame_count} sharing space · {result.fallback_frame_count} kept whole
            </p>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Metric label="Original photos" value={formatBytes(result.storage.original_total_bytes)} description="Uploaded file size." />
              <Metric label="PhotoFold collection" value={formatBytes(result.storage.package_total_bytes)} description="Download size." />
              <Metric
                label={successful ? "Space saved" : "Size difference"}
                value={successful ? `${formatBytes(result.storage.bytes_saved)} · ${formatPercent(result.storage.percent_saved)}` : `${formatBytes(Math.abs(result.storage.byte_delta))} ${result.storage.byte_delta < 0 ? "larger" : "smaller"}`}
                description="Compared with your uploads."
                tone={successful ? "positive" : "neutral"}
              />
              <Metric label="Visual match" value={`${result.quality.mean_ssim.toFixed(4)} avg · ${result.quality.minimum_ssim.toFixed(4)} lowest`} description="Closer to 1 is better." />
            </div>

            <div className="mt-5 grid gap-3 lg:grid-cols-2">
              <div className="explanation-card">
                <p className="font-semibold text-[#17211b]">What does SSIM mean?</p>
                <p className="mt-2 text-sm leading-6 text-[#607066]">
                  SSIM (<strong className="text-[#35483b]">Structural Similarity Index</strong>) compares structure, contrast, and detail. 1.000 is a perfect measured match; higher is better.
                </p>
                <p className="mt-2 text-xs leading-5 text-[#738077]">Average covers the set; lowest flags the weakest photo. Always inspect the images.</p>
              </div>
              <div className="explanation-card">
                <p className="font-semibold text-[#17211b]">Did the quality check pass?</p>
                <p className="mt-2 text-sm leading-6 text-[#607066]">
                  Targets: <strong className="text-[#35483b]">{result.quality.min_mean_threshold.toFixed(2)}</strong> average and <strong className="text-[#35483b]">{result.quality.min_per_frame_threshold.toFixed(2)}</strong> for every photo.
                </p>
                <p className={`mt-3 text-sm font-semibold ${result.quality.threshold_pass ? "text-[#215f36]" : "text-[#8b2f20]"}`}>
                  {result.quality.threshold_pass ? "✓ This collection passed both checks." : "This collection did not pass both checks."}
                </p>
              </div>
            </div>

            <details className="explanation-details mt-4">
              <summary>See collection and integrity details</summary>
              <dl className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <DataTerm label="Photos rebuilt" value={`${result.reconstructed_frame_count}`} description="Photos successfully recreated from this collection." />
                <DataTerm label="Files inside collection" value={`${result.package_contents.member_count}`} description="All images, change data, and instructions stored in the .photofold file." />
                <DataTerm label="Changed areas stored" value={`${result.package_contents.patch_count}`} description="Small regions saved separately because they differ from the shared scene." />
                <DataTerm label="Photos kept whole" value={`${result.package_contents.independent_source_count}`} description="Photos stored independently because sharing was not a safe fit." />
                <DataTerm label="Integrity fingerprint" value={`${result.storage.package_sha256.slice(0, 12)}…`} description="A SHA-256 fingerprint used to confirm the downloaded file has not changed or become corrupted." />
              </dl>
            </details>
          </>
        ) : result.error ? <ErrorPanel error={{ error: result.error }} nested /> : null}
      </section>

      {frame.reconstructed && (
        <section className="panel" aria-labelledby="viewer-heading">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Step 4 of 4 · Compare</p>
              <h2 id="viewer-heading" className="section-title">Compare photo {frame.index + 1} · {frame.original_filename}</h2>
              <p className="mt-1 text-sm text-[#607066]">
                Visual match <strong className="text-[#35483b]">{frame.ssim?.toFixed(4)}</strong> · {frame.storage_mode === "independent_source" ? "Kept whole" : "Shares space"}{frame.storage_mode !== "independent_source" ? ` · ${frame.patch_count} changed area${frame.patch_count === 1 ? "" : "s"} preserved` : ""}
              </p>
              {frame.fallback_reason && <p className="mt-2 text-sm text-[#8a5a20]">{friendlyFallbackReason(frame.fallback_reason)}</p>}
            </div>
            <div className="flex flex-wrap gap-2">
              <a className="button-primary" href={`${base}/export`}>Save this rebuilt photo</a>
              <a className="button-secondary" href={`/api/prototype/runs/${runId}/bundle`}>Download collection</a>
            </div>
          </div>
          <p className="mb-4 rounded-xl bg-[#f3f0e8] px-4 py-3 text-xs leading-5 text-[#607066]">
            A <strong className="text-[#35483b]">.photofold file</strong> holds the full set and needs PhotoFold to export photos.
          </p>

          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#17211b]/10 pb-4">
            <div className="flex flex-wrap gap-2" role="group" aria-label="Viewer mode">
              {(["compare", "original", "reconstruction", "difference"] as ViewMode[]).map((mode) => (
                <button className={`view-tab ${props.viewMode === mode ? "view-tab-active" : ""}`} type="button" key={mode} onClick={() => props.setViewMode(mode)}>
                  {mode === "difference" ? "Change heatmap" : mode === "reconstruction" ? "Rebuilt photo" : mode[0].toUpperCase() + mode.slice(1)}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-3">
              {props.zoom > 1 && (
                <button className="view-reset-button" type="button" onClick={() => setViewerZoom(1)}>
                  Fit
                </button>
              )}
              <label className="flex items-center gap-3 text-xs font-semibold uppercase tracking-[0.12em] text-[#607066]">
                Zoom {zoomLabel(props.zoom)}
                <input aria-label="Zoom" type="range" min="1" max="3" step="0.25" value={props.zoom} onChange={(event) => setViewerZoom(Number(event.target.value))} />
              </label>
            </div>
          </div>

          <ViewerGuide mode={props.viewMode} />

          {props.viewMode === "compare" && (
            <label className="mt-4 flex items-center gap-3 text-xs font-semibold text-[#607066]">
              Original side {props.comparison}%
              <input className="flex-1" aria-label="Comparison position" type="range" min="0" max="100" value={props.comparison} onChange={(event) => props.setComparison(Number(event.target.value))} />
              Rebuilt side
            </label>
          )}

          <div
            className={`viewer-stage mt-4 ${props.zoom > 1 ? "viewer-stage-pannable" : ""} ${panning ? "viewer-stage-panning" : ""}`}
            data-testid="frame-viewer"
            aria-label={props.zoom > 1 ? "Photo viewer. Drag to pan." : "Photo viewer"}
            onPointerDown={beginPan}
            onPointerMove={movePan}
            onPointerUp={endPan}
            onPointerCancel={endPan}
          >
            <div
              ref={canvasRef}
              className={`viewer-canvas ${panning ? "viewer-canvas-panning" : ""}`}
              style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${props.zoom})` }}
            >
              {props.viewMode === "compare" ? (
                <>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={`${base}/reconstruction`} alt={`Reconstruction of ${frame.original_filename}`} />
                  <div className="viewer-overlay" style={{ clipPath: `inset(0 ${100 - props.comparison}% 0 0)` }}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={`${base}/original`} alt={`Original ${frame.original_filename}`} />
                  </div>
                  <div className="comparison-line" style={{ left: `${props.comparison}%` }} />
                </>
              ) : (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={`${base}/${props.viewMode}`} alt={`${props.viewMode} for ${frame.original_filename}`} />
              )}
            </div>
          </div>

          <div className="mt-4 flex gap-2 overflow-x-auto pb-2" aria-label="Frame browser">
            {result.frames.map((item) => (
              <button
                className={`frame-selector ${item.index === frame.index ? "frame-selector-active" : ""}`}
                type="button"
                key={item.index}
                onClick={() => {
                  resetPan();
                  props.setSelectedFrame(item.index);
                }}
              >
                <span>Photo {item.index + 1}</span>
                <strong>{item.storage_mode === "independent_source" ? "Kept whole" : "Shares space"} · match {item.ssim?.toFixed(4) ?? "—"}</strong>
              </button>
            ))}
          </div>
        </section>
      )}

      <details className="explanation-details">
        <summary>About this storage comparison and technical notes</summary>
        <p className="mt-3 text-sm leading-6 text-[#607066]">The size comparison uses the exact files you uploaded. It tells you whether this collection is smaller than those files; it does not compare every possible photo format or compression setting during this quick interactive run.</p>
        {result.warnings.length > 0 && <ul className="mt-3 space-y-1 text-sm leading-6 text-[#607066]">{result.warnings.map((warning) => <li key={warning}>— {warning}</li>)}</ul>}
      </details>
    </div>
  );
}

function WorkflowRail({ analysis, result, busy, uploadCount }: { analysis: PrototypeAnalysis | null; result: PrototypeResult | null; busy: "analyzing" | "folding" | null; uploadCount: number }) {
  const steps = [
    { label: "Choose photos", detail: uploadCount ? `${uploadCount} selected` : "5–20 from one moment", state: busy === "analyzing" || analysis || result ? "complete" : "current" },
    { label: "Check the match", detail: analysis ? "Check complete" : busy === "analyzing" ? "Checking now" : "Find what can be shared", state: busy === "folding" || result ? "complete" : busy === "analyzing" || analysis ? "current" : "upcoming" },
    { label: "Create collection", detail: result ? "Collection created" : busy === "folding" ? "Creating now" : "Rebuild and measure", state: result ? "complete" : busy === "folding" ? "current" : "upcoming" },
    { label: "Compare & download", detail: result?.reconstructed_frame_count ? `${result.reconstructed_frame_count} photos ready` : "Review every photo", state: result ? "current" : "upcoming" },
  ];
  return (
    <aside className="h-fit rounded-3xl border border-[#17211b]/10 bg-[#17211b] p-6 text-[#f3f0e8] lg:sticky lg:top-6">
      <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-[#b7c7ba]">How PhotoFold works</p>
      <ol className="mt-6 space-y-5">
        {steps.map((step, index) => (
          <li className="flex gap-3" key={step.label}>
            <span className={`step-number ${step.state === "current" ? "step-number-active" : step.state === "complete" ? "step-number-complete" : ""}`}>
              {step.state === "complete" ? "✓" : index + 1}
            </span>
            <div><p className="font-semibold">{step.label}</p><p className="mt-1 text-xs capitalize text-[#afbbb2]">{step.detail}</p></div>
          </li>
        ))}
      </ol>
      <div className="mt-7 border-t border-white/15 pt-5 text-xs leading-5 text-[#afbbb2]">
        <p className="font-semibold text-[#d9e5db]">Private by design</p>
        <p className="mt-2">No account or cloud upload. Working files stay on this computer.</p>
      </div>
    </aside>
  );
}

function Metric({ label, value, description, tone = "neutral" }: { label: string; value: string; description?: string; tone?: "positive" | "neutral" }) {
  return (
    <div className={`metric ${tone === "positive" ? "metric-positive" : ""}`}>
      <p>{label}</p>
      <strong>{value}</strong>
      {description && <span>{description}</span>}
    </div>
  );
}

function DataTerm({ label, value, description }: { label: string; value: string; description?: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold text-[#607066]">{label}</dt>
      <dd className="mt-1 font-semibold">{value}</dd>
      {description && <dd className="mt-1 text-xs leading-5 text-[#738077]">{description}</dd>}
    </div>
  );
}

function StatusBadge({ status, label }: { status: string; label?: string }) {
  const positive = status === "safe_to_fold" || status === "shared_scene" || status === "complete";
  const warning = status === "hybrid" || status === "independent_only" || status === "complete_no_savings" || status === "failed_quality";
  const friendlyLabel = status === "complete"
    ? "Smaller & quality checked"
    : status === "complete_no_savings"
      ? "Quality checked · Not smaller"
      : status === "failed_quality"
        ? "Needs a closer look"
        : status === "failed"
          ? "Could not complete"
          : status.replaceAll("_", " ");
  return <span className={`status-pill ${positive ? "status-positive" : warning ? "status-warning" : "status-negative"}`}>{label ?? friendlyLabel}</span>;
}

function ErrorPanel({ error, nested = false }: { error: ErrorEnvelope; nested?: boolean }) {
  const frameIndices = error.error.frame_indices ?? [];
  return (
    <section className={`${nested ? "mt-4" : "panel"} rounded-2xl border border-[#a43e2c]/25 bg-[#fff3ef] p-5`} role="alert">
      <p className="eyebrow text-[#8b2f20]">We could not complete this step</p>
      <p className="mt-2 font-semibold text-[#8b2f20]">{error.error.message}</p>
      {frameIndices.length > 0 && <p className="mt-2 text-sm text-[#8b2f20]">Photos to check: {frameIndices.map((index) => index + 1).join(", ")}</p>}
      <details className="mt-3 text-xs text-[#8b2f20]">
        <summary className="cursor-pointer font-semibold">Technical error details</summary>
        <p className="mt-2 font-mono">{error.error.code} · {error.error.stage}</p>
      </details>
    </section>
  );
}

function ViewerGuide({ mode }: { mode: ViewMode }) {
  const content = mode === "difference"
    ? {
        title: "How to read the change heatmap",
        body: "Dark means little change. Orange to white means larger differences worth checking; bright does not always mean damaged. Zoom and drag to inspect.",
      }
    : mode === "compare"
      ? {
          title: "Compare original and rebuilt",
          body: "1× fits the whole photo. Zoom, then drag to inspect. Use the slider to compare.",
        }
      : mode === "original"
        ? {
            title: "Original photo",
            body: "The exact photo you selected.",
          }
        : {
            title: "Rebuilt photo",
            body: "The photo recreated from the collection.",
          };
  return (
    <div className={`viewer-guide mt-4 ${mode === "difference" ? "viewer-guide-heatmap" : ""}`} role="note">
      <p className="font-semibold text-[#17211b]">{content.title}</p>
      <p className="mt-1 text-sm leading-6 text-[#607066]">{content.body}</p>
    </div>
  );
}

function zoomLabel(zoom: number): string {
  return `${zoom.toFixed(2).replace(/\.00$/, "")}×`;
}
