"""Repository errors."""


class RepositoryError(RuntimeError):
    pass


class TenantScopeError(RepositoryError):
    pass


class StorageConfigurationError(RepositoryError):
    pass
