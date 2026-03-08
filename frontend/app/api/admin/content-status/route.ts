import { NextRequest, NextResponse } from 'next/server';
import { withSecurity } from '@/lib/security';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8086';

async function proxyRequest(request: NextRequest, path: string) {
  const url = `${BACKEND_URL}/api/admin${path}`;

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };

  // Forward any custom headers
  if (request.headers.has('authorization')) {
    headers['authorization'] = request.headers.get('authorization')!;
  }

  try {
    // Create AbortController with timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000); // 30秒超时

    const response = await fetch(url, {
      method: request.method,
      headers,
      body: request.method !== 'GET' && request.method !== 'HEAD' ? await request.text() : undefined,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);
    const data = await response.json();

    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error(`Proxy error for ${path}:`, error);
    return NextResponse.json(
      { error: `Failed to connect to backend: ${error}` },
      { status: 503 }
    );
  }
}

export async function GET(request: NextRequest) {
  return proxyRequest(request, '/content-status');
}
