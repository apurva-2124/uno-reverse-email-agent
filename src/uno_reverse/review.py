"""Loopback-only review server: static page, bearer token, strict Origin/Host."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import hmac
import json
from pathlib import Path
import secrets
from urllib.parse import urlsplit
import webbrowser
from .models import digest
from .replies import check_replies

STATIC = Path(__file__).with_name("static")


def make_server(workflow, port=0):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Do not log tokens, source messages, or request paths.

        def respond(self, status, data, content_type="application/json"):
            raw = json.dumps(data).encode() if content_type == "application/json" else data
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def valid_request(self, mutation=False):
            host = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != host:
                self.respond(403, {"error": "Invalid host"})
                return False
            origin = self.headers.get("Origin")
            if (mutation or origin is not None) and origin != f"http://{host}":
                self.respond(403, {"error": "Invalid origin"})
                return False
            return True

        def authenticated(self):
            value = self.headers.get("Authorization", "")
            if not hmac.compare_digest(value, "Bearer " + token):
                self.respond(401, {"error": "Open the current review URL from your terminal"})
                return False
            return True

        def do_GET(self):
            if not self.valid_request():
                return
            path = urlsplit(self.path).path
            files = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}
            if path in files:
                name, kind = files[path]
                return self.respond(200, (STATIC / name).read_bytes(), kind)
            if not self.authenticated():
                return
            if path == "/api/state":
                candidates = workflow.store.candidates()
                for c in candidates:
                    c["hash"] = digest(c["plan"])
                    # Fetch source on demand; don't cache the incoming body in SQLite.
                    c["source"] = [{"sender": m.sender, "subject": m.subject, "body": m.body} for m in workflow.mailbox.thread(c["plan"]["thread_id"]) if m.id == c["source_id"]]
                policy_id, policy = workflow.active_policy()
                return self.respond(200, {"candidates": candidates, "mailbox": workflow.mailbox.identity,
                                         "paused": workflow.store.get("paused"), "policy": policy, "policy_id": policy_id,
                                         "profile": workflow.store.get("profile"), "synthetic": workflow.mailbox.synthetic})
            self.respond(404, {"error": "Not found"})

        def do_POST(self):
            if not self.valid_request(mutation=True) or not self.authenticated():
                return
            if self.headers.get("Content-Type") != "application/json":
                return self.respond(415, {"error": "JSON required"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 65536:
                    return self.respond(413, {"error": "Invalid request size"})
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("Expected an object")
                action = urlsplit(self.path).path
                if action == "/api/approve":
                    workflow.approve(body["id"], body["hash"])
                elif action == "/api/edit":
                    workflow.edit(body["id"], body=body["body"], company=body["company"], brand=body["brand"], archive=body["archive"])
                elif action == "/api/exclude":
                    workflow.exclude(body["id"])
                elif action == "/api/send":
                    return self.respond(200, {"result": workflow.send(body["id"])})
                elif action == "/api/scan":
                    return self.respond(200, {"run": workflow.scan()})
                elif action == "/api/pause":
                    workflow.pause()
                elif action == "/api/resume":
                    workflow.resume()
                elif action == "/api/reconcile":
                    return self.respond(200, {"recovered": workflow.reconcile()})
                elif action == "/api/replies":
                    return self.respond(200, {"new_replies": check_replies(workflow)})
                else:
                    return self.respond(404, {"error": "Not found"})
                self.respond(200, {"ok": True})
            except (ValueError, KeyError, TypeError) as exc:
                self.respond(400, {"error": str(exc) if isinstance(exc, ValueError) else "Invalid request"})
            except Exception:
                self.respond(500, {"error": "Operation failed; check local state before retrying"})

    server = HTTPServer(("127.0.0.1", port), Handler)
    server.socket.settimeout(15)
    return server, f"http://127.0.0.1:{server.server_port}/#{token}"


def serve(workflow, port=0, open_browser=True):
    server, url = make_server(workflow, port)
    print(f"Synthetic mailbox review — {url}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
