from ryu.app.wsgi import ControllerBase_gevent, WSGIApplication_gevent
from controller import SimpleSwitch
from ryu.app.wsgi import WSGIServer_gevent

simple_switch_instance_name = 'simple_switch_api_app'


class WSGI_SERVER(SimpleSwitch):
    _CONTEXTS = {'wsgi': WSGIApplication_gevent}

    def __init__(self, *args, **kwargs):
        super(WSGI_SERVER, self).__init__(*args, **kwargs)
        wsgi = kwargs['wsgi']
        wsgi.register(WSGI_SERVER_CONTROLLER, {
                      simple_switch_instance_name: self})


class WSGI_SERVER_CONTROLLER(ControllerBase_gevent):
    def __init__(self, data, **config):
        super(WSGI_SERVER_CONTROLLER, self).__init__(data, **config)
        self.simple_switch_app = data[simple_switch_instance_name]
        self.logger=self.simple_switch_app.logger
    
    def websocket_app(self, environ, start_response):
        if environ["PATH_INFO"] == '/echo':
            start_response("200 OK", [("Content-Type", "text/html")])
            return self.simple_switch_app.mac_to_port
