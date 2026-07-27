// The real `server-only` package throws on import outside a React Server Component, which
// would break any unit test that touches lib/api/*. Vitest aliases the package to this stub.
export {};
