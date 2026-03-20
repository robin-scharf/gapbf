from __future__ import annotations

from .database_attempt_store import DatabaseAttemptStoreMixin
from .database_fingerprints import DatabaseFingerprintMixin
from .database_run_store import DatabaseRunStoreMixin


class DatabaseOperationsMixin(
    DatabaseFingerprintMixin,
    DatabaseRunStoreMixin,
    DatabaseAttemptStoreMixin,
):
    pass
