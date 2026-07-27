/**
 * SSE frame parser for the chat stream.
 *
 * The contract is set by ai/app/presentation/schemas/chat_schemas.py:format_sse and is
 * unchanged by the migration: frames are separated by a blank line, and the payload is the
 * first line beginning with "data:".
 *
 * This is deliberately a standalone, DOM-free function rather than logic buried in the widget
 * — chunk boundaries are the easiest thing to get wrong here (a frame can be split across two
 * network reads, and a single read can carry several frames), and that is only cheap to prove
 * with tests if the parser can be called directly.
 */
export type ChatFrame =
  | { type: "token"; text?: string }
  | { type: "tool"; name?: string }
  | { type: "done"; session_id?: string }
  | { type: "error"; message?: string };

export function createFrameParser(): (chunk: string) => ChatFrame[] {
  let buffer = "";

  return function push(chunk: string): ChatFrame[] {
    buffer += chunk;
    const frames: ChatFrame[] = [];

    let separator = buffer.indexOf("\n\n");
    while (separator !== -1) {
      const raw = buffer.slice(0, separator);
      buffer = buffer.slice(separator + 2);

      const line = raw.split("\n").find((l) => l.startsWith("data:"));
      if (line) {
        try {
          frames.push(JSON.parse(line.slice(5).trim()) as ChatFrame);
        } catch {
          // a malformed frame is skipped rather than killing the stream, matching the
          // original client — one bad chunk should not lose the tokens after it
        }
      }

      separator = buffer.indexOf("\n\n");
    }

    return frames;
  };
}
