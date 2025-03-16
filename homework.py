"""Телеграм бот, отправляющий обновления статусов ДЗ для Яндекс Практикума."""
import logging
import os
import sys
import time
from http import HTTPStatus

import requests
from dotenv import load_dotenv
from telebot import TeleBot
from telebot.apihelper import ApiException

from exceptions import EndpointRequestFailure, MissingTokenException

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}
ERROR_HANDLERS = {
    requests.exceptions.HTTPError: (
        lambda e: f'Эндпоинт Яндекс Практикума не отвечает: {e}'),
    EndpointRequestFailure: (
        lambda e: f'Эндпоинт Яндекс Практикума недоступен: {e}'),
    TypeError: lambda e: f'Ответ содержит неожиданный тип данных: {e}',
    ValueError: lambda e: f'Ответ содержит неожиданные значения: {e}',
    KeyError: lambda e: f'Ответ не содержит ключи: {e}',
}

FORMAT_STRING = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter(FORMAT_STRING)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)


def prepare_request_params(payload: dict[str, int]):
    """Подготваливает словарь с параметрами запроса."""
    request_info = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': payload
    }
    return request_info


def check_tokens() -> None:
    """Проверяет наличие и корректность токенов эндпоинта, телеграма."""
    missing_env_vars = []
    ENVIRONMENT_VARS = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }
    for env_name, env_val in ENVIRONMENT_VARS.items():
        if not env_val:
            missing_env_vars.append(env_name)
    if missing_env_vars:
        error_message = (
            f'Отсутсвуют токены: {missing_env_vars}\n'
            'Принудительная останвока программы.'
        )
        logger.critical(error_message)
        raise MissingTokenException(error_message)


def send_message(bot: TeleBot, message: str) -> bool:
    """
    Функция отправляет сообщение через API Telegram.

    chat_id - id telegram-чата ученика, которому нужно ответить.
    message - подготовленный текст сообщения с обновленным статусом работы.
    """
    try:
        logger.debug('Начало отправки сообщения через telegram')
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
        )
    except (
        requests.exceptions.RequestException,
        ApiException
    ) as e:
        logger.error(f'Сбой в отправке сообщения через telegram: {e}')
        return False
    else:
        logger.debug('Успешная отправка сообщения через telegram')
        return True


def get_api_answer(timestamp: int) -> dict:
    """
    Функция получения ответа от API информации об обновлении статуса ДЗ.

    timestamp - момент времени формата UNIX epoche, с которого нужно проверить.
    """
    payload = {'from_date': timestamp}
    parameters = prepare_request_params(payload)
    try:
        logging.debug('Отправка запроса на {url}, заголовки: {headers},'
                      ' параметры запроса: {params}'.format(**parameters))
        homework_response = requests.get(**parameters)
    except requests.RequestException as e:
        raise EndpointRequestFailure(e.response.status_code) from e
    if homework_response.status_code != HTTPStatus.OK:
        raise EndpointRequestFailure(homework_response.status_code)
    return homework_response.json()


def check_response(response: dict) -> list:
    """Функция проверки корерктности формата ответа API."""
    if not isinstance(response, dict):
        raise TypeError(
            f'Ответ не приведен в формат json. Тип ответа - {type(response)}'
        )

    if 'homeworks' not in response:
        raise KeyError('В ответе отсутствует ключ homeworks')
    homeworks = response['homeworks']

    if not isinstance(homeworks, list):
        raise TypeError(
            'В ответе информация о ДЗ в формате не списка,'
            f' а {type(homeworks)}'
        )

    return homeworks


def parse_status(homework: dict) -> str:
    """
    Функция получает словарь соответсвующий одному ДЗ и выдает сообщение.

    homework - словарь из ответа API, соответсвующий одному ДЗ.
    """
    if 'status' not in homework.keys():
        raise KeyError('status')
    if 'homework_name' not in homework.keys():
        raise KeyError('Ключ homework_name отсутсвует')
    if (
        not isinstance(homework['status'], str)
    ) or (
        not isinstance(homework['homework_name'], str)
    ):
        raise TypeError('Статус или имя ДЗ не строки')
    if homework['status'] not in HOMEWORK_VERDICTS.keys():
        raise KeyError('status')
    homework_name = homework['homework_name']
    verdict = HOMEWORK_VERDICTS.get(homework['status'])
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def handle_error(bot, error_message, last_error_message):
    """Функция отправляет сообщение об ошибке в log и telegram."""
    logger.error(error_message)
    if error_message != last_error_message:
        send_message(bot, error_message)
    return error_message


def main():
    """Основная логика работы бота."""
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_error_message = ''

    check_tokens()

    while True:
        try:
            homework_response = get_api_answer(
                timestamp=timestamp)
            homeworks = check_response(homework_response)
            if homeworks:
                message = parse_status(homeworks[0])
                if send_message(bot=bot, message=message):
                    timestamp = homework_response.get(
                        'current_date',
                        timestamp
                    )
                    last_error_message = ''
            else:
                logger.debug('Статус домашнего задания не обновлялся')
        except Exception as error:
            for exc_type, message_func in ERROR_HANDLERS.items():
                if isinstance(error, exc_type):
                    error_message = message_func(error)
                    last_error_message = handle_error(
                        bot,
                        error_message,
                        last_error_message)
                    break
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        format=FORMAT_STRING,
        level=logging.DEBUG,
        handlers=[
            logging.StreamHandler(stream=sys.stdout),
            logging.FileHandler('homework_bot.log')
        ]
    )
    main()
