"use client";

import type { components } from "@photofold/contracts";
import { useEffect, useMemo, useState } from "react";

type HealthResponse = components["schemas"]["HealthResponse"];

type HealthState =
  | { kind: "loading" }
  | { kind: "connected"; health: HealthResponse }
  | { kind: "error"; message: string };

const processorUrl =
  process.env.NEXT_PUBLIC_PROCESSOR_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

function formatBytes(bytes: number): string {
  return new Intl.NumberFormat("en", {
    notation: "compact",
    maximumFractionDigits: 1,
    style: "unit",
    unit: "byte",
    unitDisplay: "narrow",
  }).format(bytes);
}

export default function Home() {
  const [state, setState] = useState<HealthState>({ kind: "loading" });
  const healthUrl = useMemo(() => `${processorUrl}/v1/health`, []);

  useEffect(() => {
    const controller = new AbortController();

    async function loadHealth() {
      try {
        const response = await fetch(healthUrl, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`Processor returned HTTP ${response.status}`);
        const health = (await response.json()) as HealthResponse;
        setState({ kind: "connected", health });
      } catch (error) {
        if (controller.signal.aborted) return;
        setState({
          kind: "error",
          message: error instanceof Error ? error.message : "Unknown processor error",
        });
      }
    }

    void loadHealth();
    return () => controller.abort();
  }, [healthUrl]);

  return (
    <main className="min-h-screen bg-[#f3f0e8] px-5 py-10 text-[#17211b] sm:px-8 sm:py-16">
      <div className="mx-auto max-w-5xl">
        <header className="border-b border-[#17211b]/15 pb-8">
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.22em] text-[#496151]">
            Phase 0 · Foundation
          </p>
          <div className="mt-4 grid gap-5 lg:grid-cols-[1fr_auto] lg:items-end">
            <div>
              <h1 className="text-5xl font-semibold tracking-[-0.055em] sm:text-7xl">
                PhotoFold
              </h1>
              <p className="mt-3 max-w-2xl text-lg leading-8 text-[#496151]">
                Keep every shot. Store the scene once.
              </p>
            </div>
            <p className="max-w-sm text-sm leading-6 text-[#607066]">
              This page still reports foundation readiness only. The Gate 1 compression proof is
              available through the CLI and offline report, not a product workflow.
            </p>
          </div>
        </header>

        <section className="mt-8 overflow-hidden rounded-3xl border border-[#17211b]/10 bg-white/70 shadow-[0_24px_80px_rgba(23,33,27,0.08)]">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#17211b]/10 px-6 py-5 sm:px-8">
            <div>
              <h2 className="text-xl font-semibold tracking-tight">Processor readiness</h2>
              <p className="mt-1 font-mono text-xs text-[#607066]">{healthUrl}</p>
            </div>
            <StatusPill state={state} />
          </div>

          <div className="p-6 sm:p-8">
            {state.kind === "loading" && (
              <p className="text-sm text-[#607066]">Checking the deterministic processor…</p>
            )}
            {state.kind === "error" && (
              <div className="rounded-2xl border border-[#a43e2c]/25 bg-[#fff3ef] p-5">
                <p className="font-semibold text-[#8b2f20]">Processor unavailable</p>
                <p className="mt-2 text-sm text-[#8b2f20]">{state.message}</p>
              </div>
            )}
            {state.kind === "connected" && <HealthDetails health={state.health} />}
          </div>
        </section>

        <footer className="mt-7 flex flex-wrap items-center justify-between gap-3 px-1 text-xs text-[#607066]">
          <span>Gate 1 CLI proof available · no model credential required</span>
          <a className="underline underline-offset-4" href={`${processorUrl}/docs`}>
            Open processor API docs
          </a>
        </footer>
      </div>
    </main>
  );
}

function StatusPill({ state }: { state: HealthState }) {
  if (state.kind === "loading") {
    return <span className="status-pill bg-[#ece9de] text-[#607066]">Checking…</span>;
  }
  if (state.kind === "error") {
    return <span className="status-pill bg-[#ffe6df] text-[#8b2f20]">Disconnected</span>;
  }
  const ready = state.health.status === "ok";
  return (
    <span className={`status-pill ${ready ? "bg-[#dbf2df] text-[#215f36]" : "bg-[#fff0c9] text-[#76570d]"}`}>
      {ready ? "Processor connected" : "Processor degraded"}
    </span>
  );
}

function HealthDetails({ health }: { health: HealthResponse }) {
  const dataset = health.dataset;
  const cards = [
    ["WebP codec", health.webp_available && health.webp_roundtrip ? "Available" : "Unavailable"],
    ["Processor", `v${health.version}`],
    ["Python", health.python_version],
    ["Semantic provider", "Disabled"],
  ];

  return (
    <div className="space-y-8">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map(([label, value]) => (
          <div className="rounded-2xl bg-[#f3f0e8] p-4" key={label}>
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-[#738077]">{label}</p>
            <p className="mt-2 font-semibold">{value}</p>
          </div>
        ))}
      </div>

      <div>
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-[#738077]">
              Curated dataset
            </p>
            <h3 className="mt-2 text-2xl font-semibold tracking-tight">
              {dataset?.id ?? "Not available"}
            </h3>
          </div>
          {dataset && <p className="font-mono text-xs text-[#607066]">{formatBytes(dataset.total_bytes)}</p>}
        </div>
        {dataset ? (
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <DataPoint label="Frames" value={String(dataset.frame_count)} />
            <DataPoint label="Width" value={`${dataset.width}px`} />
            <DataPoint label="Height" value={`${dataset.height}px`} />
          </div>
        ) : (
          <p className="mt-3 text-sm text-[#8b2f20]">Dataset validation did not pass.</p>
        )}
      </div>

      <div className="rounded-2xl border border-dashed border-[#17211b]/20 p-5">
        <p className="font-medium">Current limitations</p>
        <ul className="mt-3 space-y-2 text-sm leading-6 text-[#607066]">
          {health.limitations.map((limitation) => (
            <li key={limitation}>— {limitation}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function DataPoint({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-[#17211b]/10 p-4">
      <p className="text-xs text-[#738077]">{label}</p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
    </div>
  );
}
