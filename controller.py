# Copyright (C) 2011 Nippon Telegraph and Telephone Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
An OpenFlow 1.0 L2 learning switch implementation.
"""

import json
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER, CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_0
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types
from os.path import dirname
from vsctl import Vsctl
from ryu.lib import hub

ROOT_PATH = dirname(__file__)


class SimpleSwitch(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        with open(ROOT_PATH + '/subs.json') as f:
            self.subs = json.load(f)
        super(SimpleSwitch, self).__init__(*args, **kwargs)
        self.switch_ctl = Vsctl()
        self.mac_to_port = {}
        self.dst_to_queue = {}
        self.port_n_queue = {}
        self.rate_requests = {}
        self.datapaths = {}
        self.port_to_name = {}
        self.default_rate = 10000000
        self.interval = 4

        # PANDA part
        self.bandwidth_history = []
        self.estimate_bandwidth = []
        self.smooth_bandwidth = []
        self.debug_bandwidth = 0
        self.step = 0
        self.k = 0.14
        self.w = 0.3
        self.interval = 4
        self.panda_thread = hub.spawn(self.panda)

# PANDA bandwidth estimate:
    def panda(self):
        self.logger.info("Start PANDA thread")
        while 1:
            hub.sleep(self.interval)
            self.debug_bandwidth = 100000 + self.step  # TODO: change to real metrics
            self.bandwidth_history.append(self.debug_bandwidth)
            if self.step == 0:
                self.estimate_bandwidth.append(self.bandwidth_history[0])
            else:
                self.estimate_bandwidth.append(self.interval * (self.k * self.w - max(
                    0, self.estimate_bandwidth[self.step - 1] - self.bandwidth_history[self.step - 1])) + self.estimate_bandwidth[self.step - 1])

            self.step += 1
            if self.logger:
                self.logger.info("step: %d, bandwidth: %f",
                                 self.step, self.estimate_bandwidth[-1])

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        msg = ev.msg
        self.logger.info('OFPSwitchFeatures received: '
                         'datapath_id=0x%016x n_buffers=%d '
                         'n_tables=%d capabilities=0x%08x ports=%s',
                         msg.datapath_id, msg.n_buffers, msg.n_tables,
                         msg.capabilities, msg.ports)
        ports = msg.ports
        datapath_id = msg.datapath_id
        self.port_to_name.setdefault(datapath_id, {})
        for port in ports:
            port = ports[port]
            self.port_to_name[datapath_id][port.port_no] = port.name

    def _add_flow(self, datapath, match, actions):
        """ Add flow with datapath, match, actions """
        ofproto = datapath.ofproto

        mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath, match=match, cookie=0,
            command=ofproto.OFPFC_ADD, idle_timeout=0, hard_timeout=0,
            priority=ofproto.OFP_DEFAULT_PRIORITY,
            flags=ofproto.OFPFF_SEND_FLOW_REM, actions=actions)
        datapath.send_msg(mod)

    def _get_protocols(self, pkt):
        protocols = {}
        for p in pkt.protocols:
            if hasattr(p, 'protocol_name'):
                if p.protocol_name == name:
                    protocols['name'] = p
        return protocols

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto

        pkt = packet.Packet(msg.data)
        protocols = self._get_protocols(pkt)
        p_arp = self.protocols.get("arp", None)
        p_icmp = self.protocols.get("icmp", None)
        p_ipv4 = self.protocols.get("ipv4", None)
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            # ignore lldp packet
            return
        dst = eth.dst
        src = eth.src
        in_port = msg.in_port
        parser = datapath.ofproto_parser

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})

        self.logger.info("packet in %s %s %s %s", dpid, src, dst, in_port)

        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[dpid][src] = msg.in_port

        actions = None
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
            if dst in self.subs:
                # When dst needs a queue
                self.logger.info("add queue")
                self.switch_ctl.add_queue(
                    self.port_to_name[dpid][out_port], 0, self.default_rate, self.default_rate)
                actions = [
                    datapath.ofproto_parser.OFPActionEnqueue(out_port, 1)]
            else:
                actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]
            match = parser.OFPMatch(in_port=in_port, dl_dst=dst, dl_src=src)
            self._add_flow(datapath, match, actions)

        else:
            actions = [datapath.ofproto_parser.OFPActionOutput(
                ofproto.OFPP_FLOOD)]

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath, buffer_id=msg.buffer_id, in_port=msg.in_port,
            actions=actions, data=data)
        datapath.send_msg(out)

    @set_ev_cls(ofp_event.EventOFPStateChange,
                [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        datapath = ev.datapath
        datapath_id = datapath.id
        if ev.state == MAIN_DISPATCHER:
            if datapath.id not in self.datapaths:
                self.datapaths[datapath.id] = datapath
                self.mac_to_port[datapath_id] = {}
                self.dst_to_queue[datapath_id] = {}
                self.port_n_queue[datapath_id] = {}
                self.rate_requests[datapath_id] = {}
                self.qos[datapath_id] = {}
                self.port_to_name.setdefault(datapath_id, {})
                self.logger.debug('registor datapath %s' % datapath_id)
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                del self.datapaths[datapath.id]
                del self.mac_to_port[datapath_id]
                del self.dst_to_queue[datapath_id]
                del self.port_n_queue[datapath_id]
                del self.rate_requests[datapath_id]
                del self.qos[datapath_id]
                del self.port_to_name[datapath_id]
                self.logger.debug('unregistor datapath %s' % datapath_id)

    @set_ev_cls(ofp_event.EventOFPPortStatus, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _port_status_handler(self, ev):
        msg = ev.msg
        reason = msg.reason
        port_no = msg.desc.port_no
        port_name = msg.desc.name
        ofproto = msg.datapath.ofproto
        if reason == ofproto.OFPPR_ADD:
            self.logger.info("port added %s:%s", port_no, port_name)
        elif reason == ofproto.OFPPR_DELETE:
            self.logger.info("port deleted %s:%s", port_no, port_name)
        elif reason == ofproto.OFPPR_MODIFY:
            self.logger.info("port modified %s:%s", port_no, port_name)
        else:
            self.logger.info("Illeagal port state %s %s", port_no, reason)
