import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

const API_TARGET = "http://127.0.0.1:3101";

export default defineConfig({
  plugins: [vue()],
  base: "./",
  build: { outDir: "dist", sourcemap: false },
  server: {
    proxy: {
      "/api": API_TARGET,
      "/data": API_TARGET,
    },
  },
});
