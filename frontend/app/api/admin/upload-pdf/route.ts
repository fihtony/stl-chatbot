import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8086';

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const file = formData.get('file') as File;

    if (!file) {
      return NextResponse.json(
        { error: 'No file provided' },
        { status: 400 }
      );
    }

    // Validate file type
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      return NextResponse.json(
        { error: 'Only PDF files are allowed' },
        { status: 400 }
      );
    }

    // Create new FormData for backend
    const backendFormData = new FormData();
    backendFormData.append('file', file);

    // Send to backend
    const response = await fetch(`${BACKEND_URL}/api/admin/upload-pdf`, {
      method: 'POST',
      body: backendFormData,
    });

    if (!response.ok) {
      const error = await response.json();
      return NextResponse.json(
        { error: error.detail || error.error || 'Upload failed' },
        { status: response.status }
      );
    }

    const data = await response.json();
    // Pass through backend response directly (already has success/data structure)
    return NextResponse.json(data);

  } catch (error) {
    console.error('PDF upload error:', error);
    return NextResponse.json(
      { error: `Upload failed: ${error instanceof Error ? error.message : String(error)}` },
      { status: 500 }
    );
  }
}
