/**
 * Failure codes shared by Server Actions and the client components that call them.
 *
 * Deliberately its own module with no imports: result.ts pulls in lib/api/client.ts for
 * ApiError, and that is `server-only`, so a client component importing a constant from there
 * fails the build.
 */
export const UNAUTHENTICATED = "unauthenticated";
