# __author__ = 'InfSub'
# __contact__ = 'ADmin@TkYD.ru'
# __copyright__ = 'Copyright (C) 2024-2025, [LegioNTeaM] InfSub'
# __date__ = '2026/02/19'
# __deprecated__ = False
# __email__ = 'ADmin@TkYD.ru'
# __maintainer__ = 'InfSub'
# __status__ = 'Production'  # 'Production / Development'
# __version__ = '1.9.1.2'

from io import StringIO
from asyncio import gather as aio_gather, create_task as aio_create_task, Task as aio_Task, to_thread as aio_to_thread
from typing import Sequence, Any

from pandas import read_csv as pd_read_csv, concat as pd_concat, Series, DataFrame, notna
from decimal import Decimal, ROUND_HALF_UP
from aiofiles import open as aio_open
from pathlib import Path
from re import compile as re_compile, sub as re_sub, IGNORECASE
from datetime import datetime, timedelta
from shutil import copy as shutil_copy
from argparse import ArgumentParser

from config import OverlayConfig
from load_to_ftp import upload_file_to_ftp
from send_message import send_telegram_message, Emoji
from execution_time import logging_execution_time
from logger import logging


logging = logging.getLogger(__name__)


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('--config', nargs='*', help='Имя конфигурации или список конфигураций')
    return parser.parse_args()


async def check_file_modification(file_path: Path) -> None:
    """
    Асинхронная функция для проверки времени последней модификации файла и отправки уведомления в случае
    превышения установленного лимита времени неактивности.

    :param file_path: Путь к файлу, который необходимо проверить на предмет последней модификации.
    :ptype file_path: Path

    Функция выполняет следующие действия:
        1. Получает время последней модификации файла.
        2. Вычисляет разницу времени между текущим моментом и временем последней модификации файла.
        3. Формирует строку с описанием времени, прошедшего с момента модификации.
        4. Логирует информацию о времени последней модификации файла.
        5. Если файл не изменялся дольше, чем установлено в лимите времени неактивности, отправляет предупреждение
            в лог и уведомление в Telegram.

    :return: None
    """
    cfg: dict[str: int, str] = OverlayConfig().get_config('inactivity', 'ftp', 'log')
    # Получаем время последней модификации файла
    file_mod_time: datetime = datetime.fromtimestamp(Path(file_path).stat().st_mtime)

    current_time: datetime = datetime.now()
    file_mod_delta: timedelta = current_time - file_mod_time

    # Определение времени, прошедшего с момента модификации
    days: int = file_mod_delta.days
    hours, remainder = divmod(file_mod_delta.seconds, 3600)
    minutes, _ = divmod(remainder, 60)

    time_components: list[str] = []

    if days > 0:
        time_components.append(f'{days} days')
    if hours > 0:
        time_components.append(f'{hours} hours')
    time_components.append(f'{minutes} minutes')

    time_description: str = ', '.join(time_components)
    tg_msg: str = (
        'The file:\n```{}```\nwas modified at: `{}`,\n*{}* ago.'
        .format(file_path, file_mod_time.strftime(cfg.get('log_date_format')), time_description)
    )

    # Проверяем разницу во времени
    time_difference: bool = file_mod_delta <= timedelta(hours=cfg.get('inactivity_limit_hours'))
    if time_difference:
        logging.info(re_sub(r'\n+', ' ', tg_msg).replace('```', '"').replace('*', '"'))
    else:
        tg_msg: str = (
            'The file has not been modified for more than *{}* hours.\n\n{}'
            .format(cfg['inactivity_limit_hours'], tg_msg)
        )

        logging.warning(re_sub(r'\n+', ' ', tg_msg).replace('```', '"').replace('*', '"'))

    tg_msg = '*{}*:\n\n{}'.format(cfg.get('ftp_host', ''), tg_msg)
    # Отправляем уведомление в Telegram
    await send_telegram_message(tg_msg, str(Emoji.CHECK_MARK if time_difference else Emoji.CROSS_MARK))


@logging_execution_time()
async def read_file_lines(file_path: Path) -> list[str] | None:
    """
    Асинхронная функция для чтения строк из файла.

    :param file_path: Путь к файлу, строки которого необходимо прочитать.
    :ptype file_path: Path

    Функция выполняет следующие действия:
        1. Открывает файл в асинхронном режиме для чтения с указанной в .cfg кодировкой, по умолчанию: 'utf-8'.
        2. Читает все строки из файла.
        3. Возвращает список строк, если файл не пустой. Если файл пуст, возвращает None.

    Обработка исключений:
        - Логирует ошибку, если файл не найден.
        - Логирует ошибку, если доступ к файлу запрещен.
        - Логирует общую ошибку, если происходит другая неисправность во время чтения.

    :return: Список строк из файла или None, если файл пуст или произошла ошибка.
    :rtype: list[str] | None
    """
    cfg: dict[str: str] = OverlayConfig().get_config('csv')
    encoding = cfg.get('csv_file_encoding', 'utf-8')
    logging.debug('CSV file: "%s" encoding: "%s"', file_path, encoding)

    try:
        async with aio_open(file_path, mode='r', encoding=encoding) as file:
            lines = await file.readlines()
            return lines if lines else None
    except FileNotFoundError:
        logging.error('File not found: "%s"', file_path)
    except PermissionError:
        logging.error('Access denied for file: "%s"', file_path)
    except Exception as e:
        logging.error('An error occurred while reading "%s": "$s"', file_path, str(e))
    return None


