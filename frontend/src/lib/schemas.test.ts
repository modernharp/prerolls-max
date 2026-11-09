import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { checkPassword } from "./validate";
import { withConfirm, zChecked } from "./schemas";

const schema = z.object({ password: zChecked(checkPassword), confirm: z.string() });
const resolver = withConfirm(zodResolver(schema), "password");
const run = (values: { password: string; confirm: string }) =>
  resolver(values, undefined, { fields: {}, shouldUseNativeValidation: false });

describe("type the password again", () => {
  it("says the two don't match even while the password is still too short", async () => {
    const { errors } = await run({ password: "abc", confirm: "abd" });
    expect(errors.password?.message).toBe("Use at least 8 characters.");
    expect(errors.confirm?.message).toBe("The two passwords don't match.");
  });

  it("asks for the second box when it's empty", async () => {
    expect((await run({ password: "pumpkin spice 42", confirm: "" })).errors.confirm?.message).toBe("Type the password again.");
  });

  it("is happy when they match", async () => {
    const result = await run({ password: "pumpkin spice 42", confirm: "pumpkin spice 42" });
    expect(result.errors).toEqual({});
    expect(result.values).toEqual({ password: "pumpkin spice 42", confirm: "pumpkin spice 42" });
  });
});
