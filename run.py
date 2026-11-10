# __author__ = 'InfSub'
# __contact__ = 'https:/t.me/InfSub'
# __copyright__ = 'Copyright (C) 2025, [LegioNTeaM] InfSub'
# __date__ = '2025/12/14'
# __deprecated__ = False
# __maintainer__ = 'InfSub'
# __status__ = 'Production'  # 'Production / Development'
# __version__ = '1.9.0.6'

"""
Утилита для управления виртуальным окружением проекта.

Содержит класс VirtualEnvironmentManager, который:
- создаёт виртуальное окружение;
- устанавливает зависимости из requirements.txt;
- запускает основной скрипт проекта в созданном окружении.

Типизация:
- config_name в публичных методах принимает Optional[Sequence[str]].
  Это соответствует тому, что argparse с nargs='*' возвращает list[str] | None.

Docstring для класса и методов описывают параметры, возвращаемые значения и возможные исключения.
"""

from __future__ import annotations

from argparse import ArgumentParser
from subprocess import check_call
from sys import platform
from typing import Optional, Sequence
from venv import create as venv_create
from os import getlogin
from os.path import exists, join as os_join
import logging


# Константы
__maintainer__ = 'InfSub'

MAIN_SCRIPT = 'merge_csv'
REQUIREMENTS_FILE = 'requirements.txt'
VENV_PATH = '.venv'
LOG_FORMAT = '%(filename)s:%(lineno)d\n%(asctime)-20s| %(levelname)-8s| %(name)-15s| %(funcName)-27s| %(message)s'
LOG_DATE_FORMAT = '%Y.%m.%d %H:%M:%S'
LOG_LANGUAGE = 'en'  # en / ru
LOG_MESSAGE = {
    'venv_create': {
        'en': 'Creating a virtual environment in directory "%s"...',
        'ru': 'Создаем виртуальное окружение в каталоге "%s"...',
    },
    'venv_exists': {
        'en': 'Virtual environment already exists in directory "%s".',
        'ru': 'Виртуальное окружение уже существует в каталоге "%s".',
    },
    'requirements': {
        'en': 'Installing dependencies (requirements)...',
        'ru': 'Устанавливаем зависимости...',
    },
    'run_script': {
        'en': 'Running script "%s"...',
        'ru': 'Запускаем скрипт "%s"...',
    },
    'task_cancelled': {
        'en': 'Task was cancelled.',
        'ru': 'Задание отменено',
    },
    'dir_not_found': {
        'en': 'Directory "%s" not found!',
        'ru': 'Каталог "%s" не найден!',
    },
    'file_not_found': {
        'en': 'File "%s" not found: "%s".',
        'ru': 'Файл "%s" не найден: "%s".',
    },
    'config_name': {
        'en': 'Received arguments when running code: "%s".',
        'ru': 'Получены аргументы при запуске кода: "%s".',
    },
}

# Настройка логирования
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
logger = logging.getLogger(__name__)


