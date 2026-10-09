import { mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";

// Only public URLs become templates. JavaScript and API paths stay unchanged.
async function prepare(directory = "dist", relative = "") {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const source = join(directory, entry.name);
    const path = join(relative, entry.name);
    if (entry.isDirectory()) {
      await prepare(source, path);
    } else if (/\.(html|xml)$/.test(entry.name) || entry.name === "robots.txt") {
      const content = await readFile(source, "utf8");
      if (!content.includes("https://runtime.invalid")) continue;
      const destination = join("runtime-templates", path);
      await mkdir(dirname(destination), { recursive: true });
      await writeFile(destination,
        content.replaceAll("https://runtime.invalid", "${FRONTEND_BASE_URL}"));
    }
  }
}

await mkdir("runtime-templates", { recursive: true });
await prepare();
