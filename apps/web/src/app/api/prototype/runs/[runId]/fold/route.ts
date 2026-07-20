import { BridgeError, foldRun } from "@/lib/prototype-server";
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(_request: Request, context: { params: Promise<{ runId: string }> }) {
  try {
    const { runId } = await context.params;
    const result = await foldRun(runId);
    return NextResponse.json({ runId, result }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if (error instanceof BridgeError) {
      return NextResponse.json(error.envelope, { status: error.status });
    }
    return NextResponse.json(
      {
        error: {
          code: "PROCESSOR_FAILED",
          message: "The local prototype could not finish this fold.",
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
