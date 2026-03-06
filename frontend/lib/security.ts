import { NextRequest, NextResponse } from 'next/server';

/**
 * Security configuration interface
 */
interface SecurityConfig {
  allowedOrigins: string[];
  internalApiKey: string;
}

/**
 * Get security configuration from environment variables
 */
function getSecurityConfig(): SecurityConfig {
  const allowedOriginsEnv = process.env.ALLOWED_ORIGINS || '';
  const internalApiKey = process.env.INTERNAL_API_KEY || '';

  // Parse allowed origins - support both comma-separated and space-separated
  const allowedOrigins = allowedOriginsEnv
    .split(/[,\s]+/)
    .map(origin => origin.trim())
    .filter(origin => origin.length > 0);

  return {
    allowedOrigins,
    internalApiKey,
  };
}

/**
 * Check if the origin is allowed
 */
function isOriginAllowed(origin: string, allowedOrigins: string[]): boolean {
  if (allowedOrigins.length === 0) {
    // If no origins configured, allow all (for development)
    return true;
  }

  // Normalize the origin for comparison
  const normalizedOrigin = origin.toLowerCase().replace(/\/+$/, '');

  return allowedOrigins.some(allowed => {
    const normalizedAllowed = allowed.toLowerCase().replace(/\/+$/, '');
    // Exact match
    if (normalizedOrigin === normalizedAllowed) {
      return true;
    }
    // Support wildcard subdomains (e.g., *.example.com)
    if (normalizedAllowed.startsWith('*.')) {
      const baseDomain = normalizedAllowed.slice(2);
      return normalizedOrigin.endsWith(baseDomain);
    }
    return false;
  });
}

/**
 * Verify the request has a valid API key
 */
function verifyApiKey(request: NextRequest, internalApiKey: string): boolean {
  // Check X-Internal-API-Key header
  const apiKeyHeader = request.headers.get('X-Internal-API-Key');
  if (apiKeyHeader && apiKeyHeader === internalApiKey) {
    return true;
  }

  // Also check query parameter for convenience (less secure but useful)
  const apiKeyQuery = request.nextUrl.searchParams.get('api_key');
  if (apiKeyQuery && apiKeyQuery === internalApiKey) {
    return true;
  }

  return false;
}

/**
 * Security verification result
 */
export interface SecurityVerificationResult {
  allowed: boolean;
  reason?: string;
  isDevelopmentMode: boolean;
}

/**
 * Verify the security of a request
 * 
 * This function checks:
 * 1. Origin header validation (if ALLOWED_ORIGINS is configured)
 * 2. Internal API key validation (if INTERNAL_API_KEY is configured)
 * 
 * @param request - The Next.js request object
 * @returns SecurityVerificationResult indicating if the request is allowed
 */
export function verifyRequestSecurity(request: NextRequest): SecurityVerificationResult {
  const config = getSecurityConfig();

  // Development mode: no security checks if no configuration
  if (config.allowedOrigins.length === 0 && !config.internalApiKey) {
    return {
      allowed: true,
      isDevelopmentMode: true,
    };
  }

  // Check origin header
  const origin = request.headers.get('origin') || request.headers.get('referer');
  if (origin && config.allowedOrigins.length > 0) {
    if (!isOriginAllowed(origin, config.allowedOrigins)) {
      console.warn(`Security: Origin not allowed: ${origin}`);
      return {
        allowed: false,
        reason: `Origin not allowed: ${origin}`,
        isDevelopmentMode: false,
      };
    }
  }

  // Check API key if configured
  if (config.internalApiKey) {
    if (!verifyApiKey(request, config.internalApiKey)) {
      console.warn(`Security: Invalid or missing API key`);
      return {
        allowed: false,
        reason: 'Invalid or missing API key',
        isDevelopmentMode: false,
      };
    }
  }

  return {
    allowed: true,
    isDevelopmentMode: false,
  };
}

/**
 * Middleware function to protect API routes
 * 
 * Use this in your API route handlers to verify requests are from trusted sources.
 * 
 * @param request - The Next.js request object
 * @returns NextResponse with 403 error if not allowed, or null if allowed
 */
export function requireSecureRequest(request: NextRequest): NextResponse | null {
  const verification = verifyRequestSecurity(request);

  if (!verification.allowed) {
    return NextResponse.json(
      {
        error: 'Forbidden',
        message: verification.reason,
        status: 'security_violation',
      },
      { status: 403 }
    );
  }

  return null;
}

/**
 * Create a security check middleware for API routes
 * 
 * Usage in route.ts:
 * 
 * export async function POST(request: NextRequest) {
 *   const securityError = await withSecurity(request);
 *   if (securityError) return securityError;
 *   
 *   // ... your route logic
 * }
 */
export async function withSecurity(request: NextRequest): Promise<NextResponse | null> {
  return requireSecureRequest(request);
}

/**
 * Check if security is enabled (not in development mode without configuration)
 */
export function isSecurityEnabled(): boolean {
  const config = getSecurityConfig();
  return config.allowedOrigins.length > 0 || config.internalApiKey.length > 0;
}
