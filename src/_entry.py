"""PyInstaller entry shim for the truman-director binary distribution.

The bundled binary's module graph must root in an ABSOLUTE import so the
package-relative imports inside ``truman_director`` (``from .state import ...``)
resolve. PyInstaller treats this file as the top-level ``__main__``; a package
module used directly as the entry loses its package context and the relative
imports fail.

Normal dev/test does NOT use this — run ``python -m truman_director.plugin``
(``plugin.py`` carries its own ``if __name__ == "__main__": main()`` guard).
This shim exists only so ``scripts/package_binary.sh`` can hand PyInstaller a
clean absolute-import entry point.
"""

from truman_director.plugin import main

if __name__ == "__main__":
    main()
