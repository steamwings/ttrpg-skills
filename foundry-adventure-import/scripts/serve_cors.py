#!/usr/bin/env python3
"""serve_cors.py DIR PORT — static file server the Foundry tab can fetch() from (CORS + Private Network Access).

Use when the browser driving Foundry runs in the same container (Playwright MCP): the page then does
`await fetch("http://localhost:PORT/journal.json")`, which avoids pasting large JSON into browser_evaluate.
"""
import functools, http.server, sys


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("0.0.0.0", int(sys.argv[2])),
                                    functools.partial(Handler, directory=sys.argv[1])).serve_forever()
