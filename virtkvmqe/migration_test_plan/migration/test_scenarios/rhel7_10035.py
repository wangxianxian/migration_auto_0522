import time
from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
from vm import CreateTest
from utils_migration import do_migration
import threading

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    incoming_port = params.get('incoming_port')
    test = CreateTest(case_id='rhel7_10035', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)
    downtime = 10000
    speed = 52428800
    speed_m = speed / 1024 / 1024
    stress_time = 120
    gap_speed = 5
    gap_downtime = 5000

    test.main_step_log('1.Boot up a guest on source host')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('1.1 Connecting to src serial')
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()
    src_guest_session = GuestSession(case_id=id, params=params,
                                      ip=src_guest_ip)

    test.main_step_log('2. Running some application inside guest')
    chk_cmd = 'yum list installed | grep stress.`arch`'
    output = src_guest_session.guest_cmd_output(cmd=chk_cmd)
    if not output:
        install_cmd = 'yum install -y stress.`arch`'
        install_info = src_guest_session.guest_cmd_output(cmd=install_cmd)
        if re.findall('Complete', install_info):
            test.test_print('Guest install stress pkg successfully')
        else:
            test.test_error('Guest failed to install stress pkg')

    stress_cmd = 'stress --cpu 4 --vm 4 --vm-bytes 256M --timeout %d' \
                 % stress_time
    thread = threading.Thread(target=src_guest_session.guest_cmd_output,
                              args=(stress_cmd, 1200))
    thread.name = 'stress'
    thread.daemon = True
    thread.start()
    time.sleep(10)
    output = src_guest_session.guest_cmd_output('pgrep -x stress')
    if not output:
        test.test_error('Stress is not running in guest')

    test.main_step_log('3. Boot up the guest on destination host')
    incoming_val = 'tcp:0:%s' % incoming_port
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)
    dst_serial = RemoteSerialMonitor(id, params, dst_host_ip, serial_port)

    test.main_step_log('4.Set  the migration speed and downtime')
    downtime_cmd = '{"execute":"migrate-set-parameters","arguments":' \
                   '{"downtime-limit": %d}}' % downtime
    src_remote_qmp.qmp_cmd_output(cmd=downtime_cmd)
    speed_cmd = '{"execute":"migrate-set-parameters","arguments":' \
                '{"max-bandwidth": %d}}' % speed
    src_remote_qmp.qmp_cmd_output(cmd=speed_cmd)
    paras_chk_cmd = '{"execute":"query-migrate-parameters"}'
    output = src_remote_qmp.qmp_cmd_output(cmd=paras_chk_cmd)
    if re.findall(r'"downtime-limit": %d' % downtime, output) \
            and re.findall(r'"max-bandwidth": %d' % speed, output):
        test.test_print('Change downtime and speed successfully')
    else:
        test.test_error('Failed to change downtime and speed')

    test.main_step_log('5. Migrate guest from source host to destination host')
    check_info = do_migration(remote_qmp=src_remote_qmp,
                              migrate_port=incoming_port, dst_ip=dst_host_ip)
    if (check_info == False):
        test.test_error('Migration timeout')

    test.main_step_log('6.After migration finished,check migration statistics')
    cmd = '{"execute":"query-migrate"}'
    output = eval(src_remote_qmp.qmp_cmd_output(cmd=cmd))

    transferred_ram = int(output.get('return').get('ram').get('transferred'))
    transferred_ram_cal = transferred_ram / 1024 / 1024
    total_time = int(output.get('return').get('total-time'))
    total_time_cal = total_time / 1000
    speed_cal = transferred_ram_cal / total_time_cal
    gap_cal = abs(speed_cal - speed_m)
    if (gap_cal >= gap_speed):
        test.test_error('The real migration speed and expected speed '
                        'have a gap more than %d M/s' % gap_speed)
    else:
        test.test_print('The real migration speed is not more or less than '
                        'expected speed by %d M/s' % gap_speed)

    real_downtime = int(output.get('return').get('downtime'))
    gap_cal = real_downtime - downtime
    if (gap_cal > gap_downtime):
        test.test_error('The real migration downtime and expected downtime '
                        'have a gap more than %d milliseconds' % gap_downtime)
    else:
        test.test_print('The real migration downtime is not more or less than '
                        'expected downtime by %d milliseconds' % gap_downtime)

    test.main_step_log('7.After migration finished, check the status of guest')
    test.sub_step_log('7.1 Reboot guest')
    test.sub_step_log('check dmesg info')
    cmd = 'dmesg'
    output = dst_serial.serial_cmd_output(cmd=cmd)
    if re.findall(r'Call Trace:', output) or not output:
       test.test_error('Guest hit call trace')

    dst_serial.serial_cmd(cmd='reboot')
    dst_guest_ip = dst_serial.serial_login()

    test.sub_step_log('7.2 DD a file inside guest')
    dst_guest_session = GuestSession(case_id=id, params=params, ip=dst_guest_ip)
    cmd_dd = 'dd if=/dev/zero of=file1 bs=100M count=10 oflag=direct'
    output = dst_guest_session.guest_cmd_output(cmd=cmd_dd, timeout=600)
    if not output or re.findall('error', output):
        test.test_error('Failed to dd a file in guest')

    test.sub_step_log('7.3 Shutdown guest')
    dst_serial.serial_shutdown_vm()

    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}', recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src end')
