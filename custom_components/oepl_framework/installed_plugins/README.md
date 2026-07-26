# Runtime-installed plugins

This directory is populated at runtime when a user installs a plugin from a
custom GitHub repository via the framework's options flow ("Add custom
plugin repository"). Its contents are not committed to version control
(see `.gitignore`) — only this file and `__init__.py` are tracked so the
directory exists as a valid Python package in a fresh checkout.

Do not edit files here by hand; they are overwritten on reinstall/update.
