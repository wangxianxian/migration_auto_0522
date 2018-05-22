from utils_host import HostSession
from utils_guest import GuestSession, GuestSessionV2
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
from vm import CreateTest
import re
import time
import os
project_file = os.path.dirname(os.path.dirname(os.path.dirname
                                           (os.path.dirname
                                            (os.path.dirname
                                             (os.path.abspath(__file__))))))
tmp_file = project_file


def run_case(params):
    src_host_ip = params.get('src_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))

    test = CreateTest(case_id='rhel7_11947_virtio_scsi_local', params=params)
    id = test.get_id()

    test.main_step_log('1. boot a guest with datadisk '
                       'and set datadisk cache=writeback/writethrough.')

    test.main_step_log('2. download fio tools from '
                       'http://www.bluestop.org/fio/ and load some i/o in guest.')

    test.main_step_log('3.power off the host by unplug power cable.')

    test.main_step_log('4. boot up host again.')

    test.main_step_log('5. boot up the guest and do fio testing as step 2 again.')