import gevent
from threading import Thread
from geventwebsocket import WebSocketServer, WebSocketApplication, Resource
from geventwebsocket._compat import range_type
from controller import SimpleSwitch


class WSGI_SERVER(SimpleSwitch):
    def __init__(self, *args, **kwargs):
        super(WSGI_SERVER, self).__init__(*args, **kwargs)
        self.server = WebSocketServer(
            ('', 8080), self.resource, debug=True, _logger=self.logger)
        Thread(target=self.server.serve_forever(), args=(10,))


class TestApplication(WebSocketApplication):
    def on_open(self):
        self.ws.send("helloooooooooo")

    def on_close(self, reason):
        print("Connection Closed!!!", reason)


def static_wsgi_app(self, environ, start_response):
    start_response("200 OK", [("Content-Type", "text/html")])
    return "hello world"


resource = Resource([
    ('/', self.static_wsgi_app),
    ('/data', self.TestApplication)
])
