import nextJest from "next/jest.js";

// next/jest wires up the SWC transform, CSS/asset stubs, tsconfig `paths` and
// `next.config.mjs` env, so the specs compile exactly like the app does.
const createJestConfig = nextJest({ dir: "./" });

/** @type {import('jest').Config} */
const config = {
  testEnvironment: "<rootDir>/jest.environment.cjs",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  testPathIgnorePatterns: ["<rootDir>/.next/", "<rootDir>/node_modules/"],
  collectCoverageFrom: [
    "lib/**/*.{ts,tsx}",
    "components/**/*.{ts,tsx}",
    // Generated from the backend's OpenAPI schema -- types only, nothing to execute.
    "!lib/api/generated/**",
  ],
};

export default createJestConfig(config);
