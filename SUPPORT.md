# Getting help with Blaze

Start with the platform setup instructions in [README.md](README.md).
Run your installed launcher with `--help` for available options and `--version`
to identify the application version.

If setup fails, keep the terminal open and read the first error. Extract the
whole installer ZIP, check your internet connection, and rerun setup after
closing Blaze. Linux installer requirements are listed in its README.

For a download issue, retry with `--no-tui` to see plain output. If it only
occurs with aria2c, compare with `--no-aria2c`. Website extractors can change
independently of Blaze; include the affected service and sanitized error.

Use the [bug report form](https://github.com/Brooth-C/blaze/issues/new?template=bug_report.yml)
with your version, operating system, architecture, installation method,
reproduction steps, and expected/actual result. Use the feature request form
for suggestions. Response times are not guaranteed.

Remove cookies, tokens, private URLs, personal paths and account details from
logs or screenshots before posting. Do not post credentials in an issue.
