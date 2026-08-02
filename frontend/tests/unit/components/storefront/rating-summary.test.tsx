import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RatingSummary } from "@/components/storefront/rating-summary";
import type { Review } from "@/lib/api/types";

function review(id: number, rating: number): Review {
  return {
    id,
    product_id: 1,
    user_id: id,
    user_email: `buyer${id}@example.com`,
    rating,
    text: "Good.",
    created_at: "2026-01-01T00:00:00Z",
  };
}

describe("RatingSummary", () => {
  it("stays out of the way when there is nothing to summarise", () => {
    const { container } = render(<RatingSummary reviews={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("averages the ratings it was given", () => {
    render(<RatingSummary reviews={[review(1, 5), review(2, 4), review(3, 3)]} />);
    expect(screen.getByText("4.0")).toBeInTheDocument();
    expect(screen.getByText("3 reviews")).toBeInTheDocument();
  });

  it("counts every band, including the empty ones", () => {
    const { container } = render(<RatingSummary reviews={[review(1, 5), review(2, 5)]} />);
    const rows = container.querySelectorAll(
      '[data-testid="rating-summary"] > div:last-child > div',
    );
    expect(rows).toHaveLength(5);
    expect(rows[0]).toHaveTextContent("2");
    expect(rows[1]).toHaveTextContent("0");
  });

  it("singularises a lone review", () => {
    render(<RatingSummary reviews={[review(1, 4)]} />);
    expect(screen.getByText("1 review")).toBeInTheDocument();
  });
});
