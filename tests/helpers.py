"""
Доступ к коду HTTP API из тестов. Обработчики разнесены по модулям api/*,
поэтому подмена зависимостей (run_query, has_consent и т.п.) делается во всех
модулях, где это имя используется.
"""
import importlib

_MODULES = [
    importlib.import_module(name)
    for name in ("api.common", "api.consultation", "api.profile", "api.health", "api.auth", "main")
]


class _ApiNamespace:
    """Читает атрибут из того модуля API, где он определён или импортирован."""

    def __getattr__(self, name):
        for module in _MODULES:
            if hasattr(module, name):
                return getattr(module, name)
        raise AttributeError(name)


api = _ApiNamespace()


def patch_api(monkeypatch, name, value):
    """monkeypatch.setattr во всех модулях API, где есть это имя."""
    found = False
    for module in _MODULES:
        if hasattr(module, name):
            monkeypatch.setattr(module, name, value)
            found = True
    assert found, f"{name} not found in API modules"
