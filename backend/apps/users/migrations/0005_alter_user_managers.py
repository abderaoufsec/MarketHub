"""Point the ``user`` model at the Phase 8 ``UserManager``.

Split from 0004 because the manager (which normalizes an empty email to
``None`` instead of ``""``) landed after the schema migration: without it,
phone-only accounts would collide on ``email = ''``.
"""

import apps.users.models
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_phoneotp_remove_emailverificationtoken_user_and_more'),
    ]

    operations = [
        migrations.AlterModelManagers(
            name='user',
            managers=[
                ('objects', apps.users.models.UserManager()),
            ],
        ),
    ]
