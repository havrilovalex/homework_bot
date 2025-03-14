"""Кастомные исключения для homework_bot."""
import requests


class MissingTokenException(ValueError):
    """Исключение отстутвия переменных окружения - токенов."""

    def __init__(self, token):
        """Создает сообщение ошибки."""
        self.message = (
            f'Отсутствует обязательная переменная окружения: {token}'
        )
        super().__init__(self.message)


class EndpointRequestFailure(Exception):
    """Исключение непредвиденного сбоя при запросе к API ЯП."""

    def __init__(self, response: requests.Response):
        """Создает сообщение ошибки."""
        self.response = response
        super().__init__(
            f"Запрос к эндпоинту API ЯП выдал ошибку: {response.status_code}"
        )


class StatusNotUpdated(Exception):
    """Исключение при отсутсвии обновления статуса."""

    def __init__(self):
        """Создает сообщение ошибки."""
        self.message = 'Статус домашнего задания не обновлялся'
        super().__init__(self.message)