@logging_execution_time()
async def process_headers(header_line: str, sep: str) -> list[str]:
    """
    Асинхронная функция для обработки строки заголовков CSV и фильтрации пустых заголовков.

    :param header_line: Строка, содержащая заголовки, разделенные заданным разделителем.
    :ptype header_line: str
    :param sep: CSV разделитель.
    :ptype sep: str

    Функция выполняет следующие действия:
        1. Удаляет начальные и конечные пробелы в строке заголовков.
        2. Разделяет строку заголовков на отдельные заголовки, используя разделитель, указанный в конфигурации CSV.
        3. Фильтрует и возвращает список заголовков, исключая те, которые содержат только пробелы.

    :return: Список непустых заголовков.
    :rtype: list[str]
    """
    # # await aio_sleep(0)  # Предполагается, что это асинхронная пауза для имитации работы
    # cfg: dict[str: str] = OverlayConfig().get_config('csv')
    # headers = header_line.strip().split(cfg.get('csv_separator_out', ';'))  # Разделяем строку заголовков
    headers = header_line.strip().split(sep)  # Разделяем строку заголовков
    return [header for header in headers if header.strip()]  # Возвращаем непустые заголовки


@logging_execution_time()
async def load_header_template(template_path: Path) -> list[str]:
    """
    Асинхронно загружает и обрабатывает шаблон заголовка CSV из файла.

    Чтение и обработка:
    - Асинхронно считывает все строки файла через `read_file_lines`.
    - Если файл пуст или не существует — возвращает пустой список.
    - Определяет разделитель в первой строке через `guess_sep` и сравнивает его
      с настройкой `csv_separator_out` из конфигурации.
    - Если разделитель отличается — логгирует предупреждение.
    - Обрабатывает первую строку как заголовок через `process_headers` и
      возвращает результат.

    :param template_path: Путь к файлу шаблона заголовков.
    :type template_path: Path
    :return: Список обработанных заголовков; пустой список при отсутствии данных.
    :rtype: list[str]
    """
    cfg: dict[str, str] = OverlayConfig().get_config('csv')
    sep: str = cfg.get('csv_separator_out', ';')
    lines: list[str] = await read_file_lines(template_path)
    if not lines:
        return []

    detected_sep: str = guess_sep(lines[0])
    if detected_sep != sep:
        log_fmt = 'В шаблоне заголовков обнаружен разделитель "%s", но в настройках указан "%s"!'
        logging.warning(log_fmt, detected_sep, sep)
        tg_msg: str = log_fmt % (detected_sep, sep)  # явная строка для отправки в Telegram
        await send_telegram_message(tg_msg, str(Emoji.EXCLAMATION_MARK))

    return await process_headers(lines[0], sep=sep)


def guess_sep(line: str, candidates: str = ';,|\t') -> str:
    """
    Определяет наиболее вероятный разделитель в строке.

    :param line: Строка, в которой нужно определить разделитель.
    :param candidates: Строка символов-кандидатов для разделителя.
    :return: Символ разделителя с наибольшим количеством вхождений.
    """
    counts = {c: line.count(c) for c in candidates}
    return max(counts, key=counts.get)


# TODO: def read_csv_async
@logging_execution_time()
async def read_csv_async(file_path: Path, sep: str | None = None, encoding: str | None = None) -> DataFrame | None:
    """
    Асинхронно читает CSV-файл в DataFrame.

    :param file_path: путь к CSV-файлу.
    :param sep: разделитель (по умолчанию ';').
    :param encoding: кодировка файла (по умолчанию 'utf-8').

    :return: DataFrame или None, если файл не существует или пуст/ошибка чтения.
    """
    cfg: dict[str: str] = OverlayConfig().get_config('csv')
    sep = sep if sep else cfg.get('csv_separator_in', ';')
    encoding = encoding if encoding else cfg.get('csv_file_encoding', 'utf-8')

    if not file_path.exists() or not file_path.is_file():
        logging.warning('File not found or not a file: "%s"', file_path)
        return None

    def _read() -> DataFrame | None:
        try:
            df = pd_read_csv(file_path, sep=sep, encoding=encoding)
            if df.empty:
                return None
            return df
        except Exception as e:
            logging.exception('Failed to read CSV "%s": "%s"', file_path, e)
            return None

    return await aio_to_thread(_read)


@logging_execution_time()
async def read_csv_async_old(file_path: Path) -> DataFrame | None:
    """
    Асинхронная функция для чтения CSV-файла и возвращения DataFrame, содержащего только столбцы
    с корректными заголовками.

    :param file_path: Путь к CSV-файлу, который необходимо прочитать.
    :ptype file_path: Path

    :return: DataFrame, содержащий данные из файла с корректными заголовками, или None, если файл пуст.
    :rtype: DataFrame | None

    Функция выполняет следующие действия:
        1. Логирует информацию о начале чтения файла.
        2. Асинхронно считывает строки из файла.
        3. Проверяет, пуст ли файл, и логирует предупреждение, если это так.
        4. Обрабатывает первую строку для извлечения корректных заголовков.
        5. Обрабатывает оставшиеся строки данных, удаляя лишние пробелы.
        6. Объединяет очищенные строки данных.
        7. Создает DataFrame из очищенных данных, используя только непустые заголовки для чтения.
    """
    cfg: dict[str: str] = OverlayConfig().get_config('csv')
    sep = cfg.get('csv_separator_in', ';')
    logging.info(f'Reading file: {file_path}.')
    lines = await read_file_lines(file_path)
    if not lines:
        logging.warning(f'File is empty: {file_path}')
        return None

    # Обрабатываем первую строку (заголовки)
    valid_headers = await process_headers(lines[0], sep=sep)
    logging.debug('valid_headers from file %s: %s', file_path, valid_headers)

    # Обрабатываем остальные строки
    data_lines = lines[1:]

    cleaned_data = []
    for line in data_lines:
        # Удаляет символы справа, которые входят в набор {sep, '\n'} (не актуально).
        trimmed_line = sep.join([item.strip() for item in line.rstrip(f'{sep}\n').split(sep)])
        cleaned_data.append(trimmed_line)
    # Объединяем строки обратно в одну строку
    content = '\n'.join(cleaned_data)

    # Читаем данные в DataFrame, используя только непустые заголовки
    df = pd_read_csv(
        StringIO(content), sep=sep, names=valid_headers, usecols=valid_headers, header=None)

    return df


