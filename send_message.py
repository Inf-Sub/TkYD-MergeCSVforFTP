# __author__ = 'InfSub'
# __contact__ = 'ADmin@TkYD.ru'
# __copyright__ = 'Copyright (C) 2024, [LegioNTeaM] InfSub'
# __date__ = '2026/03/26'
# __deprecated__ = False
# __email__ = 'ADmin@TkYD.ru'
# __maintainer__ = 'InfSub'
# __status__ = 'Production'  # 'Production / Development'
# __version__ = '1.8.2.0'

"""
Модуль для отправки сообщений в Telegram.

Содержит:
- Emoji: перечисление используемых эмодзи;
- escape_markdown_v2: утилита для экранирования текста под MarkdownV2;
- send_telegram_message: асинхронная функция отправки сообщения в Telegram Bot API.

Docstring каждого публичного элемента описывает параметры, возвращаемые значения,
возможные исключения и примеры использования.
"""

from typing import Dict, Any
from aiohttp import ClientSession as aio_ClientSession,  ClientConnectorError as aio_ClientConnectorError
from asyncio import TimeoutError as aio_TimeoutError
from aiohttp_socks import ProxyConnector
from re import sub as re_sub
from enum import Enum

from config import Config
from logger import logging

logging = logging.getLogger(__name__)


class Emoji(Enum):
    """
    Перечисление эмодзи, используемых в проекте.

    Атрибуты:
        GREEN_CIRCLE (str): зелёный круг (U+1F7E2).
        CROSS_MARK (str): восклицательный знак/крест (U+2757).

    :example:
        str(Emoji.GREEN_CIRCLE)
        '🟢'
    """
    GREEN_CIRCLE = '\U0001F7E2'  # 🟢
    CHECK_MARK = '\U00002705'  # ✅
    EXCLAMATION_MARK = '\U0000274C'  # ❌
    CROSS_MARK = '\U00002757'  # ❗
    DIAMOND_WITH_DOT = '\U0001F4A0'  # 💠

    def __str__(self) -> str:
        """Возвращает символ эмодзи при приведении к строке."""
        return self.value


def escape_markdown_v2(text: str) -> str:
    """
    Экранирует строку для безопасной вставки в Telegram MarkdownV2.

    MarkdownV2 требует экранирования следующих символов:
    _ * [ ] ( ) ~ ` > # + - = | { } . !

    :param text: Исходная строка, которую нужно экранировать.
    :ptype text: str

    :return: Строка с экранированными символами, готовая для отправки с parse_mode='MarkdownV2'.
    :rtype: str

    :example:
        escape_markdown_v2("Hello *world* (test).")
        'Hello \\*world\\* \\(test\\)\\.'
    """
    # Включаем точку '.' и восклицательный знак '!' в список экранируемых символов
    return re_sub(r'([_\*\[\]\(\)~`>#+\-\=\|{}\.!])', r'\\\1', text)


