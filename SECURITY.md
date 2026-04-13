# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.3.x   | :white_check_mark: |
| < 0.3   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it
responsibly:

1. **Do not** open a public GitHub issue.
2. Email [security@phinitelab.com](mailto:security@phinitelab.com) with a
   description of the vulnerability, steps to reproduce, and any potential
   impact.
3. You will receive an acknowledgement within 48 hours.
4. A fix will be developed and released as soon as feasible, typically within
   7 days for critical issues.

## Scope

This policy covers the Python pipeline (`phinitelab_pdf_pipeline/`), the VS
Code extension (`vscode-extension/`), Docker images, and CI/CD workflows.

## Best Practices

- Keep dependencies up to date (`pip install --upgrade`).
- Run the pipeline with the least privilege necessary.
- Never commit secrets, API keys, or credentials to the repository.