@logging_execution_time()
async def sort_columns_by_template(df: DataFrame, header_template: list[str]) -> DataFrame:
    """
    Асинхронная функция для фильтрации и сортировки столбцов DataFrame на основе заданного шаблона заголовков.

    :param df: DataFrame, столбцы которого необходимо отсортировать и отфильтровать.
    :ptype df: DataFrame
    :param header_template: Список строк с именами столбцов, определяющий порядок и фильтрацию столбцов DataFrame.
    :ptype header_template: list[str]

    Функция выполняет следующие действия:
        1. Использует шаблон заголовков для фильтрации столбцов DataFrame.
        2. Сортирует столбцы в порядке, указанном в шаблоне заголовков.
        3. Возвращает новый DataFrame, столбцы которого соответствуют заданному шаблону.

    Важно:
        - Столбцы, отсутствующие в DataFrame, но указанные в шаблоне, будут добавлены как пустые.
        - Столбцы, отсутствующие в шаблоне, будут удалены из итогового DataFrame.

    :return: Новый DataFrame с отсортированными и отфильтрованными столбцами.
    :rtype: DataFrame
    """
    # await aio_sleep(0)
    # Фильтруем и сортируем столбцы DataFrame по шаблону
    sorted_df = df.reindex(columns=header_template)
    return sorted_df


def _safe_sum(series: Series, decimal_places: int | None = None) -> float:
    """
    Суммирует значения в серии с корректной обработкой десятичных знаков.

    :param series: pandas.Series с числовыми значениями (возможно с NaN).
    :param decimal_places: количество знаков после запятой для округления (если None — без округления).

    :return: float — итоговая сумма (округлённая при необходимости).
    """
    total = Decimal(0)
    for item in series.dropna():
        total += Decimal(str(item))

    if decimal_places is not None:
        total = total.quantize(Decimal(10) ** -int(decimal_places), rounding=ROUND_HALF_UP)

    return float(total)


# def _safe_sum(series: Series, decimal_places: int | None = None) -> float:
#     """
#     Вычисляет сумму значений в серии данных с возможностью округления результата до указанного количества
#     десятичных знаков.
#
#     :param series: Серия данных, содержащая числовые значения, которые необходимо суммировать.
#     :ptype series: Series
#     :param decimal_places: Количество знаков после запятой, до которого нужно округлить итоговую сумму.
#                            Если None, то округление не выполняется.
#     :ptype decimal_places: int | None
#
#     :return: Итоговая сумма значений в серии, округленная до указанного количества десятичных знаков (если применимо).
#     :rtype: Float
#
#     Функция выполняет следующие действия:
#         1. Инициализирует переменную total, представляющую собой сумму, с нулевым значением типа Decimal.
#         2. Перебирает значения в серии, исключая 'NaN' значения, и добавляет их к общей сумме, преобразуя каждое
#           значение в тип Decimal.
#         3. Если указано количество десятичных знаков, округляет итоговую сумму до заданной точности с использованием
#           метода округления ROUND_HALF_UP.
#         4. Преобразует итоговую сумму из типа Decimal в тип float и возвращает результат.
#     """
#     total = Decimal(0)
#     for item in series.dropna():
#         total += Decimal(str(item))
#
#     if decimal_places is not None:
#         # Округление до указанного количества знаков после запятой
#         total = total.quantize(Decimal(10) ** -decimal_places, rounding=ROUND_HALF_UP)
#
#     return float(total)


def _extract_width_from_row(
    row: Series,
    width_col: str,
    sku_col: str,
    name_col: str,
    source_col: str,
    max_width: float,
) -> tuple[float | None, str | None]:
    """
    Извлекает значение ширины из строки и формирует сообщение для уведомления, если значение вне допустимого диапазона.

    :param row: pandas.Series — строка данных.
    :param width_col: имя колонки, содержащей ширину.
    :param sku_col: имя колонки с артикулом/штрихкодом.
    :param name_col: имя колонки с наименованием товара.
    :param source_col: имя колонки с источником (имя файла).
    :param max_width: максимально допустимая ширина (включительно).

    :return: кортеж (width, tg_message). width — float или None, tg_message — строка уведомления или None.
    """
    width: float | None = None

    try:
        if width_col in row and notna(row[width_col]):
            val = row[width_col]
            if isinstance(val, (int, float)):
                width = float(val)
            else:
                try:
                    width = float(str(val).strip())
                except Exception as e:
                    logging.debug('Error extracting width from row: "%s"', e)
                    width = None
    except Exception as e:
        logging.debug('Error extracting width from row: "%s"', e)
        width = None

    if width is None:
        return None, None

    if width <= 0 or width > max_width:
        code = row.get(sku_col, '<unknown>')
        name = row.get(name_col, '')
        source = row.get(source_col, '')
        tg_msg = (
            f'Width alert for {code}: value={width} (allowed 0..{max_width}). '
            f'Name="{name}". Source="{source}"'
        )
        return width, tg_msg

    return width, None