class VirtualEnvironmentManager:
    """
    Менеджер виртуального окружения проекта.

    Назначение
    ----------
    Создавать виртуальное окружение, устанавливать зависимости и запускать основной скрипт
    внутри этого окружения.

    :param venv_path: Путь к директории виртуального окружения. Если параметр individual=True,
        к пути добавляется имя текущего пользователя.
    :ptype venv_path: str
    """

    def __init__(self, venv_path: str, individual: bool = True) -> None:
        """
        Инициализация менеджера.

        Parameters
        ----------
        :param venv_path: Базовый путь для виртуального окружения (например, '.venv').
        :ptype venv_path: str
        :param individual: Если True, к venv_path добавляется суффикс с именем пользователя (getlogin()),
            чтобы создать индивидуальное окружение (по умолчанию True).
        :ptype individual: bool, optional

        :return: None
        """
        self.venv_path = venv_path if not individual else f'{venv_path}_{getlogin()}'

    def create_virtual_environment(self) -> None:
        """
        Создаёт виртуальное окружение в self.venv_path, если оно ещё не существует.

        :return: None

       :raise OSError: При ошибках создания окружения (пробрасывается от venv.create).
        """
        if not exists(self.venv_path):
            logger.info(LOG_MESSAGE['venv_create'][LOG_LANGUAGE], self.venv_path)
            venv_create(self.venv_path, with_pip=True)
        else:
            logger.warning(LOG_MESSAGE['venv_exists'][LOG_LANGUAGE], self.venv_path)

    def install_dependencies(self) -> None:
        """
        Устанавливает зависимости из файла requirements.txt в виртуальном окружении.

        Логика
        ------
        - Определяет путь к pip внутри виртуального окружения в зависимости от платформы.
        - Выполняет `pip install -r requirements.txt` через subprocess.check_call.
        - Логирует процесс и ошибки.

        :return: None

        :raise FileNotFoundError: Если исполняемый pip не найден (логируется как ошибка).
        :raise subprocess.CalledProcessError: При ошибке установки зависимостей (пробрасывается).
        """
        pip_executable = os_join(
            self.venv_path, 'Scripts', 'pip') if platform == "win32" else os_join(self.venv_path, 'bin', 'pip')

        logger.info(LOG_MESSAGE['requirements'][LOG_LANGUAGE])
        try:
            check_call([pip_executable, 'install', '-r', REQUIREMENTS_FILE])
        except Exception as e:
            logger.error(LOG_MESSAGE['file_not_found'][LOG_LANGUAGE], pip_executable, e)

    def run_main_script(self, config_name: Optional[Sequence[str]] = None) -> None:
        """
        Запускает основной скрипт проекта внутри виртуального окружения.

        :param config_name: Последовательность имён конфигов для передачи в основной скрипт.
            Примеры:
                - None -> запуск без аргумента --config
                - ['staging'] -> добавит ['--config', 'staging']
                - ['staging', 'production'] -> добавит ['--config', 'staging', 'production']
        :ptype Optional[Sequence[str]]

        :return: None

        :raise KeyboardInterrupt: При прерывании пользователем (логируется).
        :raise FileNotFoundError: Если python внутри venv не найден (логируется).
        :raise subprocess.CalledProcessError: При ошибках выполнения команды (логируется).
        """
        python_executable = os_join(self.venv_path, 'Scripts', 'python') if platform == 'win32' else os_join(
            self.venv_path, 'bin', 'python')

        try:
            # Обновляем pip перед запуском
            check_call([python_executable, '-m', 'pip', 'install', '--upgrade', 'pip'])
            logger.info(LOG_MESSAGE['run_script'][LOG_LANGUAGE], MAIN_SCRIPT)
            cmd = [python_executable, f'{MAIN_SCRIPT}.py']

            if config_name:
                # config_name — Sequence[str], безопасно индексируем
                if len(config_name) == 1:
                    cmd += ['--config', config_name[0]]
                else:
                    cmd += ['--config', *config_name]

            check_call(cmd)
        except KeyboardInterrupt:
            logger.error(LOG_MESSAGE['task_cancelled'][LOG_LANGUAGE])
        except Exception as e:
            logger.error(LOG_MESSAGE['file_not_found'][LOG_LANGUAGE], python_executable, e)

    def setup(self, config_name: Optional[Sequence[str]] = None) -> None:
        """
        Полный сценарий подготовки окружения и запуска проекта.

        Шаги
        -----
        1. create_virtual_environment
        2. Проверка наличия исполняемых директорий Scripts/bin
        3. install_dependencies
        4. run_main_script

        :param config_name: Параметр(ы) конфигурации для передачи в основной скрипт.
        :ptype Optional[Sequence[str]]

        :return: None
        """
        self.create_virtual_environment()
        if exists(os_join(self.venv_path, 'Scripts')) or exists(os_join(self.venv_path, 'bin')):
            self.install_dependencies()
            logger.info(LOG_MESSAGE['config_name'][LOG_LANGUAGE], str(config_name))
            self.run_main_script(config_name=config_name)
        else:
            logger.error(LOG_MESSAGE['file_not_found'][LOG_LANGUAGE], self.venv_path, 'Directory not found')


def _build_arg_parser() -> ArgumentParser:
    """
    Создаёт и настраивает парсер аргументов командной строки.

    :return: argparse.ArgumentParser: Настроенный парсер.
    """
    parser = ArgumentParser(description='Setup virtualenv and run main script')
    parser.add_argument(
        '--config', '-c', nargs='*', type=str,
        help='Config name(s) to pass to the main script (e.g. --config staging production)')
    parser.add_argument(
        '--no-individual', action='store_true', help='Do not append username to venv path')
    return parser


if __name__ == '__main__':
    """
    Точка входа при запуске модуля как скрипта.

    Поведение
    --------
    - Разбирает аргументы командной строки (--config, --no-individual).
    - Определяет, нужно ли создавать индивидуальное окружение (VENV_INDIVIDUAL).
    - Создаёт экземпляр VirtualEnvironmentManager и запускает setup().

    Примеры
    --------
    python venv_manager.py --config staging
    python venv_manager.py --config staging production
    python venv_manager.py --no-individual
    """
    arg_parser = _build_arg_parser()
    args = arg_parser.parse_args()

    # Если пользователь явно указал --no-individual, отключаем индивидуальный суффикс
    venv_individual_default = False if getlogin().lower() == __maintainer__.lower() else True
    venv_individual = venv_individual_default and not args.no_individual

    manager = VirtualEnvironmentManager(VENV_PATH, venv_individual)
    # args.config: list[str] | None соответствует Optional[Sequence[str]]
    manager.setup(config_name=args.config)
