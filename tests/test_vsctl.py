import unittest
from vsctl import Vsctl
class Test(unittest.TestCase):
    def test_add(self):
        c=Vsctl()
        print c.add_queue('s1-eth1',9
          ,2333333333
          ,2333)
    