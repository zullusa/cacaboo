import hashlib
import json

import requests

from app.errors import AuthenticationError


class KeeneticAuthenticator:
    """Performs NDM challenge-response authentication to a Keenetic router.

    Only responsibility: turn login/password into an authenticated
    ``requests.Session`` and its required headers.
    """

    def __init__(self, base_url: str, login: str, password: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._login = login
        self._password = password
        self._session = requests.Session()
        self._base_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
        }

    @property
    def auth_url(self) -> str:
        return f"{self._base_url}/auth"

    def authenticate(self) -> tuple[requests.Session, dict]:
        """Authenticate and return ``(session, headers)`` ready for RCI calls."""
        challenge_data = self._fetch_challenge()
        encrypted_password = self._encrypt_password(
            login=self._login,
            password=self._password,
            challenge=challenge_data["challenge"],
            realm=challenge_data["realm"],
        )
        headers = self._build_headers(challenge_data["cookie"])
        payload = {"login": self._login, "password": encrypted_password}
        response = self._session.post(
            self.auth_url, data=json.dumps(payload), headers=headers
        )
        self._raise_for_auth_status(response)
        return self._session, headers

    def _fetch_challenge(self, cookie: str | None = None) -> dict:
        headers = self._build_headers(cookie)
        response = self._session.get(self.auth_url, headers=headers)
        challenge = response.headers.get("X-NDM-Challenge")
        realm = response.headers.get("X-NDM-Realm")
        set_cookie = response.headers.get("Set-Cookie", "").split(";")[0]
        if cookie is None:
            return self._fetch_challenge(set_cookie)
        return {"cookie": set_cookie, "challenge": challenge, "realm": realm}

    def _build_headers(self, cookie: str | None = None) -> dict:
        headers = dict(self._base_headers)
        if cookie:
            headers["Cookie"] = cookie
        return headers

    @staticmethod
    def _encrypt_password(login: str, password: str, challenge: str, realm: str) -> str:
        first = hashlib.md5(f"{login}:{realm}:{password}".encode()).hexdigest()
        return hashlib.sha256((challenge + first).encode()).hexdigest()

    @staticmethod
    def _raise_for_auth_status(response: requests.Response) -> None:
        if response.status_code == 200:
            return
        if response.status_code == 400:
            raise AuthenticationError("Bad request! Check login and password.")
        if response.status_code == 401:
            raise AuthenticationError("Login or password is incorrect!")
        if response.status_code == 403:
            raise AuthenticationError("Not authorized!")
        response.raise_for_status()