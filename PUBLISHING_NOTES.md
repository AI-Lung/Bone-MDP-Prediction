# Publishing Notes

This folder is now structured to be shared on GitHub as a runnable desktop application project.

## What is already prepared

- Windows-first bootstrap launcher: `Run-Windows.bat`
- Automatic first-run setup:
  - locate or install Python 3.10
  - create isolated local runtimes in `.runtime/img_env` and `.runtime/dl_env`
  - install packages automatically
  - run import-based health checks
  - launch the GUI
- Existing macOS launcher kept as `launch_local.command`
- English README for public-facing usage
- `.gitignore` updated so runtime folders and outputs are not committed

## Recommended checks before public release

- Confirm that no patient-identifiable data is included anywhere in the repository.
- Confirm that `assets/model_assets.json` contains only model coefficients and no PHI.
- Test `Run-Windows.bat` on a clean Windows machine with no preconfigured Python environment.
- Test first-run package installation on a normal user account without administrator privileges.

## Important legal/project decisions still owned by you

- Choose and add an open-source license before publishing if you want others to reuse the code formally.
- Decide whether the repository should be public or private during early validation.
- Keep the research-use disclaimer in the README. This project is not a certified medical device.
