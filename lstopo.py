#!/usr/bin/env python

import argparse
from mininet.net import Mininet
from mininet.cli import CLI
from mininet.node import UserSwitch, RemoteController, DefaultController, NullController, OVSController, Controller
from mininet.topo import Topo
from mininet.log import lg, error, debug, info, output
from mininet.util import irange, quietRun
from mininet.link import TCLink
from functools import partial
try:
    from cStringIO import StringIO
except:
    from StringIO import StringIO
import sys
import requests
import json

flush = sys.stdout.flush

class LeafSpineTopo(Topo):
    "Topology for a leaf spine network"

    def __init__(self, nSpines, nLeaves, nHosts, numlinks, **params):
        Topo.__init__(self, **params)

        self.spines={}
        self.leaves={}
        self.numlinks = numlinks
        self.numhosts = nHosts
        h={}

        # Add switches
        sc=0
        hc=1
        for i in range(0, nSpines):
            self.spines[i] = self.addSwitch('s%d' % (sc+1))
            sc += 1
        for i in range(0, nLeaves):
            self.leaves[i] = self.addSwitch('s%d' % (sc+1))
            for s in self.spines:
                for l in range(0, self.numlinks):
                    self.addLink(self.leaves[i], self.spines[s])
            for j in range(0, nHosts):
                name = 'h%d' % hc
                ip = '10.0.%d.%d/24'%(i+1,j+2)
                defaultRoute = 'via 10.0.%d.254'%(i+1)
                hc += 1
                h[name] = self.addHost(name, ip=ip, defaultRoute=defaultRoute,
                        startCommand='foo')
                debug('*** Add host %s as %s\n' % (name, ip))
                self.addLink(h[name], self.leaves[i])
            sc += 1

        generate = params['generate'].lower() in ['y', 'yes', 't', 'true'] if 'generate' in params else False
        self.driver = 'ofdpa-ovs'
        self.onos = 'http://karaf:karaf@localhost:8181'
        post = params['post'].lower() in ['y', 'yes', 't', 'true'] if 'post' in params else False

        if generate or post:
             do_post_internal(self)

def do_post(self, _line):
    if not isinstance(self.mn.topo, LeafSpineTopo):
        output('*** PORT: Currently topology is not an instance of a leaf/spine network, a configuration cannot be generated\n')
        return
    do_post_internal(self.mn.topo)

def do_post_internal(topo):
    output('*** POST: Generating network configuration for ONOS controlled leaf/spine network\n')
    nSpines = len(topo.spines)
    nLeaves = len(topo.leaves)
    buf = StringIO()
    print >>buf, '{'
    print >>buf, '    "devices": {'
    for i in range(0, nSpines):
        print >>buf, '        "of:%016x": {' % (i+1)
        print >>buf, '            "segmentrouting": {'
        print >>buf, '                "name": "Spine%d",' % (i+1)
        print >>buf, '                "ipv4NodeSid": %d,' % (101 + i)
        print >>buf, '                "ipv4Loopback": "192.168.0.%d",' % (201 + i)
        print >>buf, '                "ipv6NodeSid" : %d,' % (201 + i),
        print >>buf, '                "ipv6Loopback" : "2000::c0a8:0%d",' % (101 + i)
        print >>buf, '                "routerMac": "c0:ff:ee:00:00:%02x",' % (i+1)
        print >>buf, '                "isEdgeRouter": false,'
        print >>buf, '                "adjacencySids": []'
        print >>buf, '            },'
        print >>buf, '            "basic": {'
        print >>buf, '                "name": "Spine%d",' % (i+1)
        print >>buf, '                "driver": "%s"' % topo.driver
        print >>buf, '            }'
        print >>buf, '        },'
    for i in range(0, nLeaves):
        print >>buf, '        "of:%016x": {' % (nSpines+i+1)
        print >>buf, '            "segmentrouting": {'
        print >>buf, '                "name": "Leaf%d",' % (i+1)
        print >>buf, '                "ipv4NodeSid": %d,' % (101 + nSpines+i)
        print >>buf, '                "ipv4Loopback": "192.168.0.%d",' % (201 + nSpines+i)
        print >>buf, '                "ipv6NodeSid" : %d,' % (201 + nSpines+i),
        print >>buf, '                "ipv6Loopback" : "2000::c0a8:0%d",' % (201 + nSpines+i)
        print >>buf, '                "routerMac": "c0:ff:ee:00:00:%02x",' % (nSpines+i+1)
        print >>buf, '                "isEdgeRouter": true,'
        print >>buf, '                "adjacencySids": []'
        print >>buf, '            },'
        print >>buf, '            "basic": {'
        print >>buf, '                "name": "Leaf%d",' % (i+1)
        print >>buf, '                "driver": "%s"' % topo.driver
        print >>buf, '            }'
        print >>buf, '        }%s' % (',' if i+1 < nLeaves else '')
    print >>buf, '    },'
    print >>buf, '    "ports": {'
    cnt = 0
    for i in range(0, nLeaves):
        for j in range(0, topo.numhosts):
            print >>buf, '        "of:%016x/%d": {' % (nSpines+i+1, nSpines*topo.numlinks+1+j)
            print >>buf, '            "interfaces": [ {'
            print >>buf, '                "ips": [ "10.0.%d.254/24" ],' % (i+1)
            print >>buf, '                "vlan-untagged": 10'
            print >>buf, '            } ]'
            print >>buf, '        }%s' % (',' if cnt+1 < nLeaves*topo.numhosts else '')
            cnt += 1
    print >>buf, '    }'
    print >>buf, '}'
    output('*** POST: POSTing ONOS network configuration to %s/onos/v1/network/configuration\n' % topo.onos)
    response = requests.post('%s/onos/v1/network/configuration' % topo.onos,
        headers={'Content-type': 'application/json'},
        data=buf.getvalue())
    if int(response.status_code / 100) != 2:
        error('*** POST: failed to post configuration to ONOS: %d:%s\n' % (response.status_code, response.text))
    else:
        output('*** POST: successfully posted configuration to ONOS\n')
    response.close()
    buf.close()

CLI.do_post = do_post

def do_pinggw(self, _line):
    output( '*** Ping: testing host reachability to default gateway\n') 
    sent = 0
    total = 0
    for h in self.mn.hosts:
        gw = h.cmd('ip route | grep default | cut -d\  -f3').rstrip()
        output( '%s -> %s' % (h.name, gw))
        result = h.cmd('ping -q -c 1 -t 1  $(ip route | grep default | cut -d\  -f3)')
        send, recv = self.mn._parsePing(result)
        sent += send
        total += recv
        if send == recv:
            output(' OK\n')
        else:
            output(' FAIL\n')
    dropped = (sent - total) * 100.0 / sent
    output( '*** Results: %d%% dropped (%d/%d received)\n' % (dropped, total, sent))

CLI.do_pinggw = do_pinggw
topos = { 'leafspine': ( lambda **x: LeafSpineTopo(**x) )}

