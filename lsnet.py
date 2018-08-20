#!/usr/bin/env python

import argparse
from mininet.net import Mininet
from mininet.cli import CLI
from mininet.node import UserSwitch, RemoteController, DefaultController, NullController, OVSController, Controller
from mininet.topo import Topo
from mininet.log import lg, error, debug, info
from mininet.util import irange, quietRun
from mininet.link import TCLink
from functools import partial
try:
    from cStringIO import StringIO
except:
    from StringIO import StringIO
import sys
import requests

flush = sys.stdout.flush

class LeafSpineTopo(Topo):
    "Topology for a leaf spine network"

    def __init__(self, nSpines, nLeaves, nHosts, numlinks, **params):
        Topo.__init__(self, **params)

        # Add switches
        spines={}
        leaves={}
        h={}
        sc=0
        hc=1
        for i in range(0, nSpines):
            spines[i] = self.addSwitch('s%d' % (sc+1))
            sc += 1
        for i in range(0, nLeaves):
            leaves[i] = self.addSwitch('s%d' % (sc+1))
            for s in spines:
                for l in range(0, numlinks):
                    self.addLink(leaves[i], spines[s])
            for j in range(0, nHosts):
                name = 'h%d' % hc
                ip = '10.0.%d.%d/24'%(i+1,j+2)
                hc += 1
                h[name] = self.addHost(name, ip=ip)
                debug('*** Add host %s as %s\n' % (name, ip))
                self.addLink(h[name], leaves[i])
            sc += 1

