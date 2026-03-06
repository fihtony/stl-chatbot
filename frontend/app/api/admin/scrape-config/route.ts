import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8086';

async function proxyToBackend(path: string, method: string = 'GET', body?: string) {
  const url = `${BACKEND_URL}/api/admin${path}`;

  try {
    const response = await fetch(url, {
      method,
      headers: {
        'Content-Type': 'application/json',
      },
      body,
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: `Backend returned ${response.status}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error(`Proxy error for ${path}:`, error);
    return NextResponse.json(
      { error: `Backend connection failed: ${error}` },
      { status: 503 }
    );
  }
}

export async function GET() {
  return proxyToBackend('/scrape-config');
}

export async function POST(request: NextRequest) {
  const body = await request.text();
  return proxyToBackend('/scrape-config', 'POST', body);
}
