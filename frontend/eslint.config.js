import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: [
            { name: "child_process", message: "Frontend must not launch OS processes." },
            { name: "node:child_process", message: "Frontend must not launch OS processes." },
            { name: "shelljs", message: "Frontend must not use shell execution libraries." },
            { name: "execa", message: "Frontend must not use shell execution libraries." },
            { name: "cross-spawn", message: "Frontend must not use shell execution libraries." }
          ]
        }
      ]
    }
  }
);
