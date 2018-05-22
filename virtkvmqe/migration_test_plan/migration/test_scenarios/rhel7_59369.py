import time
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
    test = CreateTest(case_id='rhel7_59369', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)

    test.main_step_log('1. Boot guest with specified SMP configuration')
    params.vm_base_cmd_update('smp', '4,maxcpus=4,cores=2,threads=1,sockets=2',
                              '2,maxcpus=4,cores=2,threads=2,sockets=1')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('1.1 Connecting to src serial')
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()

    test.main_step_log('2. Check hot-pluggable CPU information')
    cmd = '{"execute": "query-hotpluggable-cpus"}'
    output = src_remote_qmp.qmp_cmd_output(cmd=cmd ,recv_timeout=5)
    if re.findall(r'"qom-path": "/machine/peripheral/core1"', output):
        src_remote_qmp.test_error('The info of hot-pluggable cpu is wrong')
    else:
        src_remote_qmp.test_print('The info of hot-pluggable cpu is right')

    test.main_step_log('3. Hot-plug the CPU core')
    cmd = '{"execute": "device_add", "arguments": ' \
          '{"driver":"host-spapr-cpu-core","core-id": 2,"id":"core1"}}'
    output = src_remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=5)
    if re.findall('error', output):
        test.test_error('Failed to execute cpu hotplug command')
    else:
        test.test_print('Cpu hotpulg command is executed successfully')

    test.main_step_log('4. Verify the core has been hot-plugged to the guest')
    test.sub_step_log('4.1 Check cpu info inside guest')
    cmd = "lscpu | sed -n '3p' | awk '{print $2}'"
    output = src_serial.serial_cmd_output(cmd=cmd)
    if not re.findall(r'4', output):
        test.test_error('The guest cpus info checked inside guest is wrong')

    test.sub_step_log('4.2 Check cpu info in src host')
    cmd = '{"execute": "query-hotpluggable-cpus"}'
    output = src_remote_qmp.qmp_cmd_output(cmd=cmd ,recv_timeout=5)
    if re.findall(r'"qom-path": "/machine/peripheral/core1"', output):
        src_remote_qmp.test_print('The guest cpus info checked in src host '
                                  'is right')
    else:
        src_remote_qmp.test_print('The guest cpus info checked in src host '
                                  'is wrong')

    test.main_step_log('5. Boot the destination guest '
                       '(with the hot-plugged core)')
    cpu_val = 'host-spapr-cpu-core,core-id=2,id=core1'
    params.vm_base_cmd_add('device', cpu_val)
    incoming_val = 'tcp:0:%s' % incoming_port
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd,
                                       ip=dst_host_ip, vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)
    cmd = '{"execute": "query-hotpluggable-cpus"}'
    output = dst_remote_qmp.qmp_cmd_output(cmd=cmd ,recv_timeout=5)
    if re.findall(r'"qom-path": "/machine/peripheral/core1"', output):
        src_remote_qmp.test_print('The guest cpus info of dst host is right')
    else:
        src_remote_qmp.test_print('The guest cpus info of dst host is wrong')

    test.main_step_log('6. Migrate guest from source to destination and '
                       'wait until it finishes,quit qemu of src host')
    flag = do_migration(remote_qmp=src_remote_qmp,
                        migrate_port=incoming_port, dst_ip=dst_host_ip)
    if (flag == False):
        test.test_error('Migration timeout')
    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}',
                                           recv_timeout=5)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src host')

    test.main_step_log('7. Run some command onto the hot-plugged core')
    dst_serial = RemoteSerialMonitor(id, params, dst_host_ip, serial_port)
    time.sleep(10)
    cmd = 'taskset -c 2,3 dd if=/dev/urandom of=/dev/null bs=64K count=1000'
    output = dst_serial.serial_cmd_output(cmd=cmd, recv_timeout=5)
    if re.findall('Failed', output) or re.findall('Error', output):
        test.test_error('Failed to execute taskset inside guest')
    else:
        test.test_print('Succeed to execute taskset inside guest')

    test.main_step_log('8. Reboot and then shutdown guest')
    cmd = 'dmesg'
    output = dst_serial.serial_cmd_output(cmd)
    if re.findall(r'Call Trace:', output):
        test.test_error('Guest hit call trace')
    dst_serial.serial_cmd(cmd='reboot')
    dst_serial.serial_login()

    cmd = "lscpu | sed -n '3p' | awk '{print $2}'"
    output = dst_serial.serial_cmd_output(cmd=cmd)
    if re.findall(r'4', output):
        test.test_print('After reboot, the guest cpus info is right')
    else:
        test.test_error('After reboot, the guest cpus info is wrong')

    dst_serial.serial_shutdown_vm()