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
          <div className="space-y-5">
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
      <div>
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.22em] text-[#496151]">
          Gate 3P · Local deterministic prototype
        </p>
        <h1 className="mt-3 text-5xl font-semibold tracking-[-0.055em] sm:text-7xl">PhotoFold</h1>
        <p className="mt-2 text-lg text-[#496151]">Keep every shot. Store the scene once.</p>
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
          <p className="eyebrow">01 · Choose</p>
          <h2 id="upload-heading" className="section-title">A short photo set</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[#607066]">
            Choose 5–20 photos taken at approximately the same moment and from approximately the same position.
          </p>
        </div>
        <div className="text-right">
          <p className="font-mono text-xs text-[#607066]">{uploads.length} / 20 frames</p>
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
        <p className="mt-4 font-semibold">Drop the moment here</p>
        <p className="mt-1 text-sm text-[#607066]">JPEG, PNG, or WebP · mixed dimensions use safe independent storage</p>
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
                    <p className="text-xs font-semibold text-[#728077]">FRAME {String(index + 1).padStart(2, "0")}</p>
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
          {uploads.length < 5 ? `${5 - uploads.length} more photo${5 - uploads.length === 1 ? "" : "s"} needed` : "Ready for deterministic validation"}
        </p>
        <button className="button-primary" type="button" disabled={!canAnalyze} onClick={onAnalyze}>
          {busy ? "Validating and analyzing…" : "Analyze this moment"}
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
    ? `${analysis.shared_frame_count} frames can share scene data.`
    : analysis.strategy === "hybrid"
      ? `${analysis.shared_frame_count} frames can share scene data; ${analysis.fallback_frame_count} will be stored independently.`
      : "These photos will use independent storage.";
  return (
    <section className="panel" aria-labelledby="analysis-heading">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">02 · Confirm</p>
          <h2 id="analysis-heading" className="section-title">Processor analysis</h2>
        </div>
        <StatusBadge status={analysis.strategy} label="Ready to fold" />
      </div>

      <p className="mb-5 rounded-2xl bg-[#eef2e9] px-5 py-4 font-semibold">{strategyMessage}</p>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Metric label="Accepted photos" value={`${analysis.source_frames.length}`} />
        <Metric label="Shared frames" value={`${analysis.shared_frame_count}`} />
        <Metric label="Fallback frames" value={`${analysis.fallback_frame_count}`} />
        <Metric label="Exact source total" value={formatBytes(analysis.original_total_bytes)} />
        <Metric label="Normalized canvas" value={analysis.normalized_dimensions ? `${analysis.normalized_dimensions.width}×${analysis.normalized_dimensions.height}` : "Per frame"} />
        <Metric label="Reference frame" value={reference ? `${reference.index + 1} · ${reference.original_filename}` : "No shared base"} />
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <div className="rounded-2xl bg-[#eef2e9] p-5">
          <p className="eyebrow">Measured alignment</p>
          <dl className="mt-4 grid grid-cols-2 gap-4">
            <DataTerm label="Reference score" value={analysis.reference_score?.toFixed(3) ?? "Unavailable"} />
            <DataTerm label="Mean inlier ratio" value={`${(meanInlier * 100).toFixed(1)}%`} />
            <DataTerm label="Minimum overlap" value={`${(minimumOverlap * 100).toFixed(1)}%`} />
            <DataTerm label="Error threshold" value={`${analysis.alignment_measurement.max_median_reprojection_error.toFixed(2)} analysis px`} />
            <DataTerm label="Analysis canvas" value={`≤ ${analysis.alignment_measurement.analysis_max_dimension}px`} />
          </dl>
        </div>
        <div className="rounded-2xl border border-dashed border-[#17211b]/20 p-5">
          <p className="eyebrow">Explicitly deferred</p>
          <ul className="mt-3 space-y-2 text-sm text-[#607066]">
            {analysis.deferred_fields.map((field) => <li key={field}>— {field.replaceAll("_", " ")}</li>)}
          </ul>
        </div>
      </div>

      <div className="mt-5 rounded-2xl border border-[#17211b]/10 p-5">
        <p className="font-semibold">Per-frame storage</p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {analysis.source_frames.map((source) => {
            const disposition = analysis.frame_dispositions[source.index];
            const fallback = disposition.storage_mode === "independent_source";
            return (
              <div className="rounded-xl bg-[#f7f5ef] p-3 text-sm" key={source.index}>
                <div className="flex items-center justify-between gap-3">
                  <span className="truncate font-medium">{source.index + 1} · {source.original_filename}</span>
                  <span className={`status-pill ${fallback ? "status-warning" : "status-positive"}`}>
                    {fallback ? "Fallback" : "Shared"}
                  </span>
                </div>
                <p className="mt-1 text-xs text-[#607066]">
                  {fallback ? disposition.fallback_reason : disposition.storage_mode.replaceAll("_", " ")} · {source.width}×{source.height}
                </p>
              </div>
            );
          })}
        </div>
      </div>

      <div className="mt-5 rounded-2xl border border-[#17211b]/10 p-5">
        <p className="font-semibold">Why this result</p>
        <ul className="mt-2 space-y-1 text-sm leading-6 text-[#607066]">
          {analysis.reasons.map((reason) => <li key={reason}>— {reason}</li>)}
        </ul>
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-[#17211b]/10 pt-5">
        <p className="max-w-xl text-sm text-[#607066]">Fold reuses this evidence and the exact source checksums. Independent fallback may reduce or eliminate savings.</p>
        <button className="button-primary" disabled={analysis.status !== "analyzed_foldable" || busy} type="button" onClick={onFold}>
          {busy ? "Folding with the real processor…" : "Fold this moment"}
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
  const base = `/api/prototype/runs/${runId}/frames/${frame.index}`;
  const successful = result.status === "complete";
  const statusTitle = result.status === "complete"
    ? "Moment folded successfully"
    : result.status === "complete_no_savings"
      ? "Fold complete — no storage reduction"
      : result.status === "failed_quality"
        ? "Fold measured — quality threshold missed"
        : "Fold failed";

  return (
    <div className="space-y-5">
      <section className="panel" aria-labelledby="results-heading">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">03 · Review</p>
            <h2 id="results-heading" className="section-title">{statusTitle}</h2>
          </div>
          <StatusBadge status={result.status} />
        </div>

        {result.storage && result.quality && result.package_contents ? (
          <>
            <p className="mb-5 text-sm text-[#607066]">
              Strategy: <strong className="text-[#17211b]">{result.strategy.replaceAll("_", " ")}</strong> · {result.shared_frame_count} shared · {result.fallback_frame_count} fallback
            </p>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Metric label="Uploaded originals" value={formatBytes(result.storage.original_total_bytes)} />
              <Metric label="PhotoFold archive" value={formatBytes(result.storage.package_total_bytes)} />
              <Metric
                label={successful ? "Saved vs uploads" : "Difference vs uploads"}
                value={successful ? `${formatBytes(result.storage.bytes_saved)} · ${formatPercent(result.storage.percent_saved)}` : `${formatBytes(Math.abs(result.storage.byte_delta))} ${result.storage.byte_delta < 0 ? "larger" : "smaller"}`}
                tone={successful ? "positive" : "neutral"}
              />
              <Metric label="Mean / minimum SSIM" value={`${result.quality.mean_ssim.toFixed(4)} / ${result.quality.minimum_ssim.toFixed(4)}`} />
            </div>
            <div className="mt-4 flex flex-wrap gap-2 font-mono text-xs text-[#607066]">
              <span className="data-chip">{result.reconstructed_frame_count} reconstructions</span>
              <span className="data-chip">{result.package_contents.member_count} package members</span>
              <span className="data-chip">{result.package_contents.patch_count} change patches</span>
              <span className="data-chip">{result.package_contents.independent_source_count} independent sources</span>
              <span className="data-chip">SHA-256 {result.storage.package_sha256.slice(0, 12)}…</span>
            </div>
          </>
        ) : result.error ? <ErrorPanel error={{ error: result.error }} nested /> : null}
      </section>

      {frame.reconstructed && (
        <section className="panel" aria-labelledby="viewer-heading">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">04 · Inspect</p>
              <h2 id="viewer-heading" className="section-title">Frame {frame.index + 1} · {frame.original_filename}</h2>
              <p className="mt-1 font-mono text-xs text-[#607066]">
                SSIM {frame.ssim?.toFixed(6)} · {frame.storage_mode.replaceAll("_", " ")}{frame.storage_mode !== "independent_source" ? ` · ${frame.patch_count} patches` : ""}
              </p>
              {frame.fallback_reason && <p className="mt-2 text-sm text-[#8a5a20]">Fallback: {frame.fallback_reason}</p>}
            </div>
            <div className="flex flex-wrap gap-2">
              <a className="button-primary" href={`${base}/export`}>Export selected photo</a>
              <a className="button-secondary" href={`/api/prototype/runs/${runId}/bundle`}>Download PhotoFold archive</a>
            </div>
          </div>
          <p className="mb-4 text-xs text-[#607066]">Requires PhotoFold to reconstruct the complete set.</p>

          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#17211b]/10 pb-4">
            <div className="flex flex-wrap gap-2" role="group" aria-label="Viewer mode">
              {(["compare", "original", "reconstruction", "difference"] as ViewMode[]).map((mode) => (
                <button className={`view-tab ${props.viewMode === mode ? "view-tab-active" : ""}`} type="button" key={mode} onClick={() => props.setViewMode(mode)}>
                  {mode === "difference" ? "Heatmap" : mode[0].toUpperCase() + mode.slice(1)}
                </button>
              ))}
            </div>
            <label className="flex items-center gap-3 text-xs font-semibold uppercase tracking-[0.12em] text-[#607066]">
              Zoom {zoomLabel(props.zoom)}
              <input aria-label="Zoom" type="range" min="1" max="3" step="0.25" value={props.zoom} onChange={(event) => props.setZoom(Number(event.target.value))} />
            </label>
          </div>

          {props.viewMode === "compare" && (
            <label className="mt-4 flex items-center gap-3 text-xs font-semibold uppercase tracking-[0.12em] text-[#607066]">
              Original {props.comparison}%
              <input className="flex-1" aria-label="Comparison position" type="range" min="0" max="100" value={props.comparison} onChange={(event) => props.setComparison(Number(event.target.value))} />
              Reconstruction
            </label>
          )}

          <div className="viewer-stage mt-4" data-testid="frame-viewer">
            <div className="viewer-canvas" style={{ width: `${props.zoom * 100}%` }}>
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
                onClick={() => props.setSelectedFrame(item.index)}
              >
                <span>Frame {item.index + 1}</span>
                <strong>{item.storage_mode === "independent_source" ? "Fallback" : "Shared"} · {item.ssim?.toFixed(4) ?? "—"}</strong>
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="rounded-3xl border border-[#17211b]/10 bg-[#e8eadf] p-5 text-sm leading-6 text-[#55665b]">
        <p className="font-semibold text-[#17211b]">What this number means</p>
        <p className="mt-1">Storage is measured against the exact uploaded source files. The accepted offline Gate 1/Phase 1B evidence contains the matched-quality independent-WebP control; this fast interactive run does not rerun that research sweep.</p>
        <ul className="mt-3 space-y-1">{result.warnings.map((warning) => <li key={warning}>— {warning}</li>)}</ul>
      </section>
    </div>
  );
}

function WorkflowRail({ analysis, result, busy, uploadCount }: { analysis: PrototypeAnalysis | null; result: PrototypeResult | null; busy: "analyzing" | "folding" | null; uploadCount: number }) {
  const steps = [
    { label: "Choose", detail: uploadCount ? `${uploadCount} selected` : "5–20 photos", active: !analysis },
    { label: "Analyze", detail: analysis ? analysis.strategy.replaceAll("_", " ") : busy === "analyzing" ? "running now" : "processor validation", active: Boolean(busy === "analyzing" || (analysis && !result)) },
    { label: "Fold", detail: result ? result.status.replaceAll("_", " ") : busy === "folding" ? "running now" : "single real treatment", active: Boolean(busy === "folding" || result) },
    { label: "Inspect", detail: result?.reconstructed_frame_count ? `${result.reconstructed_frame_count} frames ready` : "compare and export", active: Boolean(result) },
  ];
  return (
    <aside className="h-fit rounded-3xl border border-[#17211b]/10 bg-[#17211b] p-6 text-[#f3f0e8] lg:sticky lg:top-6">
      <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-[#b7c7ba]">Local workflow</p>
      <ol className="mt-6 space-y-5">
        {steps.map((step, index) => (
          <li className="flex gap-3" key={step.label}>
            <span className={`step-number ${step.active ? "step-number-active" : ""}`}>{index + 1}</span>
            <div><p className="font-semibold">{step.label}</p><p className="mt-1 text-xs capitalize text-[#afbbb2]">{step.detail}</p></div>
          </li>
        ))}
      </ol>
      <div className="mt-7 border-t border-white/15 pt-5 text-xs leading-5 text-[#afbbb2]">
        <p>No account. No cloud. No model credential.</p>
        <p className="mt-2">Uploads remain in a run-scoped local workspace until startup or manual cleanup.</p>
      </div>
    </aside>
  );
}

function Metric({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "positive" | "neutral" }) {
  return <div className={`metric ${tone === "positive" ? "metric-positive" : ""}`}><p>{label}</p><strong>{value}</strong></div>;
}

function DataTerm({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-xs text-[#738077]">{label}</dt><dd className="mt-1 font-semibold">{value}</dd></div>;
}

function StatusBadge({ status, label }: { status: string; label?: string }) {
  const positive = status === "safe_to_fold" || status === "shared_scene" || status === "complete";
  const warning = status === "hybrid" || status === "independent_only" || status === "complete_no_savings" || status === "failed_quality";
  return <span className={`status-pill ${positive ? "status-positive" : warning ? "status-warning" : "status-negative"}`}>{label ?? status.replaceAll("_", " ")}</span>;
}

function ErrorPanel({ error, nested = false }: { error: ErrorEnvelope; nested?: boolean }) {
  const frameIndices = error.error.frame_indices ?? [];
  return (
    <section className={`${nested ? "mt-4" : "panel"} rounded-2xl border border-[#a43e2c]/25 bg-[#fff3ef] p-5`} role="alert">
      <p className="eyebrow text-[#8b2f20]">{error.error.code} · {error.error.stage}</p>
      <p className="mt-2 font-semibold text-[#8b2f20]">{error.error.message}</p>
      {frameIndices.length > 0 && <p className="mt-2 text-sm text-[#8b2f20]">Affected frames: {frameIndices.map((index) => index + 1).join(", ")}</p>}
    </section>
  );
}

function zoomLabel(zoom: number): string {
  return `${zoom.toFixed(2).replace(/\.00$/, "")}×`;
}
