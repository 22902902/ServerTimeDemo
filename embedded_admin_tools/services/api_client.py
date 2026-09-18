import json
from urllib.parse import urlencode

import requests


class ApiClient:
    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint
        self.session = requests.Session()

    def set_endpoint(self, endpoint: str) -> None:
        self.endpoint = endpoint

    def send_request(
        self,
        payload: dict,
        request_mode: str = "form",
        method: str = "POST",
        timeout: int = 20,
    ) -> dict:
        method = method.upper()
        headers = {}
        request_kwargs = {"timeout": timeout}

        if request_mode == "json":
            headers["Content-Type"] = "application/json; charset=utf-8"
            request_kwargs["json"] = payload
            request_body = json.dumps(payload, ensure_ascii=False, indent=2)
        else:
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=utf-8"
            request_kwargs["data"] = payload
            request_body = urlencode(payload, doseq=True)

        response = self.session.request(method, self.endpoint, headers=headers, **request_kwargs)

        parsed_body = None
        try:
            parsed_body = response.json()
        except ValueError:
            parsed_body = None

        return {
            "url": self.endpoint,
            "method": method,
            "request_mode": request_mode,
            "request_headers": headers,
            "request_payload": payload,
            "request_body": request_body,
            "status_code": response.status_code,
            "response_headers": dict(response.headers),
            "response_text": response.text,
            "response_json": parsed_body,
        }
