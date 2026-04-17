import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const currentDir = dirname(fileURLToPath(import.meta.url));

function resolveEnvDir(): string {
  const repoRoot = resolve(currentDir, "..");
  if (existsSync(resolve(repoRoot, ".env")) || existsSync(resolve(repoRoot, ".env.example"))) {
    return repoRoot;
  }
  return currentDir;
}

export default defineConfig(({ mode }) => {
  const envDir = resolveEnvDir();
  const env = loadEnv(mode, envDir, "");

  process.env.VITE_API_BASE_URL ??= env.VITE_API_BASE_URL;
  process.env.VITE_API_KEY ??= env.VITE_API_KEY;
  const mediaProxyHeaders = env.VITE_API_KEY ? { "X-API-Key": env.VITE_API_KEY } : undefined;

  return {
    envDir,
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
        },
        "/media": {
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/media/, "/api"),
          headers: mediaProxyHeaders,
        },
      },
    },
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: "./src/test/setup.ts"
    }
  };
});
