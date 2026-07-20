import {
  BridgeError,
  downloadHeaders,
  type FrameAssetKind,
  frameAsset,
  readBinary,
  responseBody,
} from "@/lib/prototype-server";
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const kinds = new Set<FrameAssetKind>(["original", "reconstruction", "difference"]);

export async function GET(
  _request: Request,
  context: { params: Promise<{ runId: string; index: string; kind: string }> },
) {
  try {
    const { runId, index: indexValue, kind: kindValue } = await context.params;
    if (!kinds.has(kindValue as FrameAssetKind)) {
      throw new BridgeError("MOMENT_NOT_FOUND", "This frame artifact was not found.", "service", 404);
    }
    const asset = await frameAsset(runId, Number(indexValue), kindValue as FrameAssetKind);
    const payload = await readBinary(asset.path);
    return new Response(responseBody(payload), {
      headers: downloadHeaders(asset.contentType, undefined, payload.byteLength),
    });
  } catch (error) {
    if (error instanceof BridgeError) {
      return NextResponse.json(error.envelope, { status: error.status });
    }
    return NextResponse.json({ error: { code: "PROCESSOR_FAILED", message: "Artifact unavailable.", stage: "service", frame_indices: [], retryable: false, debug: null } }, { status: 500 });
  }
}
