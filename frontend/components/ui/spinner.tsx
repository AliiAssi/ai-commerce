// The Jinja version carried .htmx-indicator and was toggled by htmx adding a class to an
// ancestor. There is no such class now: callers mount this only while a request is in flight.
export function Spinner() {
  return (
    <span
      className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-brand border-t-transparent align-middle"
      aria-label="Loading"
      role="status"
    />
  );
}
