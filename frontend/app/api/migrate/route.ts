import { NextRequest, NextResponse } from 'next/server';
import { withSecurity } from '@/lib/security';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8086';

/**
 * GET /api/migrate - Check migration status
 * Proxies to backend API /api/admin/migrate (GET)
 */
export async function GET(request: NextRequest) {
  // Security check
  const securityError = await withSecurity(request);
  if (securityError) return securityError;

  try {
    // Get db stats to show current status
    const response = await fetch(`${BACKEND_URL}/api/admin/db-stats`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const error = await response.json();
      return NextResponse.json(
        { error: 'Failed to get migration status', details: error.detail || error.message },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json({
      status: 'ready',
      documents: data.documents || 0,
      chunks: data.chunks || 0,
      message: data.documents > 0 
        ? `Database has ${data.documents} documents/chunks`
        : 'Database is empty. Run migration to populate it.'
    });
  } catch (error) {
    console.error('Error checking migration status:', error);
    return NextResponse.json(
      { 
        error: 'Failed to check migration status',
        details: error instanceof Error ? error.message : String(error),
        status: 'error'
      },
      { status: 500 }
    );
  }
}

/**
 * POST /api/migrate - Run database migration
 * Proxies to backend API /api/admin/migrate (POST)
 */
export async function POST(request: NextRequest) {
  // Security check
  const securityError = await withSecurity(request);
  if (securityError) return securityError;

  try {
    console.log('🚀 Starting migration via backend API...');

    const response = await fetch(`${BACKEND_URL}/api/admin/migrate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const error = await response.json();
      return NextResponse.json(
        { error: 'Migration failed', details: error.detail || error.message },
        { status: response.status }
      );
    }

    const data = await response.json();
    console.log(`✅ Migration complete: ${data.newChunks} chunks`);

    return NextResponse.json({
      status: 'success',
      documents: data.newChunks,
      chunks: data.newChunks,
      totalDocuments: data.newChunks,
      totalChunks: data.newChunks,
      message: data.message,
    });
  } catch (error) {
    console.error('❌ Migration failed:', error);
    return NextResponse.json(
      { 
        error: 'Migration failed',
        details: error instanceof Error ? error.message : String(error),
        status: 'error'
      },
      { status: 500 }
    );
  }
}
