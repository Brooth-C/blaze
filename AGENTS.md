# Current Mac development

- Target Apple Silicon only.
- The supported Mac interface is Explore and Practice. Advanced Studio is removed
  from the stable build, including its asset routes and packaged DAW assets.
  Its development is paused; do not reintroduce it without a new user request.
- Build and validate the Mac application on macOS 26 only.
- The user authorized the existing macOS 15 and Intel **installer checks** for
  release validation on 2026-10-29. Keep those checks alongside macOS 26; this
  does not add an Intel GUI build or resume Intel application development.
- Keep existing Windows, Linux and Android releases unchanged unless requested.
