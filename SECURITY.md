# Security Policy

## Supported Usage

PLUS Agent is primarily designed for local use. Public server deployment needs additional hardening before it should be exposed to untrusted users.

## Reporting A Vulnerability

Please open a private report or contact the maintainer instead of posting secrets or exploit details in a public issue.

Include:

- affected version or commit
- reproduction steps
- expected and actual behavior
- potential data exposure

## Sensitive Data

Never include API keys, `.env` files, SQLite databases, uploaded GIS files, private outputs, or PLUS runtime binaries in public issues or pull requests.

## Known Local-First Limitations

- The built-in registration flow is convenient for local isolation, not production identity management.
- API keys may be stored in a local Chainlit database when entered through the UI.
- Uploaded data and generated outputs remain on the local machine unless the user publishes or copies them elsewhere.
