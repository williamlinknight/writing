import { defineConfig } from "astro/config";

export default defineConfig({
  site: "https://williamlinknight.github.io",
  base: "/writing/",
  server: {
    host: "127.0.0.1",
    port: 3000,
  },
  trailingSlash: "never",
  legacy: {
    collectionsBackwardsCompat: true,
  },
});