# def _extract_width(row: Series, tasks: list[aio_Task]) -> float | None:
#     """
#     Извлекает значение ширины из строки данных и проверяет его валидность.
#
#     :param row: Строка данных (pandas.Series), содержащая информацию о продукте,
#                 включая ширину и описание.
#     :param tasks: Список асинхронных задач (asyncio.Task), который будет дополнен
#                   задачами отправки уведомлений при обнаружении ошибки.
#     :return: Извлечённое значение ширины (float) или None, если значение отсутствует
#              или некорректно.
#
#     Алгоритм работы:
#         1. Проверяет наличие и тип данных в поле ширины ('Packing.Ширина').
#            Если значение является числом (int, float), оно извлекается.
#         2. Если значение ширины отсутствует, пытается извлечь числовое значение
#            из поля описания ('Description'), используя регулярное выражение для поиска чисел.
#         3. Проверяет, находится ли извлечённое значение ширины в допустимом диапазоне
#            (0 < value <= cfg['max_width']).
#         4. Если значение не соответствует допустимому диапазону, генерирует предупреждающее
#            сообщение и создаёт задачу для отправки уведомления в Telegram.
#         5. Возвращает извлечённое значение ширины или None, если значение не удалось
#            извлечь или оно некорректно.
#     """
#     cfg: dict[str: int | str] = OverlayConfig().get_config('datas')
#     value: float | None = None
#     key_width: str = 'Ширина'
#     # key_description: str = 'Description'
#
#     if notna(row[key_width]) and isinstance(row[key_width], (int, float)):
#         value = row[key_width]
#     # elif isinstance(row[key_description], str) and row[key_description]:
#     #     found_value = search(r'\d+', row[key_description])
#     #     value = float(found_value.group()) if found_value else None
#
#     if value is not None:
#         if not 0 < value <= cfg['datas_max_width']:
#             message = (f'For product "{row['Номенклатурный номер']}", the width value "{value}" was outside the '
#                        f'acceptable range.')
#             message += f'Source: "{row['Source_File']}".'
#             logging.warning(message)
#             tasks.append(aio_create_task(send_telegram_message(message)))
#
#     return value


def extract_compound(row: Series, compound_col: str) -> str | None:
    """
    Извлекает значение состава ткани из строки DataFrame.

    Функция безопасно получает значение из указанной колонки,
    проверяет, что оно является непустой строкой, и возвращает
    очищенный вариант. В случае ошибки или отсутствия данных
    возвращает None.

    :param row: Строка DataFrame в виде pandas.Series.
    :param compound_col: Имя колонки, содержащей состав ткани.
    :return: Очищенная строка состава или None, если значение отсутствует или не является строкой.
    """
    try:
        val = row.get(compound_col)
        if isinstance(val, str):
            cleaned = val.strip()
            if cleaned:
                return cleaned
    except Exception as e:
        logging.debug('Error extracting compound from row: %s', e)

    return None


def safe_extract(row: Series, col: str) -> str | None:
    """
    Безопасная обёртка над extract_compound.

    Перехватывает любые исключения, возникающие при обработке строки,
    логирует их и возвращает None, чтобы не прерывать обработку всего DataFrame.

    :param row: Строка DataFrame.
    :param col: Имя колонки, содержащей состав ткани.
    :return: Результат extract_compound или None при ошибке.
    """
    try:
        return extract_compound(row, col)
    except Exception as e:
        logging.exception('Failed to extract compound for row %s: %s', row.name, e)
        return None


# def extract_compound(row: Series) -> str | None:
#     """
#     Функция для извлечения информации о составе упаковки из столбца 'Packing.Состав' или 'AdditionalDescription'.
#
#     :param row: Строка данных, содержащая столбцы 'Packing.Состав' и 'AdditionalDescription'.
#     :ptype row: Series
#
#     :return: Извлеченное значение состава или None, если значение не удалось извлечь или оно некорректно.
#     :rtype: str | None
#
#     Функция выполняет следующие действия:
#         1. Проверяет, является ли значение в столбце 'Packing.Состав' строкой и не пусто ли оно.
#         2. Если условие из пункта 1 выполняется, возвращает значение из 'Packing.Состав'.
#         3. В противном случае проверяет, является ли значение в 'AdditionalDescription' строкой и не пусто ли оно.
#         4. Если условие из пункта 3 выполняется, возвращает значение из 'AdditionalDescription'.
#         5. Если ни одно из условий не выполняется, возвращает None.
#     """
#     value: str | None = None
#     key_compound: str = 'Состав ткани'
#     # key_description: str = 'AdditionalDescription'
#
#     if isinstance(row[key_compound], str) and row[key_compound]:
#         value = row[key_compound] if row[key_compound] else None
#     # elif isinstance(row[key_description], str) and row[key_description]:
#     #     value = row[key_description] if row[key_description] else None
#
#     return value


