# Task 8 report — release surface, documentation, and delivery

## Scope delivered

- Replaced the package root with the exact public exports `CheckoutClient`,
  `Gateway`, and `get_checkout_gateway`.
- Added `tests/test_public_interface.py` to lock exact root exports, all ten
  resource method signatures, statically checked result types via `assert_type`,
  absence of Stripe SDK names in normalized public annotations, and absence of
  the pre-1.0 modules and compatibility exports.
- Removed the pre-1.0 base, DTO, authentication, Stripe implementation, registry
  compatibility, enums, errors, checks alias, fixtures, and tests. The retained
  low-level webhook helpers now use gateway terminology consistently.
- Updated `test_settings.py` to configure
  `django_checkouts.gateways.stripe.StripeGateway`.
- Replaced the README with the resource-oriented quickstart, explicit gateway
  implementation status, persistence boundary, delivery commands, and
  BSD-3-Clause notice. Added the 1.0 changelog.
- Added a warning-clean Sphinx site with configuration plus quickstart,
  subscriptions, webhooks, reconciliation, errors/retries, typed gateway
  options, gateway authoring, and complete pre-1.0 migration pages. Every
  public page states that the library owns no persistence.
- Documented absolute seat quantities, all proration and cancellation choices,
  resume semantics, raw-body verification, `(variant, event_id)` uniqueness,
  half-open reconciliation windows with overlap/deduplication, all four retry
  dispositions, Stripe portability limits, and the gateway contract suite.

## TDD evidence

The structural test was written before production removal. The prescribed RED
run:

```text
uv run pytest tests/test_public_interface.py -q
# 2 failed, 2 passed
```

The failures were the intended ones: the root still exported only the old
factory and the old modules were still importable. Exact resource signatures
and the Stripe-annotation boundary already passed. After replacing the surface:

```text
uv run pytest tests/test_public_interface.py -q --no-cov
# 4 passed
uv run mypy tests/test_public_interface.py
# Success: no issues found in 1 source file
```

The direct mypy run proves that every `assert_type` result contract is checked
statically, in addition to the runtime structural assertions.

## Fresh delivery verification

| Command | Result |
| --- | --- |
| `uv sync --all-extras --all-groups` | resolved 60 packages; checked 57 |
| `uv run pytest` | 196 passed; 95.36% coverage |
| `uv run mypy django_checkouts` | success across 45 source files |
| `uv run mypy tests/test_public_interface.py` | success |
| `uvx ruff check .` | all checks passed |
| `uv run sphinx-build -W -b html docs docs/_build/html` | build succeeded with warnings as errors |
| `uv build` | wheel and sdist built successfully |
| legacy-term scan | matches only `docs/migration-pre-1.0.rst` |
| public Stripe-annotation scan | no output |
| `git diff --check` | success |

Both a universal wheel and source distribution exist in `dist/`. A second
post-commit build derives their version from the clean immutable release commit,
without a dirty-tree suffix.

## Clean wheel installation

Installed the built wheel plus Stripe into a new `uv` virtual environment
outside the repository. With Django 5.2.17 and Stripe 15.5.0, the smoke test:

- imported the three exact package exports and `StripeGateway`;
- confirmed every removed module is undiscoverable;
- confirmed `py.typed` and the packaged BSD license;
- confirmed no removed Stripe package path exists in the wheel.

The temporary environment was deleted after the successful check.

The clean-tree wheel smoke test also asserted that its embedded setuptools-scm
version contains the release commit revision.

## Design notes

- The tests tied exclusively to deleted modules were removed with those modules;
  the complete gateway lifecycle and contract suites remain and pass.
- The low-level `django_checkouts.webhooks` utilities were retained because the
  Task 8 deletion list did not remove that module. Their constructor vocabulary
  was changed from `provider` to `gateway`, eliminating the compatibility
  surface and satisfying the release scan.
- `default_app_config` was removed from the root because modern supported Django
  versions discover `DjangoCheckoutsConfig` directly.

## Concerns

None.
