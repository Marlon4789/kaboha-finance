#!/usr/bin/env python
import os
import sys

if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kaboha_finance.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            'No se pudo importar Django. Asegúrate de haber instalado las dependencias.'
        ) from exc
    execute_from_command_line(sys.argv)
