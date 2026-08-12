/**
 * Jest runs the engine tests.
 *
 * The workflow is plain TypeScript with no DOM in it, so these run in `node` and cover
 * the methodology the same way `backend/tests/test_domain_rules.py` does.
 */
module.exports = {
  preset: "ts-jest",
  testEnvironment: "node",
  roots: ["<rootDir>/__tests__"],
  testMatch: ["**/*.test.ts", "**/*.test.tsx"],
  moduleNameMapper: { "^@/(.*)$": "<rootDir>/$1" },
};
