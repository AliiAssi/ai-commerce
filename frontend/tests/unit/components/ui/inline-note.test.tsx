import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { InlineNote } from "@/components/ui/inline-note";

describe("InlineNote", () => {
  /**
   * A failure arrives with its text already in place, so it has to be an alert — a status
   * region only announces what lands inside one that was already mounted.
   */
  it("announces a failure as an alert", () => {
    render(<InlineNote>Only 2 in stock</InlineNote>);
    expect(screen.getByRole("alert")).toHaveTextContent("Only 2 in stock");
  });

  it("reports anything else politely", () => {
    render(<InlineNote tone="success">View your bag</InlineNote>);
    expect(screen.getByRole("status")).toHaveTextContent("View your bag");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
