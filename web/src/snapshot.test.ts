import { describe, expect, it } from "vitest";
import { parseSnapshotQuery } from "./snapshot";

describe("parseSnapshotQuery", () => {
  it("is null outside snapshot mode", () => {
    expect(parseSnapshotQuery("")).toBeNull();
    expect(parseSnapshotQuery("?e2e")).toBeNull();
  });
  it("reads all parameters", () => {
    expect(parseSnapshotQuery("?snapshot=abc123&view=iso&color=A1B2C3&material=mohair")).toEqual({
      key: "abc123", view: "iso", color: "#a1b2c3", material: "mohair",
    });
  });
  it("defaults to the front view with the default yarn", () => {
    expect(parseSnapshotQuery("?snapshot=k1")).toEqual({ key: "k1", view: "front", color: "#efe6d2", material: "cotton" });
  });
  it.each(["?snapshot=", "?snapshot=../x", "?snapshot=k&view=bottom", "?snapshot=k&color=red", "?snapshot=k&material=silk"])(
    "rejects %s", (search) => expect(parseSnapshotQuery(search)).toBeNull(),
  );
});
