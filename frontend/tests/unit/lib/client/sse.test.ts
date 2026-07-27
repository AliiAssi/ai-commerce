import { describe, expect, it } from "vitest";

import { createFrameParser } from "@/lib/client/sse";

describe("createFrameParser", () => {
  it("parses a single complete frame", () => {
    const push = createFrameParser();
    expect(push('data: {"type":"token","text":"Hi"}\n\n')).toEqual([
      { type: "token", text: "Hi" },
    ]);
  });

  it("parses several frames arriving in one chunk", () => {
    const push = createFrameParser();
    const frames = push(
      'data: {"type":"tool","name":"search_products"}\n\n' +
        'data: {"type":"token","text":"A"}\n\n' +
        'data: {"type":"done","session_id":"s1"}\n\n',
    );
    expect(frames.map((f) => f.type)).toEqual(["tool", "token", "done"]);
  });

  // the case that actually breaks naive implementations: the network splits a frame
  it("reassembles a frame split across chunks", () => {
    const push = createFrameParser();
    expect(push('data: {"type":"tok')).toEqual([]);
    expect(push('en","text":"hello"}')).toEqual([]);
    expect(push("\n\n")).toEqual([{ type: "token", text: "hello" }]);
  });

  it("splits mid-separator without losing the frame", () => {
    const push = createFrameParser();
    expect(push('data: {"type":"token","text":"a"}\n')).toEqual([]);
    expect(push('\ndata: {"type":"token","text":"b"}\n\n')).toEqual([
      { type: "token", text: "a" },
      { type: "token", text: "b" },
    ]);
  });

  it("keeps a trailing partial frame buffered for the next chunk", () => {
    const push = createFrameParser();
    expect(push('data: {"type":"token","text":"one"}\n\ndata: {"type":"tok')).toEqual([
      { type: "token", text: "one" },
    ]);
    expect(push('en","text":"two"}\n\n')).toEqual([{ type: "token", text: "two" }]);
  });

  it("skips a malformed frame but keeps the stream alive", () => {
    const push = createFrameParser();
    const frames = push(
      "data: {not json}\n\n" + 'data: {"type":"token","text":"survived"}\n\n',
    );
    expect(frames).toEqual([{ type: "token", text: "survived" }]);
  });

  it("ignores comment and event lines, taking only data:", () => {
    const push = createFrameParser();
    expect(push(': keep-alive\nevent: message\ndata: {"type":"token","text":"x"}\n\n')).toEqual(
      [{ type: "token", text: "x" }],
    );
  });

  it("ignores a frame with no data line at all", () => {
    const push = createFrameParser();
    expect(push(": just a heartbeat\n\n")).toEqual([]);
  });

  it("carries an error frame's message through", () => {
    const push = createFrameParser();
    expect(push('data: {"type":"error","message":"Model timed out"}\n\n')).toEqual([
      { type: "error", message: "Model timed out" },
    ]);
  });
});
