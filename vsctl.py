from subprocess import Popen, PIPE
import logging

LOG = logging.getLogger(__name__)


class Vsctl(object):
    def __init__(self, ovsdb_addr="tcp:127.0.0.1:6632", logger=logging.getLogger(__name__)):
        self.logger = logger
        self.ovsdb_addr = ovsdb_addr

    def show(self):
        return self._run_command(["show"])

    def add_queue(self, port, queue_id, min_rate, max_rate):
        command = "set port %s qos=@newqos -- --id=@newqos create qos type=linux-htb other-config:max-rate=%s queues:%s=@newqueue -- --id=@newqueue create queue other-config:min-rate=%s" % (
            port, max_rate, queue_id, min_rate)
        return self._run_command(self._parse_command(command))

    def _run_command(self, command):
        args = [
            "ovs-vsctl"
        ]
        args += command
        self.logger.info(' '.join(args))
        p = Popen(args, stdout=PIPE, stderr=PIPE)
        p.wait()
        if p.returncode != 0:
            self.vsctl_fatal(p.stderr.read())

        return p.stdout.read()

    def _parse_command(self, command):
        return command.split(" ")

    def vsctl_fatal(msg):
        self.logger.error(msg)
        raise Exception(msg)
