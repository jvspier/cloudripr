# Releasing

1. Make sure `main` is green in CI.
2. If the release touches sign-in, the 2FA hook or the icloudpd version, check the hook with a
   real Apple ID first (it signs in with an empty, temporary session; no code is pushed):
   `uv run cloudripr verify-2fa-hook --apple-id you@example.com` must print `OK: …`.
3. Bump the version in `pyproject.toml`, `src/cloudripr/__init__.py` and `web/package.json`,
   run `uv lock`, and commit (`chore: release 1.2.3`).
4. Tag and push: `git tag v1.2.3 && git push origin main v1.2.3`.

The Release workflow checks that the tag matches the version, builds the image for amd64 and
arm64, pushes `ghcr.io/jvspier/cloudripr:1.2.3`, `:1.2`, `:1` and `:latest`, and creates a
GitHub release with generated notes.

Screenshots for the README: `make screenshots` (see `scripts/screenshots/`).
