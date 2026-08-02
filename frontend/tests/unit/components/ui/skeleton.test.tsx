import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  PlateGridSkeleton,
  RowListSkeleton,
  Skeleton,
  TextSkeleton,
} from "@/components/ui/skeleton";

describe("Skeleton", () => {
  /** `.skeleton` is what app.css animates, and what prefers-reduced-motion switches off. */
  it("carries the animated class", () => {
    const { container } = render(<Skeleton className="h-4 w-10" />);
    expect(container.firstElementChild).toHaveClass("skeleton");
  });
});

describe("TextSkeleton", () => {
  it("draws one bar per line and shortens the last", () => {
    const { container } = render(<TextSkeleton lines={3} />);
    const bars = container.querySelectorAll(".skeleton");
    expect(bars).toHaveLength(3);
    expect(bars[2]).toHaveClass("w-3/5");
  });
});

describe("PlateGridSkeleton", () => {
  it("announces itself as loading rather than as empty results", () => {
    render(<PlateGridSkeleton count={4} />);
    expect(screen.getByRole("status", { name: "Loading products" })).toBeInTheDocument();
  });

  it("fills a whole page of plates by default, so the grid does not jump on swap", () => {
    const { container } = render(<PlateGridSkeleton />);
    expect(container.querySelectorAll(".aspect-\\[4\\/5\\]")).toHaveLength(12);
  });
});

describe("RowListSkeleton", () => {
  it("names what is loading", () => {
    render(<RowListSkeleton rows={2} label="Loading your orders" />);
    expect(screen.getByRole("status", { name: "Loading your orders" })).toBeInTheDocument();
  });
});