@logging_execution_time()
async def merge_csv_files(files_dict: dict[str, Path]) -> DataFrame | None:
    """
    Асинхронно объединяет несколько CSV-файлов в один DataFrame с обработкой и проверками.

    Конфигурация колонок и поведение берутся из OverlayConfig('datas'):
      - datas_col_sku         : имя колонки с ключом товара (по умолчанию 'Номенклатурный номер')
      - datas_col_quantity    : имя колонки, которую нужно суммировать (по умолчанию 'Остаток')
      - datas_col_width       : имя колонки с шириной (по умолчанию 'Ширина')
      - datas_col_compound    : имя колонки с составом (по умолчанию 'Состав ткани')
      - datas_max_width       : максимальная допустимая ширина (по умолчанию 200)
      - datas_decimal_places  : количество знаков при суммировании (по умолчанию 2)

    :param files_dict: словарь идентификатор -> Path

    :return: агрегированный DataFrame или None
    """
    if not files_dict:
        logging.warning('No files provided to merge_csv_files.')
        return None

    if len(files_dict) == 1:
        logging.info('Single file provided; processing without special-case logic.')

    cfg: dict[str: int | str] = OverlayConfig().get_config(
        'datas',
        # 'csv'
    )

    # sep: str = cfg.get('csv_separator_in')
    # encoding: str = cfg.get('csv_file_encoding')

    # Читаем имена колонок из конфига со значениями по умолчанию
    sku_col = cfg.get('datas_col_sku', 'Номенклатурный номер')
    quantity_col = cfg.get('datas_col_quantity', 'Остаток')
    width_col = cfg.get('datas_col_width', 'Ширина')
    compound_col = cfg.get('datas_col_compound', '')

    max_width = float(cfg.get('datas_max_width', 200))
    decimals = int(cfg.get('datas_decimal_places', 2))

    # 1) Чтение файлов
    # TODO: read_csv_async
    # read_tasks = [read_csv_async(path, sep=sep, encoding=encoding) for path in files_dict.values()]
    #
    # try:
    #     dataframes = await aio_gather(*read_tasks)
    # except Exception as e:
    #     logging.exception('Unexpected error while reading CSV files: %s', e)
    #     return None

    dataframes = await aio_gather(*[read_csv_async_old(file_path) for file_path in files_dict.values()])
    dataframes = [df for df in dataframes if df is not None]

    # 2) Фильтрация валидных DataFrame
    valid_dfs: list[DataFrame] = []
    for df, (key, path) in zip(dataframes, files_dict.items()):
        if isinstance(df, DataFrame) and not df.empty:
            df = df.copy()
            # TODO: Проверить, нужна ли вообще тут колонка: Source_File
            # Добавляем колонку Source_File для трассировки (если ещё нет)
            if 'Source_File' not in df.columns:
                df['Source_File'] = key
            valid_dfs.append(df)
        else:
            logging.warning('Invalid or empty dataframe from "%s"', path)

    if not valid_dfs:
        logging.warning('No valid dataframes to merge.')
        return None

    # 3) Объединение
    combined_df = pd_concat(valid_dfs, ignore_index=True)
    logging.info('Successfully merged %d dataframes (rows=%d).', len(valid_dfs), len(combined_df))

    # 4) Проверка ширины и подготовка задач уведомлений
    notify_tasks: list[aio_Task] = []
    for idx, row in combined_df.iterrows():
        try:
            width, tg_msg = _extract_width_from_row(row, width_col, sku_col, sku_col, 'Source_File', max_width)
        except Exception as e:
            logging.exception('Error while extracting width for row "%s": "%s"', idx, e)
            continue

        # Записываем извлечённую ширину в DataFrame (если нужно)
        try:
            combined_df.at[idx, width_col] = width
        except Exception as e:
            logging.debug('Failed to set width for row "%s": "%s"', idx, e)

        if tg_msg:
            logging.warning('Width out of bounds: "%s"', tg_msg)
            if callable(send_telegram_message):
                try:
                    task = aio_create_task(send_telegram_message(tg_msg))
                    notify_tasks.append(task)
                except Exception as e:
                    logging.exception('Failed to schedule Telegram notification: %s', e)

    # Корректная обработка результатов уведомлений: собираем результаты и логируем ошибки
    if notify_tasks:
        results = await aio_gather(*notify_tasks, return_exceptions=True)
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                logging.exception('Telegram notification task "%d" failed: "%s"', i, res)
            else:
                logging.debug('Telegram notification task "%d" succeeded: "%s"', i, res)

    # 5) Извлечение состава (опционально)
    if compound_col:
        try:
            # combined_df[compound_col] = combined_df.apply(lambda r: extract_compound(r, compound_col), axis=1)
            combined_df[compound_col] = combined_df.apply(lambda r: safe_extract(r, compound_col), axis=1)
        except Exception as e:
            logging.exception('Failed to extract compound column: "%s"', e)

    # 6) Группировка и агрегация
    key_col = sku_col
    if key_col not in combined_df.columns:
        logging.error('Column "%s" not found in combined dataframe.', key_col)
        return None

    agg_map: dict[str, Any] = {}
    if quantity_col in combined_df.columns:
        agg_map[quantity_col] = lambda s: _safe_sum(s, decimals)

    # Для остальных колонок — first
    for col in combined_df.columns:
        if col == key_col or col == quantity_col:
            continue
        agg_map[col] = 'first'

    try:
        grouped_df = combined_df.groupby(key_col, as_index=False).agg(agg_map)
    except Exception as e:
        logging.exception('Failed to group/aggregate dataframe: "%s"', e)
        return None

    return grouped_df


