// ESLint flat config enforcing the strict code standards (Principles 1-10).
// Type-aware rules are scoped to application source under src/ so config files
// do not require type information.
import prettier from "eslint-config-prettier";
import tseslint from "typescript-eslint";

const SRC = ["src/**/*.{ts,tsx}"];

const typeCheckedForSrc = [
  ...tseslint.configs.strictTypeChecked,
  ...tseslint.configs.stylisticTypeChecked,
].map((config) => ({ ...config, files: SRC }));

export default tseslint.config(
  { ignores: [".next/", "node_modules/", "*.config.mjs", "*.config.ts", "next-env.d.ts"] },
  ...typeCheckedForSrc,
  prettier,
  {
    files: SRC,
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // P1: simple flow control
      "max-depth": ["error", 3],
      "no-else-return": "error",

      // P2/P4: scoping and no shared mutable state
      "no-var": "error",
      "prefer-const": "error",
      "no-shadow": "off",
      "@typescript-eslint/no-shadow": "error",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],

      // P3: no unsafe/legacy features
      "no-eval": "error",
      "no-implied-eval": "error",
      "no-new-func": "error",
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-non-null-assertion": "error",

      // P7: small focused functions
      "max-lines-per-function": ["warn", { max: 120, skipBlankLines: true, skipComments: true }],

      // P8: explicit data shapes
      "@typescript-eslint/explicit-function-return-type": ["error", { allowExpressions: true }],
      "@typescript-eslint/explicit-module-boundary-types": "error",

      // P9: standardized async error handling
      "@typescript-eslint/no-floating-promises": "error",
      "@typescript-eslint/no-misused-promises": "error",

      // P10: no prototype mutation
      "no-extend-native": "error",
    },
  },
);
