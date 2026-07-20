import { BridgeError, downloadHeaders, exportFrame, responseBody } from "@/lib/prototype-server";
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  context: { params: Promise<{ runId: string; index: string }> },
) {
  try {
    const { runId, index } = await context.params;
    const exported = await exportFrame(runId, Number(index));
    return new Response(responseBody(exported.payload), {
      headers: downloadHeaders("image/webp", exported.filename, exported.payload.byteLength),
    });
  } catch (error) {
    if (error instanceof BridgeError) {
      return NextResponse.json(error.envelope, { status: error.status });
    }
    return NextResponse.json({ error: { code: "PROCESSOR_FAILED", message: "Export unavailable.", stage: "service", frame_indices: [], retryable: false, debug: null } }, { status: 500 });
  }
}
