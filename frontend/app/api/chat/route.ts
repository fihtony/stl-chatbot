import { NextRequest, NextResponse } from 'next/server';

/**
 * Chat API endpoint - Proxy to Python backend
 * This endpoint forwards requests to the Python FastAPI backend
 */

// Backend API configuration
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8086';
const API_TIMEOUT = 120000; // 120 seconds (2 minutes) for complex queries

/**
 * POST handler - Forward chat requests to Python backend
 */
export async function POST(request: NextRequest) {
  const requestId = Math.random().toString(36).substring(2, 8);
  const startTime = Date.now();

  try {
    // Parse request body
    const body = await request.json();
    const { message, provider = 'zhipu' } = body;

    // Validate input
    if (!message || typeof message !== 'string') {
      return NextResponse.json(
        {
          error: 'Message is required and must be a string',
          code: 'INVALID_INPUT',
        },
        { status: 400 }
      );
    }

    console.log(`\n${'='.repeat(80)}`);
    console.log(`[${requestId}] 📨 Received chat request`);
    console.log(`   Message: "${message.substring(0, 100)}${message.length > 100 ? '...' : ''}"`);
    console.log(`   Provider: ${provider}`);
    console.log(`   Backend URL: ${BACKEND_URL}`);

    // Forward request to Python backend
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT);

    try {
      const backendResponse = await fetch(`${BACKEND_URL}/api/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message,
          provider,
          useCache: true,
          useFAQ: true,
          searchMethod: 'hybrid',
          enableSubjectFilter: true,
          enableQueryExpansion: true,
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!backendResponse.ok) {
        const errorData = await backendResponse.json().catch(() => ({}));
        throw new Error(
          errorData.detail || `Backend returned ${backendResponse.status}`
        );
      }

      const data = await backendResponse.json();
      const totalTime = Date.now() - startTime;

      console.log(`[${requestId}] ✅ Request completed successfully (${totalTime}ms)`);
      console.log(`   Chunks used: ${data.metadata?.chunksUsed || 0}`);
      console.log(`${'='.repeat(80)}\n`);

      // Return response
      return NextResponse.json({
        response: data.response,
        provider: data.provider,
        metadata: data.metadata,
      });
    } catch (fetchError) {
      clearTimeout(timeoutId);

      // Check if it's a timeout error
      if (fetchError instanceof Error && fetchError.name === 'AbortError') {
        console.error(`[${requestId}] ⏱️ Request timed out after ${API_TIMEOUT}ms`);
        return NextResponse.json(
          {
            error: 'Request processing timed out. Please try again.',
            code: 'TIMEOUT',
          },
          { status: 408 }
        );
      }

      throw fetchError;
    }
  } catch (error) {
    const totalTime = Date.now() - startTime;
    console.error(`[${requestId}] ❌ Request failed after ${totalTime}ms:`, error);

    // Determine error type and response
    let statusCode = 500;
    let errorCode = 'INTERNAL_ERROR';
    let errorMessage = 'Failed to process chat message';

    if (error instanceof Error) {
      errorMessage = error.message;

      // Check for specific error types
      if (error.message.includes('ECONNREFUSED') || error.message.includes('fetch failed')) {
        statusCode = 503;
        errorCode = 'BACKEND_UNAVAILABLE';
        errorMessage = 'Backend service is unavailable. Please ensure the Python backend is running.';
      }
    }

    return NextResponse.json(
      {
        error: errorMessage,
        code: errorCode,
      },
      { status: statusCode }
    );
  }
}

/**
 * GET handler - Health check and preload
 */
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const action = searchParams.get('action');

    // Health check
    if (action === 'health') {
      try {
        const backendResponse = await fetch(`${BACKEND_URL}/api/health`, {
          method: 'GET',
        });

        const backendHealth = await backendResponse.json();

        return NextResponse.json({
          status: 'healthy',
          backend: backendHealth,
          timestamp: new Date().toISOString(),
        });
      } catch (error) {
        return NextResponse.json({
          status: 'degraded',
          backend: 'unavailable',
          error: error instanceof Error ? error.message : 'Unknown error',
          timestamp: new Date().toISOString(),
        });
      }
    }

    // Preload
    if (action === 'preload') {
      // Trigger backend preload
      fetch(`${BACKEND_URL}/api/health`)
        .catch(() => {});

      return NextResponse.json({
        message: 'Preload triggered',
        status: 'ok',
      });
    }

    // Default response
    return NextResponse.json({
      endpoint: '/api/chat',
      version: '2.0',
      backend: BACKEND_URL,
      methods: ['POST', 'GET'],
    });
  } catch (error) {
    console.error('GET /api/chat error:', error);

    return NextResponse.json(
      {
        error: 'Health check failed',
        code: 'HEALTH_CHECK_ERROR',
      },
      { status: 500 }
    );
  }
}

/**
 * OPTIONS handler - CORS preflight
 */
export async function OPTIONS() {
  return new NextResponse(null, {
    status: 200,
    headers: {
      'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
      'Access-Control-Max-Age': '86400',
    },
  });
}