# @log_async_execution_time()
# async def merge_csv_files(files_dict: dict[str, Path]) -> DataFrame | None:
#     """
#     Асинхронная функция для объединения нескольких CSV-файлов в один DataFrame с обработкой и фильтрацией данных.
#
#     :param files_dict: Словарь, где ключи - это названия файлов, а значения - пути к CSV-файлам.
#     :ptype files_dict: dict[str, Path]
#
#     Функция выполняет следующие действия:
#         1. Асинхронно читает данные из указанных CSV-файлов и создает список DataFrame.
#         2. Фильтрует невалидные DataFrame и выводит предупреждение в лог, если ни один из них не был валидным.
#         3. (DISABLED) Обрабатывает каждый DataFrame, добавляя новую колонку с префиксом 'Storage_' и удаляя
#             колонку 'Packing.МестоХранения'.
#         4. Объединяет все обработанные DataFrame в один общий DataFrame и выводит сообщение об успешном объединении.
#         5. (DISABLED) Заменяет значения в колонке 'Наименование' на заданное в переменной окружения
#             'name_of_product_type', если она указана.
#         6. (DISABLED) Заполняет пропуски в столбцах, начинающихся с 'Storage_' пустыми строками.
#         7. Извлекает и проверяет значения ширины для каждого товара. Отправляет уведомление в Telegram, если
#             значение выходит за допустимые пределы.
#         8. Извлекает состав из колонок 'Состав ткани'.
#         9. Группирует данные по штрих-коду ('Номенклатурный номер'), суммируя значения в колонках 'Остаток'
#             и 'Packing.СвободныйОстаток' и объединяя значения в других колонках.
#
#     :return: Возвращает объединенный и обработанный DataFrame или None, если не удалось объединить данные.
#     :rtype: DataFrame | None
#     """
#     cfg: dict[str: int | str] = OverlayConfig().get_config('datas')
#     dataframes = await aio_gather(*[read_csv_async(file_path) for file_path in files_dict.values()])
#     dataframes = [df for df in dataframes if df is not None]
#
#     if not dataframes:
#         logging.warning('No valid dataframes to merge.')
#         return None
#
#     # Создаем комбинированный DataFrame
#     combined_data = []
#     for df, file_name in zip(dataframes, files_dict.keys()):
#         # df['Source_File'] = file_name  # Добавляем имя файла как новый столбец
#         # df[f'Storage_{file_name}'] = df['Packing.МестоХранения'].fillna('').astype(str).apply(lambda x: f'{x}')
#         # df.drop(columns=['Packing.МестоХранения'], inplace=True)
#         combined_data.append(df)
#
#     # Объединение всех DataFrame
#     combined_df = pd_concat(combined_data, ignore_index=True)
#     logging.info('Successfully merged dataframes.')
#
#     # # Обновление столбца "Наименование" только в случае, если new_name_value определено и не пусто
#     # message = 'The value of the cells in the "Наименование" column has'
#     # if cfg['datas_name_of_product_type']:
#     #     combined_df['Наименование'] = cfg['datas_name_of_product_type']
#     #     logging.warning(
#     #         f'{message} been replaced with "{cfg['datas_name_of_product_type']}"')
#     # else:
#     #     logging.warning(
#     #         f'{message} not been changed, the "CSV_NEW_NAME_VALUE" constant is empty.')
#
#     tasks: list[aio_Task] = []  # Список для задач
#
#     # # Обработка столбца 'Packing.МестоХранения'
#     # for column in combined_df.columns:
#     #     if column.startswith('Storage_'):
#     #         combined_df[column] = combined_df[column].fillna('').astype(str)
#
#     combined_df['Ширина'] = combined_df.apply(lambda row: extract_width(row, tasks), axis=1)
#
#     # Дожидаемся выполнения всех задач
#     await aio_gather(*tasks)
#
#     combined_df['Состав ткани'] = combined_df.apply(extract_compound, axis=1)
#
#     # Получаем список всех столбцов для агрегации
#     all_columns = combined_df.columns.tolist()
#
#     # Определяем столбцы для агрегации с помощью first
#     first_columns = [col for col in all_columns if col not in ['Остаток']]
#
#     # Группировка и агрегация
#     grouped_df = combined_df.groupby('Номенклатурный номер', as_index=False).agg(
#         {
#             'Остаток': lambda x: safe_sum(x, cfg['datas_decimal_places']),
#             **{col: 'first' for col in first_columns},
#         }
#     )
#
#     return grouped_df


@logging_execution_time()
async def save_dataframe_to_csv(df: 'DataFrame', output_path: Path) -> None:
    """
    Асинхронная функция для сохранения объекта DataFrame в CSV файл.

    :param df: DataFrame, который необходимо сохранить.
    :ptype df: DataFrame
    :param output_path: Путь, по которому будет сохранен CSV файл.
    :ptype output_path: Path

    Функция выполняет следующее действие:
        - Сохраняет переданный DataFrame в файл формата CSV по указанному пути, используя разделитель, заданный
        в переменной окружения 'csv_separator_out'.
    """
    cfg: dict[str: int | str] = OverlayConfig().get_config('csv')
    df.to_csv(output_path, index=False, sep=cfg.get('csv_separator_out', ';'))


async def find_matching_files(directory: Path | str, pattern: str) -> dict[str, Path]:
    """
    Асинхронная функция для поиска файлов в указанной директории, соответствующих заданному шаблону.

    :param directory: Директория, в которой необходимо искать файлы.
    :type directory: Path | str
    :param pattern: Шаблон в виде регулярного выражения, по которому производится поиск файлов.
    :type pattern: str

    :return: Словарь, где ключи — это имена файлов (из группы 1 шаблона), a значения — их полные пути Path.
    :rtype: dict
    Функция выполняет следующие действия:
        1. Обходит все файлы в указанной директории и поддиректориях.
        2. Проверяет каждый файл на соответствие заданному шаблону.
        3. Если файл соответствует шаблону, добавляет его имя и полный путь в словарь результатов.
    """
    files_dict: dict[str, Path] = {}
    base = Path(directory)

    if not base.exists() or not base.is_dir():
        return files_dict

    regex = re_compile(pattern, IGNORECASE)

    for path in base.rglob('*'):
        if path.is_file():
            m = regex.match(path.name)
            if m:
                file_name = m.group(1) if m.groups() else path.stem
                files_dict[file_name] = path.resolve()

    return files_dict


def get_valid_file_name() -> str | None:
    """
    Функция для получения корректного имени файла из переменных окружения.

    Функция сначала пытается получить имя файла из переменной окружения 'csv_file_name'.
    Если переменная пуста, она пытается получить имя файла из 'csv_file_name_for_ftp'.
    Если обе переменные пусты, функция возвращает None.

    :return: Имя файла в виде строки или None, если ни одна из переменных окружения не содержит имени файла.
    :rtype: str | None
    """
    cfg: dict[str: int | str] = OverlayConfig().get_config('csv')
    csv_file_name = cfg.get('csv_file_name', '')
    csv_file_name_for_ftp = cfg.get('csv_file_name_for_ftp', '')

    if csv_file_name:
        return csv_file_name
    elif csv_file_name_for_ftp:
        return csv_file_name_for_ftp
    else:
        return None


