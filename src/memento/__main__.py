"""Allow ``python -m memento`` as well as the ``memento`` console script."""

from memento.cli import main

raise SystemExit(main())
