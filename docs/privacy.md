# Privacy and Data Policy

PLUS Agent is intended for local research, teaching, and demonstration workflows. Treat uploaded GIS files, generated outputs, API keys, local accounts, and chat history as private local data.

## Not Committed To Git

The repository ignores:

- `.env` and other local environment files
- Chainlit SQLite databases
- memory SQLite databases
- per-user workspaces
- generated outputs
- GeoScene preview caches
- contest delivery archives
- PLUS runtime binaries, DLLs, model files, temporary parameter files, and generated CSV outputs

## API Keys

Use `.env.example` as a template and keep real values in `.env`. The app can also store per-user API keys in the local Chainlit database. Do not upload that database.

## Local Accounts

The built-in login/register flow is designed for local use. It is convenient for multi-session isolation on one machine, but it is not a hardened public identity system.

For public deployment, add stronger registration control, HTTPS, secrets management, admin controls, and a production database.

## GIS Data

Uploaded files are copied into a per-user, per-thread workspace. Generated outputs are stored in the same session workspace. These paths are ignored by Git.

If you publish screenshots, confirm that file names, map content, coordinates, and attribute values do not reveal sensitive project data.

## PLUS Runtime

The public repository excludes third-party executables and DLLs. Users should obtain and place the official runtime locally according to its license and usage terms.
