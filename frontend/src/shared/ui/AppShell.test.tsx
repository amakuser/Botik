import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AppShell } from "./AppShell";

describe("AppShell", () => {
  it("renders grouped navigation and marks the active route", () => {
    const view = render(
      React.createElement(
        MemoryRouter,
        { initialEntries: ["/runtime"] },
        React.createElement(
          AppShell,
          null,
          React.createElement("div", null, "child-content"),
        ),
      ),
    );

    expect(screen.getByRole("heading", { name: "Botik Foundation" })).toBeTruthy();
    expect(screen.getByText("Core")).toBeTruthy();
    expect(screen.getByText("Surfaces")).toBeTruthy();
    expect(screen.getByText("child-content")).toBeTruthy();

    const runtimeLink = screen.getByRole("link", { name: "Runtime Control" });
    expect(runtimeLink.className).toContain("is-active");

    view.unmount();
  });
});
