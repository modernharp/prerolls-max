import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SkipLink } from "./Layout";

describe("Skip to content", () => {
  it("moves focus to the page content without changing the address", async () => {
    window.location.hash = "#/videos";
    render(
      <>
        <SkipLink />
        <main id="main" tabIndex={-1}>
          Intro Videos
        </main>
      </>,
    );
    screen.getByRole("link", { name: "Skip to content" }).focus();
    await userEvent.keyboard("{Enter}");
    expect(screen.getByRole("main")).toHaveFocus();
    expect(window.location.hash).toBe("#/videos");
  });
});
