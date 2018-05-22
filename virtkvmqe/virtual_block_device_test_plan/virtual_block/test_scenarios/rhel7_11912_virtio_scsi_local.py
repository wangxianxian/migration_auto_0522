from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
from vm import CreateTest
import re
import time

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))

    test = CreateTest(case_id='rhel7_11912_virtio_scsi_local', params=params)
    id = test.get_id()
    host_session = HostSession(id, params)

    test.main_step_log('1. do system_reset when guest booting')
    qemu_cmd = params.create_qemu_cmd()
    host_session.boot_guest(qemu_cmd, vm_alias='src')

    test.sub_step_log('Connecting to serial')
    serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    timeout = 300
    endtime = time.time() + timeout

    searched_str = 'Trying to load'
    searched_done = False
    while time.time() < endtime:
        output = serial.serial_output(max_recv_data=500, search_str=searched_str)
        if re.findall(r'Found the searched keyword', output):
            test.test_print(output)
            searched_done = True
            remote_qmp.qmp_cmd_output('{ "execute": "system_reset" }')
            break
        else:
            test.test_print(output)
        if re.findall(r'login:', output):
            test.test_error('Failed to find the keyword: %s' % searched_str)

    if searched_done == False:
        test.test_error('Failed to find the keyword: %s under %s.'
                        % (searched_str, timeout))

    guset_ip = serial.serial_login()
    guest_session = GuestSession(case_id=id, params=params, ip=guset_ip)
    test.sub_step_log('guest ping through(http://www.redhat.com) '
                      'and there is no any error in dmesg.')
    guest_session.guest_ping_test(count=5, dst_ip='www.redhat.com')
    guest_session.guest_dmesg_check()

    test.main_step_log('2. reboot guest and do system_reset during guest rebooting')
    guest_session.guest_cmd_output(cmd='reboot')
    guest_session.close()

    searched_str = 'Stopped Network'
    searched_done = False
    while time.time() < endtime:
        output = serial.serial_output(max_recv_data=500, search_str=searched_str)
        if re.findall(r'Found the searched keyword', output):
            test.test_print(output)
            searched_done = True
            remote_qmp.qmp_cmd_output('{ "execute": "system_reset" }')
            break
        else:
            test.test_print(output)
        if re.findall(r'login:', output):
            test.test_error('Failed to find the keyword: %s' % searched_str)

    if searched_done == False:
        test.test_error('Failed to find the keyword: %s under %s.'
                        % (searched_str, timeout))

    test.main_step_log('3.repeate step 2 at least 10 times.')
    for i in range(1, 11):
        test.sub_step_log('Repeate %s time.' % i)
        searched_str = 'SLOF'
        searched_done = False
        while time.time() < endtime:
            output = serial.serial_output(max_recv_data=500,
                                          search_str=searched_str)
            if re.findall(r'Found the searched keyword', output):
                test.test_print(output)
                searched_done = True
                remote_qmp.qmp_cmd_output('{ "execute": "system_reset" }')
                break
            else:
                test.test_print(output)
            if re.findall(r'login:', output):
                test.test_error(
                    'Failed to find the keyword: %s' % searched_str)

        if searched_done == False:
            test.test_error('Failed to find the keyword: %s under %s.'
                            % (searched_str, timeout))

        guset_ip = serial.serial_login()
        guest_session = GuestSession(case_id=id, params=params, ip=guset_ip)
        test.sub_step_log('guest ping through(http://www.redhat.com) '
                          'and there is no any error in dmesg.')
        guest_session.guest_ping_test(count=5, dst_ip='www.redhat.com')
        guest_session.guest_dmesg_check()

        test.sub_step_log('reboot guest and do system_reset during guest rebooting')
        guest_session.guest_cmd_output(cmd='reboot')
        guest_session.close()

        searched_str = 'Stopped Network'
        searched_done = False
        while time.time() < endtime:
            output = serial.serial_output(max_recv_data=500,
                                          search_str=searched_str)
            if re.findall(r'Found the searched keyword', output):
                test.test_print(output)
                searched_done = True
                remote_qmp.qmp_cmd_output('{ "execute": "system_reset" }')
                break
            else:
                test.test_print(output)
            if re.findall(r'login:', output):
                test.test_error(
                    'Failed to find the keyword: %s' % searched_str)

        if searched_done == False:
            test.test_error('Failed to find the keyword: %s under %s.'
                            % (searched_str, timeout))
