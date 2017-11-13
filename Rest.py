import json
import logging

from controller import SimpleSwitch
from webob import Response
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.app.wsgi import ControllerBase, WSGIApplication, route, websocket, WebSocketRPCServer, rpc_public
from ryu.lib import dpid as dpid_lib
from ryu.lib import hub
from uuid import uuid1
import numpy as np

simple_switch_instance_name = 'simple_switch_api_app'


class SimpleSwitchRest(SimpleSwitch):
    _CONTEXTS = {'wsgi': WSGIApplication}

    def __init__(self, *args, **kwargs):
        super(SimpleSwitchRest, self).__init__(*args, **kwargs)
        self.switches = {}
        wsgi = kwargs['wsgi']
        wsgi.register(SimpleSwitchController, {
                      simple_switch_instance_name: self})
        self.lock = hub.Event()
        self.flows = []
        # params use for QoE
        self.clients = []
        self.client_to_qualitylist = {}
        self.client_to_bitratelist = {}
        self.client_to_history = {}
        self.max_bandwidth = 1000000000000000000
        self.max_buffer = 36
        self.min_buffer = 12
        self.allow_bandwidth = {}
        self.DC = {}

    def send_flow_request(self, datapath):
        self.logger.debug('send flow request: %016x', datapath.id)
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        req = parser.OFPFlowStatsRequest(
            datapath, 0, parser.OFPMatch(), 0xff, ofproto.OFPP_MAX)
        datapath.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, ev):
        flows = []
        for stat in ev.msg.body:
            flow = {}
            flow['table_id'] = stat.table_id
            flow['duration_sec'] = stat.duration_sec
            flow['priority'] = stat.priority
            flow['match'] = stat.match
            flow['actions'] = stat.actions
            flows.append(flow)
        self.logger.debug('FlowStats: %s', flows)
        self.flows = flows
        self.lock.set()

    @rpc_public
    def get_arp(self):
        self.logger.info("Ask arp via websocket")
        return self.mac_to_port

    @rpc_public
    def get_flows(self, datapath_id):
        self.logger.info("Ask flows via websocket")
        self.send_flow_request(self.datapaths[datapath_id])
        self.lock.wait()
        return self.flows

    @rpc_public
    def get_datapaths(self):
        self.logger.info("Ask datapaths via websocket")
        datapaths_id = []
        for key in self.datapaths:
            datapaths_id.append("0x%016x" % key)
        return datapaths_id

    # Return quality from the call of get_max_quality
    @rpc_public
    def get_max_quality(self, ip, metrics):
        self.client_to_qualitylist[ip]
        throughput = metrics['throughput']
        buffer_level = metrics['buffer_level']
        current_level = metrics['current_level']
        # fill information
        self.client_to_history[ip]['throughput'].append(throughput)
        self.client_to_history[ip]['buffer_level'].append(buffer_level)
        self.client_to_history[ip]['current_level'].append(current_level)
        self.logger.info("Ask for get_max_quality")
        self.client_to_history[ip]['current_quality'].append(
            self.client_to_qualitylist[ip][current_level])
        self.allow_bandwidth[ip] = throughput * 1000 # TODO: Change to PANDA
        # self.logger.info(self.client_to_history[ip])
        index, QoE = self.get_max_qoe(ip)
        self.logger.info("Next index %d with QoE: %f" % (index, QoE))
        self.client_to_history[ip]['next_level'].append(index)
        return index

    @rpc_public
    def register_client(self, ip, quality_list, bitrate_list):
        self.clients.append(ip)
        self.client_to_qualitylist[ip] = quality_list
        self.client_to_bitratelist[ip] = bitrate_list
        self.client_to_history[ip] = {}
        self.client_to_history[ip]['throughput'] = []
        self.client_to_history[ip]['buffer_level'] = []
        self.client_to_history[ip]['current_level'] = []
        self.client_to_history[ip]['current_quality'] = []
        self.client_to_history[ip]['next_level'] = []
        self.client_to_history[ip]['QoE'] = []
        self.DC[ip] = 3500000000000000
        self.allow_bandwidth[ip] = self.max_bandwidth
        self.logger.info(ip + " just been registered.")
        self.logger.info(bitrate_list)
        return ip

    def get_max_qoe(self, ip):
        quality = np.array(self.client_to_history[ip]['current_quality'])
        TQsum = np.sum(quality)
        num = len(quality)
        SQsum = np.sum(np.abs(quality[1:] - quality[:-1]))

        QoE_list = []
        for Qi in self.client_to_qualitylist[ip]:
            TQavg = (TQsum + Qi) / (num + 1)
            SQavg = (SQsum + np.abs(Qi - quality[-1])) / num
            QoE_list.append((TQavg - SQavg) / 2)

        index_QoE = np.argsort(QoE_list)[::-1]
        self.logger.info(QoE_list)
        # Clac sum of bitrate
        bitrate_sum = 0
        for c_ip in self.clients:
            if c_ip != ip:
                bitrate_sum += self.client_to_bitratelist[c_ip][self.client_to_history[c_ip]['current_level']].bitrate
        # Check best choice
        for i in range(len(QoE_list)):
            i = index_QoE[i]
            bitrate = self.client_to_bitratelist[ip][i]['bitrate']
            if (bitrate_sum + bitrate) < self.max_bandwidth:
                if bitrate < self.allow_bandwidth[ip]:
                    buffer = self.client_to_history[ip]['buffer_level'][-1]
                    if buffer > self.min_buffer:
                        # TODO: ADD DC & CT
                        return i, QoE_list[i]
        return 0, QoE_list[0]

    def map_video_quality(self, bandwidth):
        pass


class SimpleSwitchController(ControllerBase):
    def __init__(self, req, link, data, **config):
        super(SimpleSwitchController, self).__init__(req, link, data, **config)
        self.simple_switch_app = data[simple_switch_instance_name]

    @route('simpleswitch', '/mactable/{dpid}', methods=['GET'], requirements={'dpid': dpid_lib.DPID_PATTERN})
    def list_mac_table(self, req, **kwargs):
        simple_switch = self.simple_switch_app
        dpid = dpid_lib.str_to_dpid(kwargs['dpid'])
        if dpid not in simple_switch.mac_to_port:
            return Response(status=502)
        mac_table = simple_switch.mac_to_port.get(dpid, {})
        body = json.dumps(mac_table, indent=4, sort_keys=True)
        return Response(content_type='application/json', body=body)

    @route('simpleswitch', '/', methods=['GET'])
    def index_page(self, req, **kwargs):
        return Response(content_type='text/html', body="%s" % req)

    @route('simpleswitch', '/ip', methods=['GET'])
    def ip(self, req, **kwargs):
        return req.client_addr

    @websocket('simpleswitch', '/dash')
    def _websocket_handle(self, ws):
        simple_switch = self.simple_switch_app
        simple_switch.logger.info("WebSocket connected: %s", ws)
        rpc_server = WebSocketRPCServer(ws, simple_switch)
        rpc_server.serve_forever()
