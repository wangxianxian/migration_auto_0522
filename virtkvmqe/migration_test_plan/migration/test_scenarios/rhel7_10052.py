from __future__ import division
from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
from vm import CreateTest
from utils_migration import do_migration

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    incoming_port = params.get('incoming_port')
    test = CreateTest(case_id='rhel7_10052', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)
    speed = 52428800
    speed_m = speed / 1024 / 1024
    gap_speed = 5

    test.main_step_log('1. Start a VM on source host')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('1.1 Connecting to src serial')
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()

    test.main_step_log('2. Start guest on dst host with listening mode '
                       '"incoming tcp:0:5800"')
    incoming_val = 'tcp:0:%s' % incoming_port
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)

    test.main_step_log('3. On source host, set migration speed(max-bandwidth)')
    speed_cmd = '{"execute":"migrate-set-parameters","arguments":' \
                '{"max-bandwidth": %d}}' % speed
    src_remote_qmp.qmp_cmd_output(cmd=speed_cmd)
    paras_chk_cmd = '{"execute":"query-migrate-parameters"}'
    output = src_remote_qmp.qmp_cmd_output(cmd=paras_chk_cmd)
    if re.findall(r'"max-bandwidth": %d' % speed, output):
        test.test_print('Set migration speed successfully')
    else:
        test.test_error('Failed to change speed')

    test.main_step_log('4. On source host, check the migration status')
    check_info = do_migration(remote_qmp=src_remote_qmp,
                              migrate_port=incoming_port, dst_ip=dst_host_ip)
    if (check_info == False):
        test.test_error('Migration timeout')

    test.main_step_log('5. After migration completed, check migration speed')
    output = eval(src_remote_qmp.qmp_cmd_output('{"execute":"query-migrate"}'))
    transferred_ram = int(output.get('return').get('ram').get('transferred'))
    src_remote_qmp.test_print('The transferred ram is: %d' % transferred_ram)
    transferred_ram_cal = transferred_ram / 1024 / 1024
    total_time = int(output.get('return').get('total-time'))
    src_remote_qmp.test_print('The total time is: %d' % total_time)
    total_time_cal =  total_time / 1000
    speed_cal = transferred_ram_cal / total_time_cal
    gap_cal = abs(speed_cal-speed_m)
    if (gap_cal >= gap_speed):
        test.test_error('The real migration speed and expected speed have '
                        'a gap more than %d M/s' % gap_speed)
    else:
        test.test_print('The real migration speed is not more or less than '
                        'expected speed by %d M/s' % gap_speed)

    test.main_step_log('6 Check the status of guest')
    test.sub_step_log('6.1. Reboot guest')
    dst_serial = RemoteSerialMonitor(id, params, dst_host_ip, serial_port)
    cmd = 'dmesg'
    output = dst_serial.serial_cmd_output(cmd=cmd)
    if re.findall(r'Call Trace:', output):
        test.test_error('Guest hit call trace')
    dst_serial.serial_cmd(cmd='reboot')
    dst_guest_ip = dst_serial.serial_login()

    test.sub_step_log('6.2 Ping external host')
    external_host_ip = 'www.redhat.com'
    cmd_ping = 'ping %s -c 10' % external_host_ip
    dst_guest_session = GuestSession(case_id=id, params=params, ip=dst_guest_ip)
    output = dst_guest_session.guest_cmd_output(cmd=cmd_ping)
    if re.findall(r'100% packet loss', output):
        dst_guest_session.test_error('Ping failed')

    test.sub_step_log('6.3 Shutdown guest successfully')
    dst_serial.serial_shutdown_vm()

    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}', recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src end')