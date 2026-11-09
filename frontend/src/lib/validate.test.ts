import {
  checkDateRange,
  cleanApiKey,
  cleanFilename,
  cleanFolderPath,
  cleanHexColor,
  cleanName,
  cleanServerUrl,
  cleanTimeHHMM,
  cleanToken,
  checkPassword,
  parseDate,
} from "./validate";

const msg = (r: { ok: boolean; message?: string }) => (r.ok ? null : r.message);
const val = (r: { ok: boolean; value?: string }) => (r.ok ? r.value : null);

describe("cleanServerUrl (mirrors clean_server_url)", () => {
  it("adds http:// and drops a trailing slash", () => {
    expect(val(cleanServerUrl("192.168.1.5:32400/"))).toBe("http://192.168.1.5:32400");
    expect(val(cleanServerUrl("plex:32400"))).toBe("http://plex:32400");
    expect(val(cleanServerUrl("HTTPS://plex.example.com/web/"))).toBe("https://plex.example.com/web");
  });
  it("adds the default port when asked", () => {
    expect(val(cleanServerUrl("10.0.0.2", { defaultPort: 8096 }))).toBe("http://10.0.0.2:8096");
  });
  it("uses the same messages as the server", () => {
    expect(msg(cleanServerUrl("", { service: "Plex" }))).toBe("Enter the address of Plex.");
    expect(msg(cleanServerUrl("http://a b"))).toBe("The address can't contain spaces.");
    expect(msg(cleanServerUrl("javascript:alert(1)"))).toBe("The address must start with http:// or https://.");
    expect(msg(cleanServerUrl("ftp://host"))).toBe("The address must start with http:// or https://.");
    expect(msg(cleanServerUrl("http://:32400"))).toBe("Add the computer name or IP address, like http://192.168.1.10:32400.");
    expect(msg(cleanServerUrl("http://host:99999"))).toBe("The port number must be between 1 and 65535.");
    expect(msg(cleanServerUrl("http://host:0"))).toBe("The port number must be between 1 and 65535.");
    expect(msg(cleanServerUrl("http://me:pw@host"))).toBe("Leave the user name and password out of the address.");
    expect(msg(cleanServerUrl("http://host/?X-Plex-Token=abc"))).toBe("Remove everything after ? or # from the address.");
  });
  it("accepts IPv6 addresses", () => {
    expect(val(cleanServerUrl("http://[::1]:8096"))).toBe("http://[::1]:8096");
  });
});

describe("cleanToken / cleanApiKey", () => {
  it("trims spaces and pasted quotes", () => {
    expect(val(cleanToken('  "abcdefghij"  '))).toBe("abcdefghij");
  });
  it("explains what is wrong", () => {
    expect(msg(cleanToken(""))).toBe("Paste the token.");
    expect(msg(cleanToken("abc def ghi"))).toBe("The token can't contain spaces. Copy it again without extra text.");
    expect(msg(cleanToken("short"))).toBe("That token looks too short. Copy the whole thing.");
    expect(msg(cleanApiKey("0123456789"))).toBe("That API key looks too short. Copy the whole thing.");
  });
});

describe("cleanName and cleanFilename", () => {
  it("collapses spaces", () => {
    expect(val(cleanName("  Halloween   2026 "))).toBe("Halloween 2026");
  });
  it("limits length", () => {
    expect(msg(cleanName("x".repeat(101)))).toBe("Keep the name to 100 characters or fewer.");
    expect(msg(cleanName("   ", { what: "collection name" }))).toBe("Enter a collection name.");
  });
  it("refuses characters Plex and Windows can't take", () => {
    expect(msg(cleanFilename("a,b;c"))).toBe("File names can't contain , ;.");
    expect(msg(cleanFilename("intro."))).toBe("File names can't end with a dot or a space.");
    expect(msg(cleanFilename("CON.mp4"))).toBe('"CON.mp4" is a reserved name on Windows. Pick another.');
  });
});

describe("cleanFolderPath", () => {
  it("accepts Linux and Windows paths", () => {
    expect(val(cleanFolderPath("/data/prerolls"))).toBe("/data/prerolls");
    expect(val(cleanFolderPath("D:\\Prerolls"))).toBe("D:\\Prerolls");
  });
  it("refuses relative paths, web addresses and ..", () => {
    expect(msg(cleanFolderPath("prerolls"))).toMatch(/^Use the full path from the top/);
    expect(msg(cleanFolderPath("smb://nas/share"))).toBe("Enter a folder path, not a web or network address. Map the share as a folder first.");
    expect(msg(cleanFolderPath("/data/../etc"))).toBe('The folder path can\'t contain "..". Use the full path.');
  });
});

describe("times, dates, colours", () => {
  it("reads times the way people type them", () => {
    expect(val(cleanTimeHHMM("7:5"))).toBe("07:05");
    expect(val(cleanTimeHHMM("6:30 pm"))).toBe("18:30");
    expect(val(cleanTimeHHMM("12 am"))).toBe("00:00");
    expect(msg(cleanTimeHHMM("13 pm"))).toBe("With am or pm, the hour must be between 1 and 12.");
    expect(msg(cleanTimeHHMM("25:00"))).toBe("That time doesn't exist. Use hours 0-23 and minutes 0-59.");
  });
  it("checks real dates and ranges", () => {
    expect(val(parseDate("2026-12-24"))).toBe("2026-12-24");
    expect(msg(parseDate("2026-02-30"))).toBe("Enter a date like 2026-12-24.");
    expect(checkDateRange("2026-10-31", "2026-10-01")).toBe("The end must be after the start.");
    expect(checkDateRange("2026-10-01", "2026-10-31")).toBeNull();
  });
  it("normalises colours", () => {
    expect(val(cleanHexColor("3366ff"))).toBe("#3366FF");
    expect(msg(cleanHexColor("blue"))).toBe("Pick a colour, or enter one like #3366FF.");
  });
});

describe("checkPassword (mirrors _check_new_password)", () => {
  it("needs 8 characters and nothing else", () => {
    expect(msg(checkPassword("short"))).toBe("Use at least 8 characters.");
    expect(val(checkPassword("lowercase"))).toBe("lowercase");
  });
  it("turns down the most common passwords, whatever the case", () => {
    expect(msg(checkPassword("Password1"))).toMatch(/most common passwords/);
    expect(msg(checkPassword("12345678"))).toMatch(/most common passwords/);
  });
});
