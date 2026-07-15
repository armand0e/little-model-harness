"""PyInstaller entry point — see packaging/littleharness.spec."""
import os

# Third-party pydantic plugins (e.g. logfire) break frozen builds by
# introspecting source that isn't shipped; we never use them.
os.environ.setdefault("PYDANTIC_DISABLE_PLUGINS", "__all__")

from harness.app import main  # noqa: E402

if __name__ == "__main__":
    main()
