import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://127.0.0.1:8086";

/**
 * Catch-all proxy: /api/admin/** → backend /api/admin/**
 * Forwards cookies so the backend can validate the admin JWT.
 */
async function proxyAdmin(req: NextRequest, method: string) {
  // Reconstruct backend URL from the request path
  const pathname = req.nextUrl.pathname; // e.g. /api/admin/me
  const search = req.nextUrl.search;
  const url = `${BACKEND_URL}${pathname}${search}`;

  const headers: Record<string, string> = {};
  const contentType = req.headers.get("content-type");
  if (contentType) headers["Content-Type"] = contentType;
  const cookie = req.headers.get("cookie");
  if (cookie) headers["Cookie"] = cookie;

  let body: string | undefined;
  if (method !== "GET" && method !== "DELETE") {
    try {
      body = await req.text();
    } catch {
      body = undefined;
    }
  }

  try {
    const upstream = await fetch(url, {
      method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual", // do not follow OAuth redirects server-side
    });

    const responseBody = await upstream.arrayBuffer();
    const response = new NextResponse(responseBody, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") || "application/json",
      },
    });

    // Forward Set-Cookie from backend (JWT cookie)
    const setCookie = upstream.headers.get("set-cookie");
    if (setCookie) response.headers.set("Set-Cookie", setCookie);

    // Forward Location header for OAuth redirects (302 responses)
    const location = upstream.headers.get("location");
    if (location) response.headers.set("Location", location);

    return response;
  } catch {
    return NextResponse.json({ error: "Backend unavailable" }, { status: 502 });
  }
}

export async function GET(req: NextRequest) {
  return proxyAdmin(req, "GET");
}
export async function POST(req: NextRequest) {
  return proxyAdmin(req, "POST");
}
export async function PUT(req: NextRequest) {
  return proxyAdmin(req, "PUT");
}
export async function DELETE(req: NextRequest) {
  return proxyAdmin(req, "DELETE");
}
