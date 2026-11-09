import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatProductCards } from "@/components/chat/chat-product-cards";
import type { ChatProduct } from "@/lib/client/sse";

const track = vi.hoisted(() => vi.fn());
vi.mock("@vercel/analytics", () => ({ track }));

function product(overrides: Partial<ChatProduct> = {}): ChatProduct {
  return {
    id: 12,
    name: "Wild Mountain Za'atar",
    price: "14.50",
    image_url: null,
    rating_avg: "4.80",
    review_count: 9,
    stock: 3,
    url: "/products/12?utm_source=assistant&utm_medium=chat",
    ...overrides,
  };
}

describe("ChatProductCards", () => {
  beforeEach(() => track.mockClear());

  it("links each card to its product page in a new tab", () => {
    render(<ChatProductCards products={[product()]} />);

    const card = screen.getByRole("link", { name: /Wild Mountain Za'atar/ });
    expect(card).toHaveAttribute("href", "/products/12?utm_source=assistant&utm_medium=chat");
    expect(card).toHaveAttribute("target", "_blank");
    expect(card).toHaveTextContent("$14.50");
  });

  it("flags an out-of-stock product", () => {
    render(<ChatProductCards products={[product({ stock: 0 })]} />);

    expect(screen.getByText("Out of stock")).toBeInTheDocument();
  });

  it("drops a card whose url is not a store path", () => {
    const { container } = render(
      <ChatProductCards products={[product({ url: "https://evil.example" })]} />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("shows the see-all link and tracks clicks by kind and path", () => {
    render(
      <ChatProductCards
        products={[product()]}
        more={{ total: 14, url: "/catalog?q=zaatar&utm_source=assistant&utm_medium=chat" }}
      />,
    );

    fireEvent.click(screen.getByRole("link", { name: "See all 14 results →" }));
    fireEvent.click(screen.getByRole("link", { name: /Wild Mountain Za'atar/ }));

    expect(track).toHaveBeenNthCalledWith(1, "Assistant link click", {
      kind: "more",
      path: "/catalog",
    });
    expect(track).toHaveBeenNthCalledWith(2, "Assistant link click", {
      kind: "card",
      path: "/products/12",
    });
  });
});
