import gevent
from geventwebsocket import WebSocketServer, WebSocketApplication, Resource
from geventwebsocket._compat import range_type
from controller import SimpleSwitch


class WSGI_SERVER(SimpleSwitch):
    def __init__(self, *args, **kwargs):
        self.controller = self


class TestApplication(WebSocketApplication):
    def on_open(self):
        self.ws.send("helloooooooooo")

    def on_close(self, reason):
        print("Connection Closed!!!", reason)


def static_wsgi_app(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/html")])
    return "hello world"


resource = Resource([
    ('/', static_wsgi_app),
    ('/data', TestApplication)
])