async def copy_file(src: Path, dst: Path) -> None:
    """
    Асинхронная функция для копирования файла из одного места в другое.

    Функция пытается скопировать файл из указанного источника в указанное место назначения.
    В случае успешного копирования, логируется информационное сообщение.
    Если копирование не удалось, логируется сообщение об ошибке с описанием исключения.

    :param src: Путь к исходному файлу, который необходимо скопировать.
    :ptype src: Path
    :param dst: Путь, куда должен быть скопирован файл.
    :ptype dst: Path
    """
    try:
        shutil_copy(src, dst)
        logging.info(f'File copied from "{src}" to "{dst}".')
    except Exception as e:
        logging.error(f'Failed to copy file from "{src}" to "{dst}": {e}.')


@logging_execution_time()
async def process_and_save_all_csv(header_template_path: Path) -> None:
    """
    Асинхронная функция для обработки и сохранения CSV файлов. Она выполняет поиск файлов, соответствующих
    заданному шаблону, объединяет их, сортирует столбцы в соответствии с заданным шаблоном заголовков и
    сохраняет результат в новый CSV файл.

    :param header_template_path: Путь к файлу с шаблоном заголовка, который используется для сортировки столбцов.
    :ptype header_template_path: Path

    Функция выполняет следующие шаги:
        1. Загружает шаблон заголовка для сортировки столбцов.
        2. Ищет файлы, соответствующие заданному шаблону имени файла в указанной директории.
        3. Логирует количество найденных файлов.
        4. Объединяет найденные файлы в один DataFrame, если они найдены.
        5. Проверяет время последней модификации каждого файла.
        6. Для каждого файла:
            - Копирует объединенные данные.
            - Переименовывает столбец, представляющий место хранения, если он существует.
            - Удаляет все столбцы, начинающиеся с 'Storage_'.
            - Сортирует столбцы по загруженному шаблону заголовка.
            - Генерирует корректное имя для нового CSV файла и сохраняет его.
            - Логирует путь сохраненного файла.
            - Если указано, копирует файл в другое место для проверки.
        7. Логирует предупреждения в случае отсутствия данных для сохранения или если не удалось найти файлы по шаблону.
        8. Логирует предупреждения в случае отсутствия ожидаемого столбца в данных.

    :return: None
    """
    conf: dict[str, int | str] = OverlayConfig().get_config('csv', 'ftp')

    # Проверяем, существует ли локальный файл
    if header_template_path.is_file():
        logging.info(f'Header template file found: "%s".', header_template_path)
        header_template = await load_header_template(header_template_path)
    else:
        msg = 'Header template file not found'
        logging.error('%s: "%s".', msg, header_template_path)

        tg_msg = (
            f'{conf.get('ftp_host', '')}:\n\n'
            f'*{msg}*.\n\n'
            f'File:\n'
            f'```LocalPath:\n{header_template_path}```\n\n'
            f'Status: *{'error'.upper()}*'
        )
        await send_telegram_message(tg_msg, str(Emoji.CROSS_MARK))

        return

    files_dict = await find_matching_files(Path(conf.get('csv_path_directory', '')), conf.get('csv_file_pattern', ''))
    len_files = len(files_dict)
    msg = f'Found "{len_files}" files matching the pattern'
    files_string = ''.join(f'```{key.upper()}\n{value}```\n' for key, value in files_dict.items())
    merged_result = False

    logging.info(f'{msg}.') if len_files else logging.warning(f'{msg}.')
    tg_msg = (
        f'{conf.get('ftp_host', '')}:\n\n'
        f'{msg}:\n'
        f'```Pattern:\n{conf.get('csv_file_pattern', '')}```\n\n'        
        f'{'Files:\n' if len_files else ''}'
        f'{files_string}'
        f'Status: *{('found' if len_files else 'error').upper()}*'
    )
    await send_telegram_message(
        tg_msg, str(Emoji.CHECK_MARK) if len_files >= conf.get('csv_files_min_number', 2) else str(Emoji.CROSS_MARK))

    csv_file_name = get_valid_file_name()

    if files_dict:
        merged_df = await merge_csv_files(files_dict=files_dict)

        if merged_df is not None:
            for file_name, file_path in files_dict.items():
                await check_file_modification(file_path=file_path)

                current_df = merged_df.copy()
                place_columns = [col for col in current_df.columns if col.startswith('Storage_')]
                current_df.drop(columns=place_columns, inplace=True)

                current_df = await sort_columns_by_template(current_df, header_template)

                if csv_file_name:
                    output_path = Path(file_path.parent, csv_file_name)
                    await save_dataframe_to_csv(current_df, output_path)
                    logging.info('Saved merged file to "%s"', output_path)

                    csv_file_name_for_checker = conf.get('csv_file_name_for_checker', '')
                    if csv_file_name_for_checker:
                        checker_path = Path(file_path.parent, csv_file_name_for_checker)
                        await copy_file(src=output_path, dst=checker_path)
                else:
                    logging.warning('The CSV_FILE_NAME_FOR_FTP parameter for file "%s" is empty.', file_name)
                # else:
                #     logging.warning(f'Missing expected column "%s" for file "%s".', place_column, file_name)

            msg = f'{len_files} CSV files merged completed successfully'
            logging.info(f'{msg}.')
            merged_result = True
        else:
            msg = f'No data to save after merging'
            logging.warning(f'{msg}.')
    else:
        msg = f'No files found matching the pattern'
        logging.warning(f'{msg}.')

    tg_msg = (
        f'{conf.get('ftp_host', '')}:\n\n'
        f'{msg}:\n'
        f'{files_string}\n'
        f'To file:\n'
        f'```LocalPath:\n{Path(conf.get('csv_path_directory', ''), csv_file_name)}```\n\n'
        f'Status: *{('merged' if merged_result else 'error').upper()}*'
    )
    await send_telegram_message(
        tg_msg, str(Emoji.CHECK_MARK) if len_files >= conf.get('csv_files_min_number', 2) else str(Emoji.CROSS_MARK))


