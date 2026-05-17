import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";

export default defineConfig({
  site: "https://williamwriting.com",
  integrations: [sitemap()],
  server: {
    host: "127.0.0.1",
    port: 3000,
  },
  trailingSlash: "never",
  legacy: {
    collectionsBackwardsCompat: true,
  },
});
