## Reference Dependency Policy

- `screenpipe` is reference-only for architecture/docs comparison.
- Do NOT add runtime/build/test dependency on `screenpipe`.
- Do NOT import modules, execute binaries, or read required artifacts from `screenpipe` during normal MyRecall execution.
- Allowed: manual comparison and design reference.
- If reference path is needed, use optional env var `SCREENPIPE_ROOT`; workflow must still work without it.
