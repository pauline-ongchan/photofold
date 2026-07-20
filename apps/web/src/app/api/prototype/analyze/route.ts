import { analyzeRun, BridgeError, createRun, removeRun } from "@/lib/prototype-server";
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let runId: string | null = null;
  try {
    const form = await request.formData();
    const files = form.getAll("files").filter((item): item is File => item instanceof File);
    runId = await createRun(files);
    const analysis = await analyzeRun(runId);
    return NextResponse.json({ runId, analysis }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if (runId && error instanceof BridgeError && error.status < 500) await removeRun(runId);
    if (error instanceof BridgeError) {
      return NextResponse.json(error.envelope, { status: error.status });
    }
    return NextResponse.json(
      {
        error: {
          code: "PROCESSOR_FAILED",
          message: "The local prototype could not analyze these uploads.",
          stage: "service",
          frame_indices: [],
          retryable: false,
          debug: process.env.NODE_ENV === "development" && error instanceof Error ? error.message : null,
        },
      },
      { status: 500 },
    );
  }
}