def leafSpineNetwork(nSpines, nLeaves, nHosts, controller, numlinks, ping, generate, wait, onos, post):
    "Create the network"

    topo = LeafSpineTopo(nSpines, nLeaves, nHosts, numlinks)

    # Evaluate controller argument
    terms=controller.split(',')
    ctype = terms[0]
    del terms[0]
    if ctype == 'none':
        c = NullController('c0')
    elif ctype == 'remote':
        ip='127.0.0.1'
        port=6653
        for t in terms:
            kv = t.split('=')
            if kv[0] == 'ip':
                ip = kv[1]
            elif kv[0] == 'port':
                port=int(kv[1])
        c = RemoteController('c0', ip=ip, port=port)
    else:
        error('*** Unknown controller type\n')
        return
     
    net = Mininet(topo=topo, controller=c, waitConnected=wait)

    net.start()
    for h in net.hosts:
        debug('*** %s : disable ipv6\n' % h)
        h.cmd("sysctl -w net.ipv6.conf.all.disable_ipv6=1")
        h.cmd("sysctl -w net.ipv6.conf.default.disable_ipv6=1")
        h.cmd("sysctl -w net.ipv6.conf.lo.disable_ipv6=1")

    for sw in net.switches:
        debug('*** %s : disable ipv6\n' %sw)
        sw.cmd("sysctl -w net.ipv6.conf.all.disable_ipv6=1")
        sw.cmd("sysctl -w net.ipv6.conf.default.disable_ipv6=1")
        sw.cmd("sysctl -w net.ipv6.conf.lo.disable_ipv6=1")

    for h in net.hosts:
        o = h.IP().split('.')
        h.cmd('ip route add default via %s.%s.%s.254' % (o[0], o[1], o[2]))
        if ping:
            h.cmd('ping -c 1 -t 1 %s.%s.%s.254' % (o[0], o[1], o[2]))

    if generate or post:
        output = StringIO()
        print >>output, '{'
        print >>output, '    "devices": {'
        for i in range(0, nSpines):
            print >>output, '        "of:%016x": {' % (i+1)
            print >>output, '            "segmentrouting": {'
            print >>output, '                "name": "Spine%d",' % (i+1)
            print >>output, '                "ipv4NodeSid": %d,' % (101 + i)
            print >>output, '                "ipv4Loopback": "192.168.0.%d",' % (201 + i)
            print >>output, '                "routerMac": "c0:ff:ee:00:00:%02x",' % (i+1)
            print >>output, '                "isEdgeRouter": false,'
            print >>output, '                "adjacencySids": []'
            print >>output, '            },'
            print >>output, '            "basic": {'
            print >>output, '                "name": "Spine%d",' % (i+1)
            print >>output, '                "driver": "ofdpa-ovs"'
            print >>output, '            }'
            print >>output, '        },'
        for i in range(0, nLeaves):
            print >>output, '        "of:%016x": {' % (nSpines+i+1)
            print >>output, '            "segmentrouting": {'
            print >>output, '                "name": "Leaf%d",' % (i+1)
            print >>output, '                "ipv4NodeSid": %d,' % (101 + nSpines+i)
            print >>output, '                "ipv4Loopback": "192.168.0.%d",' % (201 + nSpines+i)
            print >>output, '                "routerMac": "c0:ff:ee:00:00:%02x",' % (nSpines+i+1)
            print >>output, '                "isEdgeRouter": true,'
            print >>output, '                "adjacencySids": []'
            print >>output, '            },'
            print >>output, '            "basic": {'
            print >>output, '                "name": "Leaf%d",' % (i+1)
            print >>output, '                "driver": "ofdpa-ovs"'
            print >>output, '            }'
            print >>output, '        }%s' % (',' if i+1 < nLeaves else '')
        print >>output, '    },'
        print >>output, '    "ports": {'
        cnt = 0
        for i in range(0, nLeaves):
            for j in range(0, nHosts):
                print >>output, '        "of:%016x/%d": {' % (nSpines+i+1,
                        nSpines*numlinks+1+j)
                print >>output, '            "interfaces": [ {'
                print >>output, '                "ips": [ "10.0.%d.254/24" ],' % (i+1)
                print >>output, '                "vlan-untagged": 10'
                print >>output, '            } ]'
                print >>output, '        }%s' % (',' if cnt+1 < nLeaves*nHosts else '')
                cnt += 1
        print >>output, '    }'
        print >>output, '}'
        if generate:
            print output.getvalue()
        if post:
            import json
            info('*** POSTing ONOS network configuration to %s/onos/v1/network/configuration\n' % onos)

            #req.add_header('Content-Type', 'application/json')
            response = requests.post('%s/onos/v1/network/configuration' % onos,
                headers={'Content-type': 'application/json'},
                data=output.getvalue())
            #response = urllib2.urlopen(req, data=output.getvalue())
            if int(response.status_code / 100) != 2:
                error('*** failed to post configuration to ONOS: %d:%s\n' % (ONOSresponse.status_code, response.text))
            response.close()
        output.close()

    CLI(net)
    net.stop()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('--leaves', '-l', metavar='N', default=3, type=int, nargs='?',
        help='the number of leaf nodes')
    parser.add_argument('--spines', '-s', metavar='N', default=2, type=int, nargs='?',
        help='the number of spine nodes')
    parser.add_argument('--hosts', '-t', metavar='N', default=2, type=int, nargs='?',
        help='the number of hosts per leaf node')
    parser.add_argument('--controller', '-c', metavar='CONTROLLER', default='remote,ip=127.0.0.1,port=6653', type=str, nargs='?',
        help='the number of hosts per leaf node')
    parser.add_argument('--numlinks', '-nl', metavar='N', default=1, type=int, nargs='?',
            help='the number of links from each leaf to each spine')
    parser.add_argument('--ping', '-p', action='store_true',
        help='have each host ping the leaf switch')
    parser.add_argument('--verbose', '-v', action='store_true',
        help='display a bit more detailed logging')
    parser.add_argument('--generate', '-g', action='store_true',
        help='gerate ONOS network configuration for fabric')
    parser.add_argument('--wait', '-w', action='store_true',
        help='wait for switches to connect to controller')
    parser.add_argument('--onos', '-o', metavar='ONOS', default='http://karaf:karaf@127.0.0.1:8181', type=str, nargs='?',
        help='ONOS base URL')
    parser.add_argument('--post', '-d', action='store_true',
        help='post configuration to onos')

    args = parser.parse_args()

    lg.setLogLevel('debug' if args.verbose else 'info')
    info('*** Starting Leaf - Spine Switches ***\n')
    leafSpineNetwork(args.spines, args.leaves, args.hosts, args.controller,
            args.numlinks, args.ping, args.generate, args.wait, args.onos, args.post)
