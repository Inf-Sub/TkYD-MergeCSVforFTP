# execution_time.py

# __author__ = 'InfSub'
# __contact__ = 'https:/t.me/InfSub'
# __copyright__ = 'Copyright (C) 2025, [LegioNTeaM] InfSub'
# __date__ = '2025/12/14'
# __deprecated__ = False
# __maintainer__ = 'InfSub'
# __status__ = 'Development'  # 'Production / Development'
# __version__ = '1.0.0.2'

from logging import getLogger
from asyncio import iscoroutinefunction
from time import perf_counter as time_perf_counter
from functools import wraps as ft_wraps

logger = getLogger(__name__)


def logging_execution_time():
    """ Декоратор для логирования времени выполнения асинхронной или синхронной функции """
    def decorator(func):
        msg = ' def "%s" выполнена за %.6f s.'
        if iscoroutinefunction(func):
            @ft_wraps(func)
            async def wrapper(*args, **kwargs):
                log_msg = f'Async {msg}'
                t0 = time_perf_counter()
                result = await func(*args, **kwargs)
                duration = time_perf_counter() - t0
                (logger.debug if duration < 1 else logger.warning)(log_msg, func.__name__, duration)
                return result
            return wrapper
        else:
            @ft_wraps(func)
            def wrapper(*args, **kwargs):
                log_msg = f'Sync {msg}'
                t0 = time_perf_counter()
                result = func(*args, **kwargs)
                duration = time_perf_counter() - t0
                (logger.debug if duration < 1 else logger.warning)(log_msg, func.__name__, duration)
                return result
            return wrapper
    return decorator
