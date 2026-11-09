import { useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Modal } from "./Dialog";

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        New collection
      </button>
      <Modal open={open} onOpenChange={setOpen} title="New collection">
        <label>
          Name
          <input name="name" />
        </label>
      </Modal>
    </>
  );
}

describe("Modal keyboard focus", () => {
  it("starts in the first field and goes back to the opener on Escape", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "New collection" });
    opener.focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Name" })).toHaveFocus());
    await user.keyboard("Halloween");
    expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue("Halloween");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(opener).toHaveFocus();
  });
});