@logging_execution_time()
async def run_merge(conf: dict[str, int | str]) -> None:
    template_file = (
        conf.get('csv_path_template_file')) if conf.get('csv_path_template_file') else conf.get('csv_file_name_for_ftp')

    template_path = Path(conf.get('csv_path_template_directory'), template_file)

    await process_and_save_all_csv(template_path)

    # await send_telegram_message('CSV files merged completed successfully.')


@logging_execution_time()
async def run_load_on_ftp(conf: dict[str, int | str]) -> None:
    """
    Запускает загрузку CSV файла на FTP, если это разрешено конфигурацией.
    """
    # Проверяем флаг включения FTP
    ftp_enabled = bool(conf.get('ftp_enabled'))

    if not ftp_enabled:
        logging.warning('FTP upload is disabled in the settings; for this configuration, skip it.')
        return

    # Формируем пути
    local_path = Path(conf.get('csv_path_directory'), conf.get('csv_file_name_for_ftp'))
    ftp_dir = Path(conf.get('ftp_path', '/')).parent.as_posix()
    remote_file = conf.get('csv_file_name_for_ftp')
    remote_path = f"{ftp_dir}/{remote_file}"

    # Проверяем, существует ли локальный файл
    if not local_path.is_file():
        logging.error(f'Local CSV file not found: "{local_path}"')
        return

    # Загружаем файл на FTP
    upload_result = await upload_file_to_ftp(local_path, remote_path)

    # Отправляем уведомление в Telegram
    # TODO: Если статус error то явно не green_circle
    await send_telegram_message(
        f'{conf.get('ftp_host', '')}:\n\n'
        f'CSV file:\n'
        f'```LocalPath:\n{upload_result.get('local', '')}```\n'
        f'Uploaded to FTP host:\n'
        f'```Host:\n{conf.get('ftp_host', '')}```\n'
        f'At:\n'
        f'```RemotePath:\n{upload_result.get('remote', '')}```\n\n'
        f'Status: *{upload_result.get('status', 'error').upper()}*',
        str(Emoji.GREEN_CIRCLE) if upload_result.get('status', 'error').upper() != 'ERROR' else
        str(Emoji.EXCLAMATION_MARK)
    )


@logging_execution_time()
async def run(config_names: Sequence[str] | None = None) -> None:
    """
    Запуск обработки overlay-конфигов.

    :param config_names: Опциональная последовательность "имен" overlay (только изменяемая часть,
                         например 'staging'). Не включайте префикс '.env.' и не передавайте пути.
                         Если None — будут обработаны все файлы в ENV_DIR, начинающиеся с '.env.'.
    :raises ValueError: при некорректных входных именах.
    :raises FileNotFoundError: если ENV_DIR или указанный overlay-файл не найден.
    """
    config_list: tuple = ('env', 'csv', 'ftp')
    # Берём базовую конфигурацию (ENV_DIR и т.д.) из OverlayConfig (singleton)
    base_cfg: dict[str, int | str] = OverlayConfig().get_config(*config_list)

    env_dir = Path(base_cfg.get('env_dir', 'env'))
    if not env_dir.exists() or not env_dir.is_dir():
        raise FileNotFoundError(f'ENV_DIR not found or is not a directory: {env_dir}')

    # Собираем карту реальных файлов в каталоге: lower_name -> actual_name
    real_files_map: dict[str, str] = {}
    for p in env_dir.iterdir():
        if p.is_file() and p.name.startswith('.env.'):
            real_files_map[p.name.lower()] = p.name

    # Формируем список overlay-файлов для обработки (используем реальные имена файлов)
    overlay_files: list[str]
    if config_names:
        overlay_files = []
        for raw_name in config_names:
            if raw_name is None:
                continue
            # Санитизация: оставляем только имя, убираем пути
            name = Path(str(raw_name)).name.strip()
            # Если пользователь передал префикс ".env.", убираем его
            if name.startswith('.env.'):
                name = name[5:]
            # Запрещаем пустые имена и попытки path traversal
            if not name or '..' in name or '/' in name or '\\' in name:
                raise ValueError(f'Invalid config name: {raw_name!r}')
            target_filename_lower = f'.env.{name}'.lower()
            actual = real_files_map.get(target_filename_lower)
            if actual is None:
                # raise FileNotFoundError(f'Overlay config not found for name: {raw_name!r} (expected .env.{name})')
                logging.error(
                    'FileNotFoundError: Overlay config not found for name: %r (expected .env.%s)',
                    raw_name, name
                )
                continue

            overlay_files.append(actual)
    else:
        # Берём все файлы, начинающиеся с .env.
        overlay_files = [actual for actual in real_files_map.values()]

    logging.info('Overlay files to process: %s', overlay_files)

    # Обрабатываем каждый найденный overlay-файл
    for overlay_filename in overlay_files:
        # OverlayConfig принимает имя файла (относительно ENV_DIR)
        overlay_cfg = OverlayConfig(overlay_filename)
        cfg: dict[str, int | str] = overlay_cfg.get_config(*config_list)

        # Здесь должна быть логика обработки cfg (например, запуск задач, экспорт и т.д.)
        logging.debug('Processed overlay: %s, keys: %s', overlay_filename, list(cfg.keys()))

        logging.info('Run script for Merge CSV!')
        await run_merge(cfg)

        logging.info('Run script for Upload to FTP!')
        await run_load_on_ftp(cfg)


if __name__ == '__main__':
    from asyncio import run as aio_run

    logging.info('Run Script!')
    args = parse_args()
    aio_run(run(config_names=args.config))
    logging.info('Finished Script!')
