# __author__ = 'InfSub'
# __contact__ = 'ADmin@TkYD.ru'
# __copyright__ = 'Copyright (C) 2024-2025, [LegioNTeaM] InfSub'
# __date__ = '2026/04/01'
# __deprecated__ = False
# __email__ = 'ADmin@TkYD.ru'
# __maintainer__ = 'InfSub'
# __status__ = 'Production'  # 'Production / Development'
# __version__ = '1.9.0.24'

"""
Модуль для работы с FTP: получение конфигурации, загрузка файлов, рекурсивный листинг и
поиск локальных файлов по шаблону.

Содержит:
- _get_ftp_config: извлечение и валидация FTP-параметров из OverlayConfig
- upload_file_to_ftp: асинхронная загрузка файла на FTP
- list_files_on_ftp: рекурсивный список файлов на FTP
- find_matching_files: асинхронный поиск локальных файлов по шаблону
- ftp_main: пример основной логики загрузки с ограничением параллельности
"""

from __future__ import annotations

from aioftp import Client as aioftp_Client, StatusCodeError as aioftp_StatusCodeError
from pathlib import Path
from typing import Any

from logger import logging
from config import OverlayConfig

logging = logging.getLogger(__name__)


def _get_ftp_config(config_names: list[str] | None = None) -> dict[str, str | int | bool]:
    """
    Получает и валидирует конфигурацию FTP из OverlayConfig.

    :param config_names: Список имён конфигураций/overlay (опционально). Если None — используется дефолт.
    :return: Словарь с параметрами FTP:
             {
                 'ftp_host': str,
                 'ftp_port': int,
                 'ftp_user': str,
                 'ftp_pass': str,
                 'ftp_path': str,
                 'ftp_enabled': bool | None
             }
    :raises ValueError: если обязательные параметры (host, user, pass) отсутствуют.
    """
    cfg: dict[str, str | int | bool] = OverlayConfig(config_names).get_config('ftp')
    ftp_host = cfg.get('ftp_host', '')
    ftp_port = int(cfg.get('ftp_port', 21) or 21)
    ftp_user = cfg.get('ftp_user', '')
    ftp_pass = cfg.get('ftp_pass', '')
    ftp_path = cfg.get('ftp_path', '')
    ftp_enabled = cfg.get('ftp_enabled')

    if not ftp_host or not ftp_user or not ftp_pass:
        raise ValueError('FTP host, user и password должны быть заданы в конфигурации (ftp)')

    return {
        'ftp_host': ftp_host,
        'ftp_port': ftp_port,
        'ftp_user': ftp_user,
        'ftp_pass': ftp_pass,
        'ftp_path': ftp_path,
        'ftp_enabled': ftp_enabled,
    }


async def upload_file_to_ftp(
    local_path: Path,
    remote_path: str,
    config: dict[str, str | int | bool] | None = None
) -> dict[str, Any]:
    """
    Асинхронно загружает локальный файл на FTP сервер.

    :param local_path: Путь к локальному файлу (Path). Файл должен существовать.
    :param remote_path: Путь на FTP-сервере (включая имя файла). Пример: '/uploads/file.txt'
    :param config: Словарь с параметрами подключения к FTP (опционально). Если None — берётся из _get_ftp_config.
    :return: Словарь с информацией о результате загрузки:
             {'local': Path, 'remote': str, 'status': 'success' | 'error'}
    :raises ValueError: если в конфигурации отсутствуют host/user/password.
    :raises FileNotFoundError: если локальный файл не найден.
    :raises Exception: пробрасывает исключения, связанные с подключением/загрузкой (aioftp).
    """
    cfg = config if config else _get_ftp_config()
    host = cfg.get('ftp_host', '')
    port = int(cfg.get('ftp_port', 21) or 21)
    user = cfg.get('ftp_user', '')
    password = cfg.get('ftp_pass', '')

    if not host or not user or not password:
        raise ValueError('FTP host, user и password должны быть заданы в конфигурации (ftp)')

    if not local_path.is_file():
        raise FileNotFoundError(f'Локальный файл не найден: {local_path}')

    # Убираем завершающий слеш, если он есть (не изменяем remote_path переменную напрямую)
    remote_path = str(remote_path).rstrip('/')

    result = {'local': local_path, 'remote': remote_path, 'status': 'success'}
    error_msg = None

    try:
        async with aioftp_Client.context(host, port=port, user=user, password=password) as client:
            await client.upload(source=local_path, destination=remote_path, write_into=True)
    except aioftp_StatusCodeError as e:
        # Обработка ошибок FTP (неверный логин, пароль, нет прав и т.д.)
        if '530' in str(e):
            error_msg = f'Ошибка авторизации: неверный логин или пароль для "{host}"'
        else:
            error_msg = f'Ошибка протокола FTP: {e}'

    except Exception as e:
        # Обработка сетевых ошибок (хост недоступен, тайм-аут)
        error_msg = f'Ошибка подключения к "{host}": "{e}"'

    if error_msg:
        logging.error(error_msg)
        result.update({'status': 'error', 'message': error_msg})

    logging.debug('Upload on FTP result: %s', result)

    return result


