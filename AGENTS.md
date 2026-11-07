# Finnip — Development Guidelines

## Architecture

Finnip is a personal AI assistant built using:

- Hermes Agent for reasoning, memory and Telegram integration.
- Home Assistant for smart-home device control.
- TypeScript, Fastify and Zod for Home Bridge.
- Python for the custom Hermes plugin `finnip-lights`.
- Docker Compose for service orchestration.

## Development Rules

1. Inspect existing implementations before changing them.
2. Work on feature branches. Never commit directly to `main`.
3. Use TypeScript strict mode and validate external input.
4. Add or update automated tests for behavioral changes.
5. Never commit API keys, tokens, credentials, private memories or runtime data.
6. Preserve compatibility between Home Bridge and the Hermes plugin.
7. Do not change Docker configuration or deploy services without approval.
8. Never execute physical-device actions during automated tests.
9. Prefer small, focused Pull Requests with clear descriptions.
10. Explain architectural decisions and important changes.

## Validation

Before opening a Pull Request:

- Run Home Bridge type checks.
- Run Vitest tests.
- Build the TypeScript application.
- Validate Python syntax and plugin behavior.
- Ensure the Docker image builds successfully.

## Security

- Home Bridge alone should hold the Home Assistant token.
- Hermes may use only the dedicated Bridge API key.
- Do not expose Home Bridge publicly.
- Use least-privilege credentials and container permissions.

## Deployment

Merging a Pull Request must not automatically deploy to the Debian server. Production deployments require explicit approval.
