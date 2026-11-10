# __author__ = 'InfSub'
# __contact__ = 'https:/t.me/InfSub'
# __copyright__ = 'Copyright (C) 2025, [LegioNTeaM] InfSub'
# __date__ = '2025/12/14'
# __deprecated__ = False
# __maintainer__ = 'InfSub'
# __status__ = 'Development'  # 'Production / Development'
# __version__ = '1.9.0.5'


from pathlib import Path
from typing import Any
from dotenv import dotenv_values
from datetime import datetime as dt
import logging


class Config:
    """
    Синглтон для загрузки и хранения конфигурации приложения.

    Поведение:
    - Читает базовый .env (файл рядом с config.py) через dotenv_values.
    - Нормализует значения (int, bool, lower, формат дат и т.д.) в _load_env.
    - Хранит результат в self._env.

    Пример использования:
        cfg = Config()
        cfg.get_config('FTP')  # вернёт словарь с ключами ftp_... в нижнем регистре
    """
    _instance = None

    def __new__(cls, *args, **kwargs) -> 'Config':
        """
        Создаёт единственный экземпляр Config (singleton).

        :return: экземпляр Config
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Инициализация: чтение .env и нормализация значений.

        Внутренние атрибуты:
        - self._current_date: datetime, момент инициализации (используется для форматирования путей/имён).
        - self._env: dict[str, Any], нормализованные параметры конфигурации.
        """
        if not hasattr(self, '_initialized'):
            self._initialized = True
            logging.info('Загрузка переменных окружения из файла .env')

            base_dir = Path(__file__).parent
            base_env_path = base_dir / '.env'

            self._current_date = dt.now()
            raw_env = dotenv_values(base_env_path)  # dict[str, str | None]
            self._env = self._load_env(raw_env)

    def _load_env(self, raw: dict[str, str | None]) -> dict[str, Any]:
        """
        Нормализует словарь сырых значений из .env.

        :param raw: Сырой словарь ключ->значение, как возвращает dotenv_values.
            Значения могут быть строками или None.
        :ptype raw: dict[str, str | None]

        :return: Словарь с приведёнными типами и форматами (int, bool, lower, формат дат и т.д.).
            Ключи в возвращаемом словаре — в верхнем регистре (как в .env).

        :raises: В случае критической ошибки приведения типов логирует ошибку и завершает процесс.
        """
        current_date = getattr(self, '_current_date', dt.now())

        try:
            return {
                'ENV_DIR': raw.get('ENV_DIR', 'env'),

                # 'CSV_SEPARATOR': (raw.get('CSV_SEPARATOR', ';') or ';').replace(r'\t', '\t'),
                'CSV_SEPARATOR_IN': (
                    raw.get('CSV_SEPARATOR_IN', (raw.get('CSV_SEPARATOR', ';') or ';')) or ';').replace(r'\t', '\t'),
                'CSV_SEPARATOR_OUT': (
                    raw.get('CSV_SEPARATOR_OUT', (raw.get('CSV_SEPARATOR', ';') or ';')) or ';').replace(r'\t', '\t'),
                'CSV_PATH_TEMPLATE_DIRECTORY': raw.get('CSV_PATH_TEMPLATE_DIRECTORY'),
                'CSV_PATH_TEMPLATE_FILE': raw.get('CSV_PATH_TEMPLATE_FILE', ''),
                'CSV_PATH_DIRECTORY': raw.get('CSV_PATH_DIRECTORY'),
                'CSV_FILE_PATTERN': raw.get('CSV_FILE_PATTERN'),
                'CSV_FILE_ENCODING': raw.get('CSV_FILE_ENCODING', 'utf-8'),
                'CSV_FILES_MIN_NUMBER': int(raw.get('CSV_FILES_MIN_NUMBER', 2)),
                'CSV_FILE_NAME_FOR_FTP': current_date.strftime(raw.get('CSV_FILE_NAME_FOR_FTP', 'upload_data.csv')),

                'DATAS_COL_SKU': raw.get('DATAS_COL_SKU', 'Barcode'),
                'DATAS_COL_QUANTITY': raw.get('DATAS_COL_QUANTITY', 'Количество'),
                'DATAS_COL_WIDTH': raw.get('DATAS_COL_WIDTH', 'Ширина'),
                'DATAS_COL_COMPOUND': raw.get('DATAS_COL_COMPOUND'),  # 'Состав'
                # 'DATAS_NAME_OF_PRODUCT_TYPE': raw.get('DATAS_NAME_OF_PRODUCT_TYPE'),
                'DATAS_MAX_WIDTH': int(raw.get('DATAS_MAX_WIDTH', 200)),
                'DATAS_DECIMAL_PLACES': int(raw.get('DATAS_DECIMAL_PLACES', 2)),

                'INACTIVITY_LIMIT_HOURS': int(raw.get('INACTIVITY_LIMIT_HOURS', 24)),

                'TELEGRAM_TOKEN': raw.get('TELEGRAM_TOKEN'),
                'TELEGRAM_CHAT_ID': raw.get('TELEGRAM_CHAT_ID'),
                'TELEGRAM_PARSE_MODE': raw.get('TELEGRAM_PARSE_MODE'),

                'MSG_LANGUAGE': (raw.get('MSG_LANGUAGE', 'en') or 'en').lower(),

                'FTP_ENABLED': (raw.get('FTP_ENABLED', 'true') or 'true').lower() in ('1', 'true', 'yes', 'on'),
                'FTP_HOST': raw.get('FTP_HOST'),
                'FTP_PORT': int(raw.get('FTP_PORT', 21)),
                'FTP_USER': raw.get('FTP_USER'),
                'FTP_PASS': raw.get('FTP_PASS'),
                'FTP_PATH': raw.get('FTP_PATH'),

                'LOG_DIR': current_date.strftime(raw.get('LOG_DIR', r'logs\%Y\%Y.%m')),
                'LOG_FILE': current_date.strftime(raw.get('LOG_FILE', 'backup_log_%Y.%m.%d.log')),
                'LOG_LEVEL_ROOT': (raw.get('LOG_LEVEL_ROOT', 'INFO') or 'INFO').upper(),
                'LOG_LEVEL_CONSOLE': (raw.get('LOG_LEVEL_CONSOLE', 'INFO') or 'INFO').upper(),
                'LOG_LEVEL_FILE': (raw.get('LOG_LEVEL_FILE', 'WARNING') or 'WARNING').upper(),
                'LOG_IGNORE_LIST': raw.get('LOG_IGNORE_LIST', ''),
                'LOG_FORMAT_CONSOLE': (raw.get('LOG_FORMAT_CONSOLE') or '').replace(
                    r'\t', '\t').replace(r'\n', '\n'),
                'LOG_FORMAT_FILE': (raw.get('LOG_FORMAT_FILE') or '').replace(
                    r'\t', '\t').replace(r'\n', '\n'),
                'LOG_DATE_FORMAT': raw.get('LOG_DATE_FORMAT', '%Y.%m.%d %H:%M:%S'),
                'LOG_CONSOLE_LANGUAGE': (raw.get('MSG_LANGUAGE', 'en') or 'en').lower(),
            }
        except (TypeError, ValueError) as e:
            logging.error("Ошибка при нормализации конфигурации: %s", e)
            exit()

    def get_config(self, *config_types: str) -> dict[str, Any]:
        """
        Получение конфигурации по указанным типам (префиксам).

        :param config_types: Один или несколько префиксов (например 'FTP', 'CSV').
            Будут возвращены все ключи, начинающиеся с "<PREFIX>_".
        :ptype config_types: str

        :return: Словарь с параметрами, соответствующими указанным префиксам.
            Ключи в результирующем словаре — в нижнем регистре.
        """
        result: dict[str, Any] = {}
        for config_type in config_types:
            prefix = config_type.upper() + "_"
            for key, value in self._env.items():
                if key.startswith(prefix):
                    result[key.lower()] = value
        return result


