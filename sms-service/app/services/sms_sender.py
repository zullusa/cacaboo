import json

import requests

from app.domain.models import SmsMessage
from app.errors import SmsSendError
from app.interfaces.protocols import SmsSender
from app.services.authenticator import KeeneticAuthenticator


class KeeneticSmsSender(SmsSender):
    """Sends SMS through a Keenetic router RCI endpoint.

    Depends only on the SmsSender abstraction and on the authenticator
    (injected), so any other gateway can be swapped in without changing
    the callers (OCP / DIP).
    """

    def __init__(
        self,
        authenticator: KeeneticAuthenticator,
        interface_name: str,
        base_url: str,
    ) -> None:
        self._authenticator = authenticator
        self._interface_name = interface_name
        self._base_url = base_url.rstrip("/")
        self._session = None
        self._headers = None

    @property
    def rci_url(self) -> str:
        return f"{self._base_url}/rci/"

    def send(self, message: SmsMessage) -> None:
        response = self._post(message)
        if response.status_code == 401:
            self._session, self._headers = self._authenticator.authenticate()
            response = self._post(message)
        self._raise_for_send_status(response)

    def _post(self, message: SmsMessage) -> requests.Response:
        if self._session is None or self._headers is None:
            self._session, self._headers = self._authenticator.authenticate()
        payload = [
            {
                "sms": {
                    "send": {
                        "interface": self._interface_name,
                        "to": message.phone_number,
                        "message": message.text,
                    }
                }
            }
        ]
        return self._session.post(
            self.rci_url, data=json.dumps(payload), headers=self._headers
        )

    @staticmethod
    def _raise_for_send_status(response: requests.Response) -> None:
        if response.status_code == 200:
            return
        raise SmsSendError(f"Failed to send SMS: HTTP {response.status_code} {response.text}")