async def list_files_on_ftp(
        remote_path: str | None = None, config: dict[str, str | int | bool] | None = None) -> list[str]:
    """
    Асинхронно возвращает список путей на FTP-сервере рекурсивно под указанным remote_path.

    :param remote_path: Путь на FTP-сервере. Если None — используется ftp_path из конфигурации.
    :param config: Словарь с параметрами подключения к FTP (опционально).
    :return: Список строк с путями на FTP. При отсутствии пути или ошибке доступа возвращается пустой список.
    """
    cfg = config if config else _get_ftp_config()
    host = cfg.get('ftp_host', '')
    port = int(cfg.get('ftp_port', 21) or 21)
    user = cfg.get('ftp_user', '')
    password = cfg.get('ftp_pass', '')
    path = cfg.get('ftp_path', '')

    if not host or not user or not password:
        logging.error('FTP конфигурация недостаёт: host, user или password не заданы (раздел ftp).')
        return []

    remote_path = path if not remote_path else remote_path

    results: list[str] = []
    try:
        async with aioftp_Client.context(host, port=port, user=user, password=password) as client:
            logging.info('Recursive listing FTP path: %s', remote_path)
            async for path_obj, info in client.list(remote_path, recursive=True):
                results.append(str(path_obj))
    except Exception as e:
        # Логируем и безопасно возвращаем пустой список, если путь не существует или доступ запрещён
        msg = str(e).lower()
        if '550' in msg or 'not found' in msg or 'no such file' in msg:
            logging.warning('FTP path not found or inaccessible: %s', remote_path)
            return []
        logging.exception('FTP listing error for %s: %s', remote_path, e)
        return []

    return results


async def find_matching_files(directory_path: str, filename_pattern: str) -> dict[Path, dict[str, float]]:
    """
    Асинхронно ищет файлы в каталоге по шаблону, используя Path.rglob в отдельном потоке.

    :param directory_path: Корневой каталог для поиска (строка или путь).
    :param filename_pattern: Маска файла (например '*.txt' или '*.csv').
    :return: Словарь, где ключ — Path к файлу, значение — словарь с метаданными:
             {'size': float (байты), 'mtime': float (unix timestamp)}.
    :raises ValueError: если directory_path не существует или не является директорией.
    """
    def _collect_matching_paths() -> list[Path]:
        root_dir = Path(directory_path)
        if not root_dir.exists() or not root_dir.is_dir():
            raise ValueError(f'Указанный каталог не найден или не является директорией: {directory_path}')
        # Рекурсивный поиск файлов, имя файла соответствует pattern
        return [matched_path for matched_path in root_dir.rglob(filename_pattern) if matched_path.is_file()]

    matching_paths = await to_thread(_collect_matching_paths)

    results: dict[Path, dict[str, float]] = {}
    for file_path in matching_paths:
        stats = file_path.stat()
        results[file_path] = {'size': float(stats.st_size), 'mtime': float(stats.st_mtime)}
    return results


async def ftp_main(max_concurrency: int = 1) -> None:
    """
    Основная асинхронная функция демонстрационного сценария:
    - ищет все файлы по шаблону в директории 'incoming'
    - загружает их на FTP с ограничением параллельности
    - выводит список файлов на FTP после загрузки

    :param max_concurrency: Максимальное количество одновременных загрузок (по умолчанию 1).
    :return: None
    """
    # Ищем все файлы *.txt в директории 'incoming'
    matches_files = await find_matching_files('incoming', '*.txt')
    if not matches_files:
        logging.info('No matching files found in directory: incoming/*.txt')
        return

    # Семафор ограничивает количество одновременных задач (например, чтобы не перегрузить FTP)
    sem = Semaphore(max_concurrency)

    async def _upload_with_sem(local_path: Path, remote_path: str) -> None:
        """
        Вспомогательная функция для загрузки одного файла на FTP с ограничением параллельности.

        :param local_path: Path к локальному файлу.
        :param remote_path: Путь на FTP (включая имя файла).
        """
        async with sem:
            try:
                await upload_file_to_ftp(local_path, remote_path)
                logging.info('Uploaded %s -> %s', local_path, remote_path)
            except Exception as e:
                logging.exception('Failed to upload %s: %s', local_path, e)

    # Создаём задачи для загрузки всех найденных файлов
    tasks = [
        create_task(
            _upload_with_sem(local_path, f'/uploads/{Path(local_path).name}')
        )
        for local_path in matches_files.keys()
    ]

    # Дожидаемся завершения всех задач загрузки
    if tasks:
        await gather(*tasks)

    # Получаем список файлов на FTP в директории '/uploads'
    list_paths = await list_files_on_ftp('/uploads')
    for path in list_paths:
        print(path)


if __name__ == '__main__':
    from asyncio import run as aio_run, gather, create_task, Semaphore, to_thread
    aio_run(ftp_main())
