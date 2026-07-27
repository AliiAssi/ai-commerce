import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MenuDismiss } from "@/components/behaviour/menu-dismiss";

const pathname = vi.hoisted(() => ({ current: "/" }));
vi.mock("next/navigation", () => ({ usePathname: () => pathname.current }));

/** Mirrors the account dropdown: a summary, a couple of links, and a logout button. */
function mountMenu() {
  document.body.innerHTML = `
    <details class="menu" open>
      <summary id="toggle">shopper@it.test</summary>
      <div>
        <a id="admin" href="/admin">Admin panel</a>
        <a id="orders" href="/account/orders">My orders</a>
        <button id="logout" type="submit">Log out</button>
      </div>
    </details>
    <main><a id="outside" href="/catalog">elsewhere</a></main>
  `;
  return document.querySelector<HTMLDetailsElement>("details.menu")!;
}

const click = (id: string) =>
  document.getElementById(id)!.dispatchEvent(new MouseEvent("click", { bubbles: true }));

beforeEach(() => {
  pathname.current = "/";
  document.body.innerHTML = "";
});

describe("MenuDismiss", () => {
  it("closes the menu when a link inside it is chosen", () => {
    const menu = mountMenu();
    render(<MenuDismiss />);

    click("orders");

    expect(menu.open).toBe(false);
  });

  it("closes the menu when a button inside it is pressed", () => {
    const menu = mountMenu();
    render(<MenuDismiss />);

    click("logout");

    expect(menu.open).toBe(false);
  });

  it("lets the summary open a closed menu instead of fighting the native toggle", () => {
    const menu = mountMenu();
    menu.open = false;
    render(<MenuDismiss />);

    // the browser toggles <details> itself; force-closing here would make the menu
    // impossible to open at all
    click("toggle");

    expect(menu.open).toBe(true);
  });

  it("still lets the summary close its own open menu", () => {
    const menu = mountMenu();
    render(<MenuDismiss />);

    click("toggle");

    expect(menu.open).toBe(false);
  });

  it("closes on a click outside", () => {
    const menu = mountMenu();
    render(<MenuDismiss />);

    click("outside");

    expect(menu.open).toBe(false);
  });

  it("closes on Escape", () => {
    const menu = mountMenu();
    render(<MenuDismiss />);

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

    expect(menu.open).toBe(false);
  });

  it("closes on navigation that did not come from a menu click", () => {
    const menu = mountMenu();
    const { rerender } = render(<MenuDismiss />);

    pathname.current = "/account/orders";
    rerender(<MenuDismiss />);

    expect(menu.open).toBe(false);
  });

  it("stops listening once unmounted", () => {
    const menu = mountMenu();
    const { unmount } = render(<MenuDismiss />);
    unmount();

    click("outside");

    expect(menu.open).toBe(true);
  });
});