class OverlayConfig(Config):
    """
    Конфигурация overlay, накладывающая значения из отдельного .env поверх базового.

    Поведение:
    - Не вызывает повторно инициализацию базового Config (использует синглтон).
    - Читает overlay-файл через dotenv_values и нормализует его тем же _load_env,
      что и базовый конфиг.
    - Хранит merged env в self._merged_env и последний снимок в OverlayConfig._last_merged_env.
    """
    _last_merged_env: dict[str, Any] | None = None

    def __new__(cls, *args, **kwargs):
        """
        Создаёт новый объект OverlayConfig (не singleton для overlay-объектов).
        """
        return object.__new__(cls)

    def __init__(self, overlay_env_name: str | None = None) -> None:
        """
        Инициализация overlay.

        :param overlay_env_name: Имя файла overlay (например 'staging.env') относительно ENV_DIR.
            Если None — используется последний снимок или базовый env.
        :ptype overlay_env_name: str | None

        :return: None

        :raises FileNotFoundError: если указанный overlay-файл не найден.
        """
        base = Config()  # singleton, базовый .env уже загружен один раз
        self._base_env = base._env.copy()

        if overlay_env_name:
            base_dir = Path(__file__).parent
            env_dir_value = self._base_env.get('ENV_DIR', 'env')
            env_dir = Path(env_dir_value)
            if not env_dir.is_absolute():
                env_dir = base_dir / env_dir

            env_path = env_dir / overlay_env_name
            if not env_path.exists():
                raise FileNotFoundError(f'Overlay config not found: "{env_path}"')

            raw_overlay = dotenv_values(env_path)  # dict[str, str | None]
            # используем _load_env базового экземпляра, чтобы применить ту же нормализацию
            self._overlay_env = base._load_env(raw_overlay)
            self._merged_env = {**self._base_env, **self._overlay_env}
            OverlayConfig._last_merged_env = self._merged_env
        else:
            self._overlay_env = {}
            self._merged_env = OverlayConfig._last_merged_env or self._base_env

    def get_config(self, *config_types: str) -> dict[str, Any]:
        """
        Возвращает параметры overlay/merged по указанным префиксам.

        :param config_types: Префиксы для фильтрации (например 'FTP', 'CSV').
        :ptype config_types: str

        :return: dict[str, Any]: Словарь с ключами в нижнем регистре.
        """
        result: dict[str, Any] = {}
        for config_type in config_types:
            prefix = config_type.upper() + '_'
            for key, value in self._merged_env.items():
                if key.startswith(prefix):
                    result[key.lower()] = value
        return result

    @staticmethod
    def list_overlay_files_in_dir(env_dir: Path) -> list[str]:
        """
        Возвращает список имён файлов в каталоге env_dir, начинающихся с '.env.'.

        :param env_dir: Путь к каталогу с overlay-файлами.
        :ptype env_dir: Path

        :return: Список имён файлов (str), как они реально присутствуют в файловой системе.

        :raises FileNotFoundError: если env_dir не существует или не является директорией.
        """
        if not env_dir.exists() or not env_dir.is_dir():
            raise FileNotFoundError(f'ENV_DIR not found or is not a directory: {env_dir}')
        return [p.name for p in env_dir.iterdir() if p.is_file() and p.name.startswith('.env.')]

    @staticmethod
    def resolve_overlay_filename(env_dir: Path, raw_name: str) -> str:
        """
        Разрешает пользовательское имя overlay (только изменяемая часть) в реальное имя файла.

        Правила:
        - raw_name может быть 'staging' или '.env.staging' или 'path/.env.staging' — функция извлечёт базовое имя.
        - Сопоставление с реальными файлами в каталоге выполняется регистронезависимо.
        - Запрещает пустые имена, '..', '/' и '\\' в имени.

        :param env_dir: Путь к каталогу с overlay-файлами.
        :ptype env_dir: Path
        :param raw_name: Входное имя от пользователя.
        :ptype raw_name: str

        :return: Реальное имя файла в каталоге (например '.env.staging').

        :raises ValueError: при некорректном raw_name.
        :raises FileNotFoundError: если соответствующий файл не найден.
        """
        name = Path(str(raw_name)).name.strip()
        if name.startswith('.env.'):
            name = name[5:]
        if not name or '..' in name or '/' in name or '\\' in name:
            raise ValueError(f'Invalid config name: {raw_name!r}')

        # Собираем карту реальных файлов
        real_files = {p.name.lower(): p.name for p in env_dir.iterdir() if p.is_file() and p.name.startswith('.env.')}
        target_lower = f'.env.{name}'.lower()
        actual = real_files.get(target_lower)
        if actual is None:
            raise FileNotFoundError(f'Overlay config not found for name: {raw_name!r} (expected .env.{name})')
        return actual


if __name__ == '__main__':
    from pprint import pprint

    config = Config()
    server_config = config.get_config('SERVER')
    backup_files_config = config.get_config('FILES')
    ftp_config = config.get_config('FTP')
    log_config = config.get_config('LOG')

    print('Server Config:')
    pprint(server_config)
    print()
    print('Backup Files Config:')
    pprint(backup_files_config)
    print()
    print('FTP Config:')
    pprint(ftp_config)
    print()
    print('Log Config:')
    pprint(log_config)

    conf = OverlayConfig('.env.ALLSHOPS')
    ftp_cfg = conf.get_config("FTP")
    print(ftp_cfg)

