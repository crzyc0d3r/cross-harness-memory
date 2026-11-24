"""Small client for four real UHP Memories routes, version 2026-10-19."""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class ProtocolError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class UHPClient:
    def __init__(self, base_url, api_key, memory_id, timeout=10):
        parsed = urlsplit(base_url)
        local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if (parsed.scheme != "https" and not (parsed.scheme == "http" and local)) or \
                not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Use an HTTPS base URL, or HTTP on loopback, without URL credentials")
        if not api_key or "\n" in api_key or "\r" in api_key:
            raise ValueError("An API key is required")
        if not isinstance(memory_id, str) or not memory_id.strip():
            raise ValueError("A granted memory ID is required")
        self.base, self.key, self.mid, self.timeout = base_url.rstrip("/"), api_key, memory_id, timeout
        self.opener = build_opener(NoRedirect())

    def _request(self, method, suffix, body=None, idempotency_key=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": "Bearer " + self.key, "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        url = self.base + "/v1/memories/" + quote(self.mid, safe="") + suffix
        try:
            with self.opener.open(Request(url, data=data, headers=headers, method=method),
                                  timeout=self.timeout) as response:
                payload = response.read(2_000_001)
                if len(payload) > 2_000_000:
                    raise ProtocolError("Memory response exceeds two megabytes")
        except HTTPError as exc:
            # Do not include headers or provider body, which may contain credentials or private data.
            raise ProtocolError(f"Memory request failed with HTTP {exc.code}") from None
        except URLError:
            raise ProtocolError("Memory service could not be reached") from None
        try:
            result = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            raise ProtocolError("Memory service returned invalid JSON") from None
        if not isinstance(result, dict):
            raise ProtocolError("Memory service returned a non-object response")
        return result

    def prime(self, budget=4000):
        if type(budget) is not int or budget < 1:
            raise ValueError("budget must be a positive integer")
        return self._request("GET", f"/prime?budget={budget}&depth=0")

    def recall(self, query, limit=8):
        if not isinstance(query, str) or not query.strip() or type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("Use nonempty query text and limit 1–50")
        return self._request("POST", "/recall", {"query": query, "limit": limit})

    def remember(self, text, idempotency_key):
        if not isinstance(text, str) or not text.strip() or not idempotency_key:
            raise ValueError("Text and an idempotency key are required")
        return self._request("POST", "/records", {"type": "fact", "content": text}, idempotency_key)

    def observe(self, question, answer, session_id, idempotency_key):
        if not all(isinstance(x, str) and x.strip() for x in (question, answer, session_id, idempotency_key)):
            raise ValueError("Question, answer, session ID and idempotency key are required")
        episode = {"content": [{"type": "text", "role": "user", "text": question},
                               {"type": "text", "role": "assistant", "text": answer}],
                   "attributes": {"session": session_id}}
        # An asynchronous provider may answer with job; this client returns it without claiming completion.
        return self._request("POST", "/observe", {"episodes": [episode]}, idempotency_key)
