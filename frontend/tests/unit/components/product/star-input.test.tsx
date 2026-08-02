import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { StarInput } from "@/components/product/star-input";

describe("StarInput", () => {
  /** Radios, not buttons: this is what gives arrow-key movement and the group announcement. */
  it("exposes five labelled choices in one radiogroup", () => {
    render(<StarInput value={0} onChange={() => {}} />);
    const group = screen.getByRole("radiogroup", { name: "Rating" });
    expect(group).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(5);
    expect(screen.getByRole("radio", { name: /4 stars — Good/ })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /1 star — Terrible/ })).toBeInTheDocument();
  });

  it("reports the rating that was picked", () => {
    const onChange = vi.fn();
    render(<StarInput value={0} onChange={onChange} />);

    fireEvent.click(screen.getByRole("radio", { name: /5 stars/ }));
    expect(onChange).toHaveBeenCalledWith(5);
  });

  it("marks the current value as checked and names it", () => {
    render(<StarInput value={3} onChange={() => {}} />);
    expect(screen.getByRole("radio", { name: /3 stars/ })).toBeChecked();
    expect(screen.getByText("Okay")).toBeInTheDocument();
  });

  it("says nothing before a rating exists", () => {
    render(<StarInput value={0} onChange={() => {}} />);
    expect(screen.queryByText("Excellent")).toBeNull();
    expect(screen.getAllByRole("radio").every((radio) => !(radio as HTMLInputElement).checked));
  });
});