async def send_telegram_message(message: str, emoji: str = '') -> dict:
    """
    Асинхронно отправляет сообщение в Telegram через Bot API.

    Функция читает параметры Telegram (token, chat_id, parse_mode и т.д.) из Config().get_config('telegram').
    Поддерживается опциональная обработка Markdown (включая MarkdownV2 с экранированием).

    :param message: Текст сообщения для отправки.
    :ptype message: str
    :param emoji: Опциональная строка-эмодзи, которая будет добавлена в начало сообщения.
        Можно передать Emoji, например str(Emoji.GREEN_CIRCLE).
    :ptype emoji: str

    :return: Словарь с JSON-ответом от Telegram API при успешной отправке, или пустой словарь при ошибке.
    :rtype: dict

    :raises KeyError: если в конфигурации отсутствует 'telegram_token' или 'telegram_chat_id'.
    :raises Exception: пробрасывает исключения, связанные с сетевыми ошибками (ловятся и логируются внутри).

    :notes:
        - Ожидается, что Config().get_config('telegram') вернёт словарь с ключами:
          'telegram_token' (str), 'telegram_chat_id' (str), 'telegram_parse_mode' (str, опционально).
        - chat_id может содержать суффикс вида "chat_id/message_thread_id" — в этом случае
          message_thread_id будет добавлен в полезную нагрузку запроса.

    :example:
        await send_telegram_message('Hello', str(Emoji.GREEN_CIRCLE))
    """
    env: Dict[str, Any] = Config().get_config('telegram')
    proxy_url = env.get('proxy')
    connector = ProxyConnector.from_url(proxy_url) if proxy_url else None

    logging.info('Preparing to send a message to Telegram.')

    # Проверка обязательных параметров
    if 'telegram_token' not in env or 'telegram_chat_id' not in env:
        logging.error('Telegram configuration missing: telegram_token or telegram_chat_id')
        raise KeyError('telegram_token and telegram_chat_id must be present in telegram config')

    # Поддержка parse_mode (Markdown / MarkdownV2 / HTML)
    parse_mode = (env.get('telegram_parse_mode') or '').strip()

    url = f'https://api.telegram.org/bot{env['telegram_token']}/sendMessage'

    # Вместо api.telegram.org можно использовать проверенное зеркало
    # url = f'https://api.bot-proxy.com/bot{env['telegram_token']}/sendMessage'

    # Разделение chat_id и message_thread_id, если требуется
    parts = str(env['telegram_chat_id']).split('/')
    chat_id = parts[0]
    message_thread_id = parts[1] if len(parts) > 1 else None

    text_to_send = message
    if parse_mode == 'MarkdownV2':
        text_to_send = escape_markdown_v2(message)

    payload: Dict[str, Any] = {
        'chat_id': chat_id,
        'text': text_to_send
    }

    if parse_mode:
        payload['parse_mode'] = parse_mode

    if message_thread_id:
        payload['message_thread_id'] = message_thread_id

    # Создаём неглубокую копию payload и обрабатываем поле 'text' в копии
    sanitized_payload = payload.copy()
    text = sanitized_payload.get('text')
    if isinstance(text, str):
        # заменить один или более переносов строки на один пробел и заменить маркеры
        sanitized_payload['text'] = re_sub(r'\n+', ' ', text).replace('```', '"').replace('*', '"')

    logging.debug('Payload for Telegram: "%s"', sanitized_payload)
    # logging.debug('Payload for Telegram: "%s"', payload)

    if emoji:
        payload['text'] = f'{emoji} {payload['text']}'

    # HTTP-запрос к Telegram Bot API
    async with aio_ClientSession(connector=connector) as session:
        try:
            async with session.post(url, data=payload, timeout=10) as response:
                if response.status == 200:
                    logging.info('Message successfully sent to Telegram.')
                    return await response.json()
                else:
                    error_text = await response.text()
                    logging.error('Error sending message: "%s"', error_text)
                    return {}

        # Убираем logging.exception, чтобы не видеть Traceback
        except aio_ClientConnectorError as e:
            logging.error("Telegram Error: Connection failed (Proxy/Firewall block?). Details: %s", e)
        except aio_TimeoutError:
            logging.error("Telegram Error: Request timed out.")
        except Exception as e:
            # Для всех остальных ошибок проверяем уровень логирования
            if logging.isEnabledFor(10):  # 10 = DEBUG
                logging.exception("Unexpected error while sending to Telegram:")
            else:
                logging.error("Telegram Error: %s", e)
        return {}

        # except Exception as e:
        #     # Логируем трассировку стека только при DEBUG, иначе — краткое сообщение
        #     # if logging.getLogger().isEnabledFor(logging.DEBUG):
        #     # Проверяем уровень напрямую у объекта logging (который уже логгер)
        #     if logging.isEnabledFor(10):  # 10 — это уровень DEBUG
        #         logging.exception('Exception occurred while trying to send a message to Telegram.')
        #     else:
        #         logging.error('Error sending message: "%s"', e)
        #     return {}


if __name__ == '__main__':
    """
    Простой тестовый запуск модуля.

    Поведение:
        - Загружает конфигурацию Telegram из Config().
        - Отправляет тестовое сообщение в указанный чат.
    Примечание:
        Перед запуском убедитесь, что в конфигурации заданы 'telegram_token' и 'telegram_chat_id'.

    :example:
        python -m this_module
    """
    from asyncio import run as aio_run

    aio_run(send_telegram_message('Test message.', str(Emoji.GREEN_CIRCLE)))
