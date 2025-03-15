"""Кастомные исключения для homework_bot."""


class MissingTokenException(ValueError):
    """Исключение отстутвия переменных окружения - токенов."""

    def __init__(self, error_message):
        """Создает сообщение ошибки."""
        super().__init__(error_message)


class EndpointRequestFailure(Exception):
    """Исключение непредвиденного сбоя при запросе к API ЯП."""

    def __init__(self, status_code):
        """Создает сообщение ошибки."""
        super().__init__(
            f"Запрос к эндпоинту API ЯП выдал ошибку: {status_code}"
        )
