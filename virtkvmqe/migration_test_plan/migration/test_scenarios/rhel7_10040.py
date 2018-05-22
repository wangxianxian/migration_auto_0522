import time
from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
from vm import CreateTest
from utils_migration import do_migration

def create_disk(host_session, disk_dir, disk_name, disk_format, disk_size):
        cmd = 'ls %s | grep %s.%s' % (disk_dir, disk_name, disk_format)
        output = host_session.host_cmd_output(cmd=cmd)
        if output:
            cmd = 'rm -f %s/%s.%s' % (disk_dir, disk_name, disk_format)
            output = host_session.host_cmd_output(cmd=cmd)
            if output:
                host_session.test_error('Failed to delete %s.%s disk'
                                        % (disk_name, disk_format))
        cmd = 'qemu-img create -f %s %s/%s.%s %d' \
              % (disk_format, disk_dir, disk_name, disk_format, disk_size)
        output= host_session.host_cmd_output(cmd=cmd)
        if re.findall('Failed', output) or re.findall\
                    ('Command not found', output):
            host_session.test_error('Failed to create %s.%s disk' %
                                    (disk_name, disk_format))
        cmd = 'qemu-img info %s/%s.%s' % (disk_dir, disk_name, disk_format)
        output = host_session.host_cmd_output(cmd=cmd)
        if re.findall('file format: %s' % disk_format, output):
            host_session.test_print('The format of %s disk is %s'
                                    % (disk_name, disk_format))
        else:
            host_session.test_error('The format of %s disk is not %s'
                                    % (disk_name, disk_format))

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    incoming_port = params.get('incoming_port')
    share_images_dir = params.get('share_images_dir')
    test = CreateTest(case_id='rhel7_10040', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)

    test.main_step_log('1. Boot guest with a system disk, a block data disk '
                       'and a scsi data disk.')
    test.sub_step_log('1.1 Create two images on src host')
    d0 = 'd0'
    d1 = 'd1'
    qcow2 = 'qcow2'
    create_disk(host_session=src_host_session, disk_dir=share_images_dir,
                disk_name=d0, disk_format=qcow2, disk_size=1024)
    create_disk(host_session=src_host_session, disk_dir=share_images_dir,
                disk_name=d1, disk_format=qcow2, disk_size=1024)

    test.sub_step_log('1.2 Boot a guest')
    params.vm_base_cmd_add('drive', 'file=%s/d0.qcow2,format=qcow2,if=none,'
                                    'id=drive-virtio-blk0,werror=stop,'
                                    'rerror=stop' % share_images_dir)
    params.vm_base_cmd_add('device', 'virtio-blk-pci,drive=drive-virtio-blk0,'
                                     'id=virtio-blk0,bus=pci.0,addr=10,'
                                     'bootindex=10')
    params.vm_base_cmd_add('drive', 'file=%s/d1.qcow2,if=none,id=drive_r4,'
                                    'format=qcow2,cache=none,aio=native,'
                                    'werror=stop,rerror=stop' % share_images_dir)
    params.vm_base_cmd_add('device', 'scsi-hd,drive=drive_r4,id=r4,'
                                     'bus=virtio_scsi_pci0.0,channel=0,'
                                     'scsi-id=0,lun=1')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('1.3 Connecting to src serial')
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()

    test.main_step_log('2. In HMP, hot remove the block data disk '
                       'and scsi data disk.')
    src_remote_qmp.qmp_cmd_output('{"execute":"device_del","arguments":'
                                  '{"id":"virtio-blk0"}}', recv_timeout=5)
    src_remote_qmp.qmp_cmd_output('{"execute":"device_del","arguments":'
                                  '{"id":"r4"}}', recv_timeout=5)
    test.sub_step_log('Check guest disk again')
    time.sleep(3)
    output = src_remote_qmp.qmp_cmd_output('{"execute":"query-block"}',
                                           recv_timeout=5)
    if re.findall(r'virtio-blk0', output) or re.findall(r'r4', output):
        src_remote_qmp.test_error('Failed to hot remove two data disks.')

    test.main_step_log('3. Boot guest with \'-incoming\' on des host '
                       'with only system disk.')
    params.vm_base_cmd_del('drive', 'file=%s/d0.qcow2,format=qcow2,if=none,'
                                    'id=drive-virtio-blk0,werror=stop,'
                                    'rerror=stop' % share_images_dir)
    params.vm_base_cmd_del('device', 'virtio-blk-pci,drive=drive-virtio-blk0,'
                                     'id=virtio-blk0,bus=pci.0,addr=10,'
                                     'bootindex=10')
    params.vm_base_cmd_del('drive', 'file=%s/d1.qcow2,if=none,id=drive_r4,'
                                    'format=qcow2,cache=none,aio=native,'
                                    'werror=stop,rerror=stop' % share_images_dir)
    params.vm_base_cmd_del('device', 'scsi-hd,drive=drive_r4,id=r4,'
                                     'bus=virtio_scsi_pci0.0,channel=0,'
                                     'scsi-id=0,lun=1')
    incoming_val = 'tcp:0:%s' % incoming_port
    params.vm_base_cmd_add('incoming', incoming_val)

    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)
    output = dst_remote_qmp.qmp_cmd_output('{"execute":"query-block"}',
                                           recv_timeout=10)
    if re.findall('virtio-blk0', output) or re.findall('r4', output):
        dst_remote_qmp.test_error('Destination guest boot error')

    test.main_step_log('4. Start live migration from src host')
    flag = do_migration(remote_qmp=src_remote_qmp,
                        migrate_port=incoming_port, dst_ip=dst_host_ip)
    if (flag == False):
        test.test_error('Migration timeout')

    test.main_step_log('5. Check guest status. Reboot guest ,  guest has '
                       '1 system disk and keeps working well.')
    dst_serial = RemoteSerialMonitor(id, params, dst_host_ip, serial_port)
    cmd = 'dmesg'
    output = dst_serial.serial_cmd_output(cmd=cmd)
    if re.findall(r'Call Trace:', output):
       test.test_error('Guest hit call trace')

    test.sub_step_log('5.1 Reboot dst guest')
    dst_serial.serial_cmd(cmd='reboot')
    dst_guest_ip = dst_serial.serial_login()

    test.sub_step_log('5.2 Check if guest only has 1 system disk')
    output = dst_remote_qmp.qmp_cmd_output('{"execute":"query-block"}',
                                           recv_timeout=5)
    if re.findall('drive-virtio-blk0', output) or re.findall('r4', output):
        dst_remote_qmp.test_error('Destination guest has other disk '
                                  'except 1 system disk')
    dst_guest_session = GuestSession(case_id=id, params=params, ip=dst_guest_ip)
    output = dst_guest_session.guest_cmd_output(cmd='fdisk -l', timeout=60)
    if re.findall(r'/dev/sda', output):
        dst_guest_session.test_print('The system disk is in disk')

    test.sub_step_log('5.3 Can access guest from external host')
    dst_guest_session.guest_ping_test('www.redhat.com', 10)

    test.sub_step_log('5.4 quit qemu on src end and shutdown vm on dst end')
    dst_serial.serial_shutdown_vm()

    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}', recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src host')