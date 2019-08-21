# -*- Mode:python; c-file-style:"gnu"; indent-tabs-mode:nil -*- */
#
# Copyright (C) 2015-2018, The University of Memphis,
#                          Arizona Board of Regents,
#                          Regents of the University of California.
#
# This file is part of Mini-NDN.
# See AUTHORS.md for a complete list of Mini-NDN authors and contributors.
#
# Mini-NDN is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Mini-NDN is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Mini-NDN, e.g., in COPYING.md file.
# If not, see <http://www.gnu.org/licenses/>.

import sys
import time
from ndn.experiments.experiment import Experiment

class SimpleExperiment(Experiment):

    def __init__(self, args):
        Experiment.__init__(self, args)

    def setup(self):
        # self.checkConvergence()
        pass

    def attach(self, host, ap):
        if ap.name not in host.peerList.keys():
            print("Attach error: no link between %s and %s" % (host.name, ap.name))
            return
        for iface in host.intfList():
            link = iface.link
            if link:
                node1, node2 = link.intf1.node, link.intf2.node
                if node1 == host:
                    node1 = node2
                if node1 == ap:
                    host.cmdPrint("ifconfig %s up" % iface.name)
                else:
                    host.cmdPrint("ifconfig %s down" % iface.name)
        faces = host.cmd('nfdc face list|grep non-local|cut -d" " -f1|cut -d"=" -f2').split()
        for id in faces:
            host.cmd("nfdc face destroy %s" % id)
        ip = host.peerList[ap.name]
        output = host.cmd("nfdc face create udp4://%s" % ip)
        print(output)
        id = output.split('=')[1].split()[0]
        print("New face ID: %s" % id)
        print host.cmd("nfdc route add / %s" % id)
        print host.cmd("nfdc route show /")

    def update(self, node):
        node.cmd("kill -SIGINT `ps | grep kiteproducer | awk '{$1=$1};1' | cut -d\" \" -f1`")

    def run(self):
        rvPrefix = "/rv"
        producerSuffix = "/alice"

        consumer = None
        rv = None
        producer = None
        f1 = None
        f2 = None
        f3 = None

        for host in self.net.hosts:
            host.configNdn()
            print("%s: %s" %(host.name, host.peerList))
            if host.name == 'consumer':
                consumer = host
            elif host.name == 'rv':
                rv = host
            elif host.name == 'producer':
                producer = host
            elif host.name == 'f1':
                f1 = host
            elif host.name == 'f2':
                f2 = host
            elif host.name == 'f3':
                f3 = host

        # get all available peers and prepare for mobility simulation

        #* -1. get all peers' information: name and IP
        #* 0. remove all non-local faces
        #* 00. down all other links, and up this link
        #* 1. Name and IP of the current peer (for creating UDP4 face)
        #* 2. id of created face
        #* 3. add default route on created face
        #* 4. iterate next peer and repeat from 0

        if self.options.nlsrSecurity:
            rv.cmd("ndnsec-set-default /ndn/{}-site/%C1.Operator/op".format(rv.name))

        print("Advertising the RV prefix...")
        rv.cmd("nlsrc advertise %s" % rvPrefix)
        rvConvTime = 60
        print("Waiting %d seconds for RV prefix convergence..." % rvConvTime)
        time.sleep(rvConvTime)
        didConverge = True
        for host in self.net.hosts:
            if host.name != rv.name and host.name != producer.name: # producer installs default route
                if (int(host.cmd("nfdc fib | grep \"%s\" | wc -l" % rvPrefix)) != 3 or
                    int(host.cmd("nlsrc status | grep \"%s\" | wc -l" % rvPrefix)) != 7):
                    print("%s failed..." % host.name)
                    didConverge = False
        if not didConverge:
            print("Advertising prefix failed...")
            self.net.stop()
            sys.exit(1)
        print("RV prefix converged!")
        consumer.cmd("date > peek.out") # flush consumer log
        rv.cmd("ndnsec import -i /home/charlie/ndn/misc/%s.safebag -P 1" % rvPrefix[1:])
        producer.cmd("ndnsec import -i /home/charlie/ndn/misc/%s.safebag -P 1" % producerSuffix[1:])
        rv.cmd("NDN_LOG=kite.*=ALL kiterv %s > rv.out 2>&1 &" % rvPrefix)
        time.sleep(1)
        producer.cmd("NDN_LOG=kite.*=ALL kiteproducer -r %s -p %s > producer.out 2>&1 &" %(rvPrefix, producerSuffix))
        time.sleep(1)

        seq = 0
        minRtt = 0.2

        self.attach(producer, f3)
        time.sleep(1)
        self.update(producer)
        time.sleep(minRtt) # wait for update to finish
        consumer.cmd("ndnpeek %s/%d -v -w 2000 >> peek.out 2>&1 &" % (rvPrefix + producerSuffix, seq)) # single path
        seq += 1
        time.sleep(minRtt) # wait for at least one rtt

        self.attach(producer, f2)
        time.sleep(1)
        self.update(producer)
        time.sleep(minRtt)
        consumer.cmd("ndnpeek %s/%d -v -w 2000 >> peek.out 2>&1 &" % (rvPrefix + producerSuffix, seq)) # single path
        seq += 1
        time.sleep(minRtt)

Experiment.register("kite-simple", SimpleExperiment)
