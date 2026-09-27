import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Badge, StatusBadge, StockBadge } from "@/components/ui/badge";
import { IconLink } from "@/components/ui/links";
import { PlateTag } from "@/components/ui/plate";
import { Price } from "@/components/ui/price";
import { Stars } from "@/components/ui/stars";

describe("Price", () => {
  it("formats a decimal string to two places with a dollar sign", () => {
    render(<Price value="42.5" />);
    expect(screen.getByText("$42.50")).toBeInTheDocument();
  });

  it("does not lose trailing zeros", () => {
    render(<Price value="100.00" />);
    expect(screen.getByText("$100.00")).toBeInTheDocument();
  });
});

describe("StockBadge", () => {
  it("reports out of stock at zero", () => {
    render(<StockBadge stock={0} />);
    expect(screen.getByText("Out of stock")).toBeInTheDocument();
  });

  it("warns at and below the low-stock threshold", () => {
    render(<StockBadge stock={5} />);
    expect(screen.getByText("Only 5 left")).toBeInTheDocument();
  });

  it("is plain in stock above the threshold", () => {
    render(<StockBadge stock={6} />);
    expect(screen.getByText("In stock")).toBeInTheDocument();
  });
});

describe("PlateTag", () => {
  it("stays silent when amply in stock, so cards are not noisy", () => {
    const { container } = render(<PlateTag stock={20} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("marks sold out and low stock", () => {
    const { rerender } = render(<PlateTag stock={0} />);
    expect(screen.getByText("Sold out")).toBeInTheDocument();
    rerender(<PlateTag stock={2} />);
    expect(screen.getByText("Only 2 left")).toBeInTheDocument();
  });
});

describe("Stars", () => {
  it("fills to the nearest whole star", () => {
    const { container } = render(<Stars rating="3.6" />);
    const filled = container.querySelectorAll(".text-star");
    expect(filled).toHaveLength(4);
  });

  it("rounds half away from zero, matching the Jinja round(0, 'common')", () => {
    const { container } = render(<Stars rating="3.5" />);
    expect(container.querySelectorAll(".text-star")).toHaveLength(4);
  });

  it("shows the review count when given one", () => {
    render(<Stars rating="4" count={12} />);
    expect(screen.getByText("(12)")).toBeInTheDocument();
  });

  it("omits the count entirely when absent", () => {
    render(<Stars rating="4" />);
    expect(screen.queryByText(/\(\d+\)/)).not.toBeInTheDocument();
  });
});

describe("StatusBadge", () => {
  it("capitalises the status the way the template filter did", () => {
    render(<StatusBadge status="shipped" />);
    expect(screen.getByText("Shipped")).toBeInTheDocument();
  });
});

describe("Badge", () => {
  it("defaults to the neutral variant", () => {
    render(<Badge>Plain</Badge>);
    expect(screen.getByText("Plain")).toHaveClass("bg-surface-alt");
  });
});

describe("IconLink", () => {
  it("opens web addresses in a new tab without leaking the referrer", () => {
    render(
      <IconLink href="https://github.com/AliiAssi/ai-commerce" icon="github">
        Source
      </IconLink>,
    );
    const link = screen.getByRole("link", { name: "Source" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
  });

  it("leaves mailto links in the same tab", () => {
    render(
      <IconLink href="mailto:someone@example.com" icon="mail">
        someone@example.com
      </IconLink>,
    );
    const link = screen.getByRole("link", { name: "someone@example.com" });
    expect(link).toHaveAttribute("href", "mailto:someone@example.com");
    expect(link).not.toHaveAttribute("target");
  });
});
