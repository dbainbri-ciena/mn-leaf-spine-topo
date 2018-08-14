# mn-leaf-spine-topo
A mininet based leaf-spine topology

## Quick Start
Included in this repo is a `Vagrantfile` that can be used to create a VM on
which the leaf-spine topology can be run. To create the VM a simple `vagrant up`
should do.
```
vagrant up
vagrant ssh
cd /vagrant
```

### Start the SDN Controller
The script which wraps the leaf-spine topology only supports ONOS currently.
To start and instance of the ONOS controller as container the following 
command should work.
```
docker run -tid --name onos --rm \
	-p 8101:8101 -p 8181:8181 -p 6653:6653 \
	-e ONOS_APPS=openflow,segmentrouting,layout \
	onosproject/onos:1.13.2
```

### Create the Topology
To create a simple 3 leaf / 2 spine topology the following command can be used.
```
sudo ./lsnet.py \
	--controller=remote,ip=127.0.0.1,port=6653 \
	--leaves=3 \
	--spines=2 \
	--hosts=2 \
	--wait \
	--ping \
	--onos=http://karaf:karaf@localhost:8181 \
	--post
```

This command will create the topology, wait for the switches to be connected
to the controller, have each host ping its leaf switch (for arps), and
generate and `POST` the segment routine configuration to ONOS.

_NOTE: if you add a `-v` command line argument to the `lsnet.py` command to see
more debug output from the script as the topology is created_

**NOTE: I don't know why this is, but if you execute a `pingall` at the mininet
prompt it really doesn't work. But if you `ctrl-D` out of mininet and restart
it with the same parameters and then do a `pingall` it seems to work. I think
this has something to do with a required order in ONOS between the config push
and the devices being connected and I consider it a big in ONOS or the SR 
application.**

### PingAll
At the mininet prompt execute the `pingall` command to have every host ping
across the fabric. The output should be something like the following.
```
mininet> pingall
*** Ping: testing ping reachability
h1 -> h2 h3 h4 h5 h6
h2 -> h1 h3 h4 h5 h6
h3 -> h1 h2 h4 h5 h6
h4 -> h1 h2 h3 h5 h6
h5 -> h1 h2 h3 h4 h6
h6 -> h1 h2 h3 h4 h5
*** Results: 0% dropped (30/30 received)
```

### View the Topology
Open your browser and view `http://localhost:8181/onos/ui` and you
should see the topology. If you want to see the topology in an access layout
issue the following commands via the ONOS CLI.
```
ssh -p 8101 karaf@localhost topo-layout access
```
To revert to the default layout use
```
ssh -p 8101 karaf@localhost topo-layout default
```
_NOTE: the default password is `karaf`_
