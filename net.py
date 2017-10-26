#!/usr/bin/python
from mininet.net import Mininet
#from mininet.node import RemoteController, UserSwitch, OVSKernelSwitch
from mininet.node import RemoteController, UserSwitch,OVSKernelSwitch
from mininet.link import Link
from mininet.cli import CLI
from mininet.log import setLogLevel

def topology():

    print '*** Creating network'
    net = Mininet(build=False, controller=None, autoSetMacs = True)

    print '*** Adding controller'
    c0 = net.addController( 'c0', controller=RemoteController, ip='127.0.0.1', port=6633 )

    print '*** Adding switches'
    s1 = net.addSwitch( 's1', listenPort=6674,cls=OVSKernelSwitch,protocols='OpenFlow10')
    print ('%s ' % s1.name)

    print '*** Adding hosts'
    hosts1 = [ net.addHost( 'h%d' % n,defaultRoute='via 10.0.0.254' ) for n in xrange(1,4) ]

    for h in net.hosts:
        print('%s ' % h.name),


    print '*** Adding links'
    for h in hosts1:
        net.addLink( s1, h )
        print ('(%s, %s) ' % (s1.name, h.name)),


    print " "

    print '*** Adding NAT'
    
    nat1=net.addNAT('nat1',ip='10.0.0.254',isNamespace=False)
    net.addLink(nat1,s1)
    print " "
    
    print '*** Starting network'
    net.build()
    s1.start( [c0] )
    s1.cmd('ovs-vsctl set-manager ptcp:6632')

    # print '*** Configuring hosts'
    #for h in net.hosts:
	    #h.cmd('sudo ethtool --offload %s-eth0 rx off tx off'%h.name)
        #h.cmd('sudo ethtool -K %s-eth0 tso off' % h.name )
        #h.cmd('sudo ethtool -K %s-eth0 gso off' % h.name )
    
    # print '*** Running CLI'
    CLI( net )

    print '*** Stopping network'
    net.stop()

if __name__ == '__main__':
    setLogLevel( 'info' )
    topology()
