"""Телеграм бот, отправляющий обновления статусов ДЗ для Яндекс Практикума."""
import logging
import os
import time
from http import HTTPStatus

import requests
from dotenv import load_dotenv
from telebot import TeleBot

from exceptions import (EndpointRequestFailure, MissingTokenException,
                        StatusNotUpdated)

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

FORMAT_STRING = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

logging.basicConfig(
    format=FORMAT_STRING,
    level=logging.DEBUG,
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter(FORMAT_STRING)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)


def check_tokens() -> None:
    """Проверяет наличие и корректность токенов эндпоинта, телеграма."""
    if not PRACTICUM_TOKEN:
        raise MissingTokenException('Practicum API')
    if not TELEGRAM_TOKEN:
        raise MissingTokenException('Telegram API')
    if not TELEGRAM_CHAT_ID:
        raise MissingTokenException('Chat ID')
    return None


def send_message(bot: TeleBot, message: str) -> None:
    """
    Функция отправляет сообщение через API Telegram.

    chat_id - id telegram-чата ученика, которому нужно ответить.
    message - подготовленный текст сообщения с обновленным статусом работы.
    """
    try:
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
        )
    except Exception as e:
        logger.error(f'Сбой в отправке сообщения через telegram: {e}')
    else:
        logger.debug('Успешная отправка сообщения через telegram')


def get_api_answer(timestamp: int) -> dict:
    """
    Функция получения ответа от API информации об обновлении статуса ДЗ.

    timestamp - момент времени формата UNIX epoche, с которого нужно проверить.
    """
    headers = HEADERS
    payload = {'from_date': timestamp}

    try:
        homework_response = requests.get(
            ENDPOINT,
            headers=headers,
            params=payload
        )
        homework_response.raise_for_status()
    except requests.RequestException as e:
        raise EndpointRequestFailure(response=e.response) from e

    if homework_response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR:
        raise requests.exceptions.HTTPError(response=homework_response)
    elif homework_response.status_code != HTTPStatus.OK:
        raise EndpointRequestFailure(response=homework_response)
    return homework_response.json()


def check_response(response: dict) -> None:
    """Функция проверки корерктности формата ответа API."""
    if not isinstance(response, dict):
        raise TypeError('Ответ не приведен в формат json')
    if (
        'homeworks' not in response.keys()
    ) or (
        not isinstance(response['homeworks'], list)
    ):
        raise TypeError('В ответе информация о ДЗ в неверном формате')
    if isinstance(response['homeworks'], list) and not response['homeworks']:
        raise StatusNotUpdated()
    if (
        'current_date' not in response.keys()
    ) or (
        not isinstance(response['current_date'], int)
    ):
        raise ValueError('В ответе отсутсвует информация о дате запроса')
    if (
        response['homeworks']
    ) and (
        not isinstance(response['homeworks'][0], dict)
    ):
        raise TypeError('Данные о домашнем задании не в словаре')


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


def main():
    """Основная логика работы бота."""
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_error_message = ''

    def handle_error(error_message):
        logger.error(error_message)
        nonlocal last_error_message
        if error_message != last_error_message:
            last_error_message = error_message
            send_message(bot, error_message)
    try:
        check_tokens()
    except MissingTokenException as error:
        error_message = f'{error}\nПринудительная останвока программы.'
        logger.critical(error_message)
        return
    while True:
        try:
            homework_response = get_api_answer(
                timestamp=timestamp)
            check_response(homework_response)
            if homework_response['homeworks']:
                message = parse_status(homework_response['homeworks'][0])
                send_message(bot=bot, message=message)
            timestamp = homework_response['current_date']

        except MissingTokenException as error:
            error_message = f'{error}\nПринудительная останвока программы.'
            logger.critical(error_message)
            send_message(bot, error_message)
        except requests.exceptions.HTTPError as error:
            error_message = f'Эндпоинт Яндекс Практикума не отвечает: {error}'
            handle_error(error_message)
        except EndpointRequestFailure as error:
            error_message = f'Эндпоинт Яндекс Практикума недоступен: {error}'
            handle_error(error_message)
        except TypeError as error:
            error_message = f'Ответ содержит неожиданный тип данных: {error}'
            handle_error(error_message)
        except ValueError as error:
            error_message = f'Ответ содержит неожиданные значения: {error}'
            handle_error(error_message)
        except KeyError as error:
            error_message = f'Ответ не содержит ключи: {error}'
            handle_error(error_message)
        except StatusNotUpdated as error:
            logger.debug(error)

        time.sleep(RETRY_PERIOD)

if __name__ == '__main__':
    main()
