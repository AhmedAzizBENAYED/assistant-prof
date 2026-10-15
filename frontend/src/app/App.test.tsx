import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "./App";

describe("App", () => {
  it("shows the French placeholder", () => {
    render(<App />);
    expect(screen.getByRole("heading", { level: 1, name: "Assistant Prof" })).toBeInTheDocument();
    expect(screen.getByText("L'application est en cours de construction.")).toBeInTheDocument();
  });
});
