import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8086';

/**
 * 创建后端代理处理器的工厂函数
 * 统一处理所有管理 API 的代理请求，避免代码重复
 */
export async function proxyToBackend(
  path: string,
  method: string = 'GET',
  body?: string
) {
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
    // Pass through backend response directly (already has success/data structure)
    return NextResponse.json(data);
  } catch (error) {
    console.error(`Proxy error for ${path}:`, error);
    return NextResponse.json(
      { error: `Backend connection failed: ${error}` },
      { status: 503 }
    );
  }
}
