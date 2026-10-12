"""``manage.py compile_api_messages`` — compile the API error catalogue.

Django's own ``compilemessages`` needs GNU ``gettext``. This command does the
same job with :mod:`core.mofile` (pure standard library) so the error
catalogue can be rebuilt on any machine:

    python manage.py compile_api_messages          # write backend/locale/**.mo
    python manage.py compile_api_messages --check  # CI: fail if out of date
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.mofile import CatalogueError, build_mo, iter_catalogues, parse_po


class Command(BaseCommand):
    help = (
        "Compile LOCALE_PATHS/**/*.po into .mo with the bundled pure-Python "
        "writer (GNU msgfmt is not required)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Do not write anything; exit non-zero if a .mo is missing or stale.",
        )

    def handle(self, *args, **options):
        catalogues = iter_catalogues(settings.LOCALE_PATHS)
        if not catalogues:
            self.stderr.write(
                self.style.WARNING(
                    "No .po files under LOCALE_PATHS="
                    f"{[str(path) for path in settings.LOCALE_PATHS]}"
                )
            )
            return

        stale = []
        for po_path, mo_path in catalogues:
            try:
                payload = build_mo(
                    parse_po(po_path.read_text(encoding="utf-8"), where=str(po_path))
                )
            except CatalogueError as exc:
                raise CommandError(str(exc)) from exc

            if mo_path.exists() and mo_path.read_bytes() == payload:
                self.stdout.write(f"up to date  {mo_path}")
                continue
            if options["check"]:
                stale.append(mo_path)
                self.stdout.write(self.style.ERROR(f"stale        {mo_path}"))
                continue

            mo_path.write_bytes(payload)
            self.stdout.write(self.style.SUCCESS(f"compiled     {mo_path}"))

        if stale:
            raise CommandError(
                f"{len(stale)} catalogue(s) out of date; run "
                "`python manage.py compile_api_messages` and commit the .mo files"
            )
