import signal
from typing import Any, NoReturn, Optional


class Timeout:
    def __init__(self, seconds: int, error_message: Optional[str] = "Timeout") -> None:
        self.seconds = seconds
        self.error_message = error_message

    def handle_timeout(self, signum: int, frame: Any) -> NoReturn:
        raise TimeoutError(self.error_message)

    def __enter__(self) -> None:
        signal.signal(signal.SIGALRM, self.handle_timeout)
        signal.alarm(self.seconds)

    def __exit__(self, typ: Any, value: Any, traceback: Any) -> None:
        signal.alarm(0)
