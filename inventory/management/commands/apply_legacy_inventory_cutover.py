from django.core.management.base import BaseCommand, CommandError

from inventory.cutover import LegacyInventoryCutoverError, LegacyInventoryCutoverService


class Command(BaseCommand):
    help = 'Aplica el corte aprobado del inventario legado al ledger operativo.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Valida el corte y muestra las operaciones sin escribir en la base de datos.',
        )

    def handle(self, *args, **options):
        try:
            results = (
                LegacyInventoryCutoverService.preview()
                if options['dry_run'] else LegacyInventoryCutoverService.apply()
            )
        except LegacyInventoryCutoverError as exc:
            raise CommandError(str(exc)) from exc

        for row, created in results:
            description = getattr(row, 'operation_key', row)
            state = 'se creará' if options['dry_run'] and created else ('creado' if created else 'ya existente')
            self.stdout.write(f'{description}: {state}.')
        self.stdout.write(self.style.SUCCESS(
            'Validación completada sin cambios.' if options['dry_run'] else 'Corte de inventario completado.',
        ))
