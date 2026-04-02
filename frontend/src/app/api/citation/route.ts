import { NextRequest, NextResponse } from "next/server";

interface CitationRequest {
  citation_id: number;
  original_ids: number[];
  session_id?: string;
}

interface CitationResponse {
  content: string;
  success: boolean;
  error?: string;
}

const BACKEND_URL = process.env.BACKEND_URL || "http://127.0.0.1:8086";
const CITATION_TIMEOUT = 15000; // 15 seconds

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as CitationRequest;
    const { citation_id, original_ids, session_id } = body;

    if (!citation_id || typeof citation_id !== "number") {
      return NextResponse.json(
        { error: "Invalid citation_id" },
        { status: 400 }
      );
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), CITATION_TIMEOUT);

    try {
      const response = await fetch(`${BACKEND_URL}/api/citation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ citation_id, original_ids, session_id: session_id || "default" }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        return NextResponse.json(
          { error: `Backend returned ${response.status}` },
          { status: response.status }
        );
      }

      const data = (await response.json()) as CitationResponse;
      return NextResponse.json(data);
    } catch (fetchError) {
      if (
        fetchError instanceof Error &&
        fetchError.name === "AbortError"
      ) {
        return NextResponse.json(
          { error: "Citation fetch timeout" },
          { status: 504 }
        );
      }
      throw fetchError;
    }
  } catch (error) {
    console.error("Citation API proxy error:", error);
    return NextResponse.json(
      { error: "Failed to fetch citation" },
      { status: 500 }
    );
  }
}
