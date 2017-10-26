import json
import logging

from controller import SimpleSwitch
from webob import Response
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.app.wsgi import ControllerBase, WSGIApplication, route
from ryu.lib import dpid as dpid_lib
from ryu.lib import hub

simple_switch_instance_name = 'simple_switch_api_app'

class SimpleSwitch(SimpleSwitch):
    _CONTEXTS = { 'wsgi': WSGIApplication }

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch, self).__init__(*args, **kwargs)
        wsgi = kwargs['wsgi']
        wsgi.register(SimpleSwitchController, {simple_switch_instance_name : self})
        self.lock = hub.Event()
        self.flows = []

class SimpleSwitchController(ControllerBase):
    def __init__(self, req, link, data, **config):
    super(SimpleSwitchController, self).__init__(req, link, data, **config)
    self.simpl_switch_spp = data[simple_switch_instance_name]
	@route('simpleswitch', '/mactable/{dpid}' , methods=['GET'], requirements={'dpid': dpid_lib.DPID_PATTERN})
	def list_mac_table(self, req, **kwargs):
		simple_switch = self.simpl_switch_spp
		dpid = dpid_lib.str_to_dpid(kwargs['dpid'])
		if dpid not in simple_switch.mac_to_port:
			return Response(status=404)
		mac_table = simple_switch.mac_to_port.get(dpid, {})
		body = json.dumps(mac_table, indent=4, sort_keys=True)
		return Response(content_type='application/json', body=body)