"""PyInstaller entry script: PyInstaller needs a file, not ``python -m assistant_prof``."""

from assistant_prof.main import main

raise SystemExit(main())
