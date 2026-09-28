"""
Загрузка каждого модуля бота — ловит ошибки, которые видны только при
выполнении: неимпортированное имя на уровне модуля, опечатку в
константе, цикл по несуществующему списку.

Так бот однажды не запустился: цикл по ACTIONS при загрузке модуля,
а ACTIONS не был импортирован. Компиляция и остальные тесты молчали.

Внешние библиотеки (aiogram, база, сеть, Gemini) заменяются заглушками —
проверяется только наш код.
Запуск:  python test_imports.py
"""

import importlib
import importlib.abc
import importlib.machinery
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))

EXTERNAL = ("aiogram", "httpx", "sqlalchemy", "asyncpg", "aiohttp", "google", "dotenv", "PIL", "openai")


class _StubMeta(type):
    def __getattr__(cls, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return _stub_class(name)

    def __getitem__(cls, item):
        return cls

    def __call__(cls, *args, **kwargs):
        # router.message(фильтр) — это «настройка», результат — декоратор.
        # А уже декоратор, применённый к функции, возвращает саму функцию.
        if cls.__dict__.get("_decorator") and len(args) == 1 and not kwargs and callable(args[0]) \
                and not isinstance(args[0], _StubMeta):
            return args[0]
        result = _stub_class("instance")
        result._decorator = True
        return result

    def __or__(cls, other): return cls
    def __ror__(cls, other): return cls
    def __and__(cls, other): return cls
    def __invert__(cls): return cls
    def __eq__(cls, other): return cls
    def __hash__(cls): return id(cls)
    def __iter__(cls): return iter(())
    def __bool__(cls): return True


def _stub_class(name):
    return _StubMeta(name, (), {})


class _StubModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _stub_class(name)


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path, target=None):
        if fullname.split(".")[0] in EXTERNAL:
            return importlib.machinery.ModuleSpec(fullname, self, is_package=True)
        return None

    def create_module(self, spec):
        module = _StubModule(spec.name)
        module.__path__ = []
        return module

    def exec_module(self, module):
        pass


sys.meta_path.insert(0, _Finder())

# Фиктивные переменные окружения — модули проверяют их при загрузке
import os

for key, value in {
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
    "BOT_TOKEN": "123456:TEST",
    "GEMINI_API_KEY": "test",
    "PIXABAY_API_KEY": "test",
}.items():
    os.environ.setdefault(key, value)


def main() -> int:
    failures, checks = [], 0

    modules = sorted(
        ".".join(path.relative_to(ROOT).with_suffix("").parts)
        for path in ROOT.rglob("*.py")
        if "__pycache__" not in path.parts and not path.name.startswith("test_")
        # arena/ — отдельный TypeScript-сервис; в его node_modules бывают чужие .py
        and "arena" not in path.relative_to(ROOT).parts[:1] and "node_modules" not in path.parts
        and path.name != "__init__.py"
    )

    for name in modules:
        checks += 1
        try:
            importlib.import_module(name)
        except (NameError, AttributeError, ImportError, KeyError, IndexError) as error:
            failures.append(f"  {name}: {type(error).__name__}: {error}")
        except Exception as error:
            # Ошибки заглушек (например, наследование от заглушки с метаклассом)
            # — не наш код; реальные ошибки имён ловятся выше
            if isinstance(error, TypeError) and "metaclass" in str(error):
                continue
            failures.append(f"  {name}: {type(error).__name__}: {error}")

    if failures:
        print(f"❌ {len(failures)} модулей не загружаются:\n")
        print("\n".join(failures))
        return 1

    print(f"✅ Все {checks} модулей бота загружаются.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
