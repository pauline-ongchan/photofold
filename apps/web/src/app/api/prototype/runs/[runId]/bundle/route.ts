import { BridgeError, bundle, downloadHeaders, responseBody } from "@/lib/prototype-server";
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_request: Request, context: { params: Promise<{ runId: string }> }) {
  try {
    const { runId } = await context.params;
    const payload = await bundle(runId);
    return new Response(responseBody(payload), {
      headers: downloadHeaders("application/octet-stream", "moment.photofold", payload.byteLength),
    });
  } catch (error) {
    if (error instanceof BridgeError) {
      return NextResponse.json(error.envelope, { status: error.status });
    }
    return NextResponse.json({ error: { code: "PROCESSOR_FAILED", message: "Bundle unavailable.", stage: "service", frame_indices: [], retryable: false, debug: null } }, { status: 500 });
  }
}
