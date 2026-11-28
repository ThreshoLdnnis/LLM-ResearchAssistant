"""Open the desktop copy of the research workbench in the default Windows browser."""
from http.client import HTTPConnection, HTTPException
import os

from werkzeug.serving import make_server

from finrag.web import app


HOST = "127.0.0.1"
PORT = 8766
URL = f"http://{HOST}:{PORT}/"


@app.get("/_desktop_workbench")
def desktop_status():
    return "finrag-desktop"


def workbench_is_running():
    conn = HTTPConnection(HOST, PORT, timeout=2)
    try:
        conn.request("GET", "/_desktop_workbench")
        response = conn.getresponse()
        return response.status == 200 and response.read(32) == b"finrag-desktop"
    except (OSError, HTTPException):
        return False
    finally:
        conn.close()


def main():
    if workbench_is_running():
        os.startfile(URL)
        return
    with make_server(HOST, PORT, app, threaded=True) as server:
        print(f"Local research workbench: {URL}", flush=True)
        print("Keep this window open. Press Ctrl+C to stop.", flush=True)
        os.startfile(URL)
        server.serve_forever()


if __name__ == "__main__":
    main()
