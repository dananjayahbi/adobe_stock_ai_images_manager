# 61 — Windows Installation and Upgrade

## Purpose
Define a repeatable Windows installation experience that prepares the local runtime, native tools, storage, configuration, and database without requiring users to understand the development repository.

## Scope
The plan covers supported Windows versions, prerequisites, installer or bootstrap choice, first-run setup, executable discovery, data directories, configuration, firewall and browser launch behavior, upgrades, uninstall, repair, and rollback. It excludes cloud deployment and direct marketplace configuration.

## Decisions / requirements
The supported Windows baseline, CPU architecture, and minimum disk, memory, and runtime requirements must be explicit. The distribution must choose whether Python and Node runtimes are bundled, embedded, or installed separately. Tesseract and ExifTool must be bundled or installed through a documented trusted source, with version and path verification at startup. Native dependencies that cannot be reliably provisioned must produce a guided diagnostic, not a cryptic processing failure.

Installation separates application files from user data. Originals, derived images, database files, logs, configuration, backups, and temporary work have documented locations with permissions and migration behavior. The installer must not overwrite user data. First run creates managed directories, initializes or migrates the database, validates writable space, checks tools, and presents provider configuration without exposing credentials. The application should bind to an intentional local address and launch the supported browser route.

Upgrades are versioned and run migrations before enabling new behavior. A pre-upgrade backup or verified export is required when schema changes can affect user records. Failed migration leaves the prior data recoverable and gives a clear recovery procedure. Uninstall removes application components while preserving user data unless the user explicitly chooses a documented data purge. Repair can revalidate dependencies and recreate missing non-user directories.

Installation artifacts are signed where feasible and verified in a clean Windows environment, standard-user account, path containing spaces, restricted network, and antivirus-enabled workstation. The release package includes a concise troubleshooting path and a version report suitable for support.

## Affected blueprint areas
This formalizes local desktop deployment, technology versions, configuration, storage, migrations, diagnostics, security, and operational procedures.

## Dependencies
It depends on the final packaging technology, Python/Node strategy, native tool licenses and distribution rights, database migration policy, supported Windows matrix, and secret-storage decision.

## Acceptance criteria
- A clean supported Windows machine reaches a usable first-run screen using documented steps.
- Tool versions, writable paths, database state, and configuration are verified.
- Existing user data survives upgrade and uninstall choices as documented.
- Failed upgrades are recoverable without silent data loss.
- Standard-user, path-with-spaces, and restricted-network cases are tested.
- The installer and repair flow produce actionable diagnostics.

## Risks / open questions
Bundling native tools increases package size and licensing obligations. Antivirus may quarantine generated files or executables. The team must choose installer technology, code-signing ownership, support for Windows on ARM, and whether automatic updates are in or out of MVP.