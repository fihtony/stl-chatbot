import { NextRequest, NextResponse } from 'next/server';
import { withSecurity } from '@/lib/security';
import { setCrawlerState, getCrawlerProcess, setCrawlerProcess } from '@/lib/crawlerState';

export async function POST(request: NextRequest) {
  // Security check - admin endpoint
  const securityError = await withSecurity(request);
  if (securityError) return securityError;
  try {
    const crawlerProcess = getCrawlerProcess();
    if (crawlerProcess) {
      crawlerProcess.kill();
      setCrawlerProcess(null);
    }

    setCrawlerState({ isRunning: false });

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('Error stopping crawler:', error);
    return NextResponse.json(
      { success: false, error: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}

