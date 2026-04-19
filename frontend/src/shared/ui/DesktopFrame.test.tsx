import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DesktopFrame } from "./DesktopFrame";

const close = vi.fn(() => Promise.resolve());
const isMaximized = vi.fn(() => Promise.resolve(false));
const minimize = vi.fn(() => Promise.resolve());
const onResized = vi.fn(() => Promise.resolve(() => undefined));
const toggleMaximize = vi.fn(() => Promise.resolve());

vi.mock("../host", () => ({
  isDesktopRuntime: () => true,
}));

vi.mock("@tauri-apps/api/window", () => ({
  getCurrentWindow: () => ({
    close,
    isMaximized,
    minimize,
    onResized,
    toggleMaximize,
  }),
}));

describe("DesktopFrame", () => {
  beforeEach(() => {
    close.mockClear();
    isMaximized.mockClear();
    minimize.mockClear();
    onResized.mockClear();
    toggleMaximize.mockClear();
  });

  it("renders custom chrome and dispatches window actions", async () => {
    render(
      React.createElement(MemoryRouter, { initialEntries: ["/runtime"] },
        React.createElement(
          DesktopFrame,
          null,
          React.createElement("div", null, "desktop-child"),
        ),
      ),
    );

    expect(screen.getByText("desktop-child")).toBeTruthy();
    expect(screen.getByTestId("foundation.desktop-titlebar")).toBeTruthy();
    expect(screen.getByTestId("foundation.desktop-route-context").textContent).toContain("Управление");
    expect(screen.getByTestId("foundation.desktop-route-context").textContent).toContain("Управление рантаймом");

    fireEvent.click(screen.getByRole("button", { name: "Свернуть" }));
    fireEvent.click(screen.getByRole("button", { name: "Развернуть" }));
    fireEvent.doubleClick(screen.getByTestId("foundation.desktop-titlebar").firstElementChild as HTMLElement);
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));

    await waitFor(() => {
      expect(minimize).toHaveBeenCalledTimes(1);
      expect(toggleMaximize).toHaveBeenCalledTimes(2);
      expect(close).toHaveBeenCalledTimes(1);
    });
  });
});
