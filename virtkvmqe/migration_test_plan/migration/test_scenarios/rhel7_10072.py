import time
from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
import os
from utils_migration import do_migration
from vm import CreateTest
BASE_FILE = os.path.dirname(os.path.abspath(__file__))
MIGRATION_FILE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run_case(params):
    serial_port = int(params.get('serial_port'))
    qmp_port = int(params.get('qmp_port'))
    nfs_server_list = params.get('nfs_server')
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    guest_arch = params.get('guest_arch')

    test = CreateTest(case_id='rhel7_10072', params=params)
    id = test.get_id()
    host_session = HostSession(id, params)

    test.main_step_log('1. start VM in src host, install a guest')
    nfs_server_ip_list = []
    for server in nfs_server_list:
        nfs_server_ip_list.append(server.split(':')[0])
    test.test_print('NFS server ip:%s' % nfs_server_ip_list)

    rtt_info = {}
    rtt_val = []
    test.sub_step_log('1.1 Chose a nfs server.')
    for ip in nfs_server_ip_list:
        ping_cmd = 'ping %s -c 5' % ip
        output = host_session.host_cmd_output(ping_cmd)
        rtt_line = output.splitlines()[-1]
        if float(rtt_line.split('/')[-3]) < float(params.get('rtt_tolerance')):
            rtt_info[ip] = rtt_line.split('/')[-3]
            rtt_val.append(float(rtt_line.split('/')[-3]))
    if not rtt_val:
        test.test_error('No available nfs server.')
    test.test_print('rtt info : %s' % rtt_info)
    min_rtt_val = min(rtt_val)
    mount_info = ''
    for ip, rtt in rtt_info.items():
        if float(rtt) == min_rtt_val:
            for nfs_server in nfs_server_list:
                if ip in nfs_server:
                    mount_info = nfs_server

    test.test_print('Mount point info : %s' % mount_info)
    tmp_install_dir = os.path.join(params.get('share_images_dir'), 'install')
    if not os.path.exists(tmp_install_dir):
        os.makedirs(tmp_install_dir)

    image_size = params.get('image_size')
    test.sub_step_log('1.2 Create a system image to install os.')
    params.vm_base_cmd_update('device',
                              'scsi-hd,id=image1,drive=drive_image1,'
                              'bus=virtio_scsi_pci0.0,channel=0,scsi-id=0,'
                              'lun=0,bootindex=0',
                              'scsi-hd,id=image1,drive=drive_image1,'
                              'bus=virtio_scsi_pci0.0,channel=0,'
                              'scsi-id=0,lun=0')
    params.vm_base_cmd_del('drive',
                           'id=drive_image1,if=none,snapshot=off,'
                           'aio=threads,cache=none,format=qcow2,'
                           'file=%s/%s'
                           % (params.get('share_images_dir'),
                              params.get('sys_image_name')))
    if params.get('image_format') == 'qcow2':
        image = os.path.join(tmp_install_dir,
                             (params.get('image_name') + '.qcow2'))
        host_session.host_cmd_output('rm -rf %s' % image)
        host_session.host_cmd_output('qemu-img create -f qcow2 %s %s'
                                     % (image, image_size))
        params.vm_base_cmd_add('drive',
                               'id=drive_image1,if=none,snapshot=off,'
                               'aio=threads,cache=none,format=qcow2,'
                               'file=%s' % image)

    elif params.get('image_format') == 'raw':
        image = tmp_install_dir + params.get('image_name') + '.raw'
        host_session.host_cmd_output('qemu-img create -f raw %s %s'
                                     % (image, image_size))
        params.vm_base_cmd_add('drive',
                               'id=drive_image1,if=none,snapshot=off,'
                               'aio=threads,cache=none,format=raw,'
                               'file=%s' % image)

    mnt_dir = os.path.join(tmp_install_dir, 'mnt')
    if not os.path.exists(mnt_dir):
        os.makedirs(mnt_dir)
    test.sub_step_log('1.3 Mount iso from nfs server.')
    host_session.host_cmd_output('mount -t nfs %s %s' % (mount_info, mnt_dir))

    test.sub_step_log('1.4 Find the corresponding iso')
    iso_pattern = params.get('iso_name') + '*' + 'Server' + '*' \
               + params.get('guest_arch') + '*' + 'dvd1.iso'
    iso_name = host_session.host_cmd_output('find %s -name %s'
                                            % (mnt_dir, iso_pattern))
    if not iso_name:
        test.test_error('No found the corresponding %s iso.'
                        % params.get('iso_name'))
    test.test_print('Found the corresponding iso: %s' % iso_name)

    isos_dir = os.path.join(tmp_install_dir, 'isos')
    if not os.path.exists(isos_dir):
        os.makedirs(isos_dir)
    test.sub_step_log('1.5 cp the corresponding iso to %s' % isos_dir)
    host_session.host_cmd_output('cp -f %s %s' % (iso_name, isos_dir))

    iso_name = host_session.host_cmd_output('find %s -name %s'
                                            % (isos_dir, iso_pattern))

    host_session.host_cmd_output('umount %s' % mnt_dir)

    params.vm_base_cmd_add('drive',
                           'id=drive_cd1,if=none,snapshot=off,aio=threads,'
                           'cache=none,media=cdrom,file=%s' % iso_name)
    params.vm_base_cmd_add('device',
                           'scsi-cd,id=cd1,drive=drive_cd1,bootindex=2')

    test.sub_step_log('1.6 Find the corresponding ks')
    ks_pattern = params.get('iso_name').split('.')[0] + '*'
    ks = host_session.host_cmd_output('find %s -name %s'
                                      % (MIGRATION_FILE, ks_pattern))

    ks_iso = os.path.join(tmp_install_dir, 'ks.iso')

    test.sub_step_log('1.7 Make a %s form %s.' % (ks_iso, ks))
    host_session.host_cmd_output('mkisofs -o %s %s' % (ks_iso, ks))

    params.vm_base_cmd_add('drive',
                           'id=drive_unattended,if=none,snapshot=off,'
                           'aio=threads,cache=none,media=cdrom,'
                           'file=%s' % ks_iso)

    params.vm_base_cmd_add('device',
                           'scsi-cd,'
                           'id=unattended,drive=drive_unattended,bootindex=3')

    test.sub_step_log('1.8 cp vmlinuz and initrd.img form %s.' % iso_name)
    host_session.host_cmd_output('mount %s %s' % (iso_name, mnt_dir))
    if (guest_arch == 'x86_64'):
        host_session.host_cmd_output('cp -f /%s/images/pxeboot/vmlinuz %s'
                                     % (mnt_dir, isos_dir))
        host_session.host_cmd_output('cp -f /%s/images/pxeboot/initrd.img %s'
                                     % (mnt_dir, isos_dir))
    elif (guest_arch == 'ppc64le'):
        host_session.host_cmd_output('cp -f /%s/ppc/ppc64/vmlinuz %s'
                                     % (mnt_dir, isos_dir))
        host_session.host_cmd_output('cp -f /%s/ppc/ppc64/initrd.img %s'
                                     % (mnt_dir, isos_dir))
    host_session.host_cmd_output('umount %s' % mnt_dir)

    test.sub_step_log('1.9 Check the name of mounted ks.iso.')
    host_session.host_cmd_output('mount %s %s' % (ks_iso, mnt_dir))
    ks_name = host_session.host_cmd_output('ls %s' % mnt_dir)
    host_session.host_cmd_output('umount %s' % mnt_dir)

    params.vm_base_cmd_add('kernel',
                           '"%s/vmlinuz"' % isos_dir)
    console_option = ''
    if params.get('guest_arch') == 'x86_64':
        console_option = 'ttyS0,115200'
    elif params.get('guest_arch') == 'ppc64le':
        console_option = 'hvc0,38400'
    params.vm_base_cmd_add('append',
                           '"ksdevice=link inst.repo=cdrom:/dev/sr0 '
                           'inst.ks=cdrom:/dev/sr1:/%s nicdelay=60 '
                           'biosdevname=0 net.ifnames=0 '
                           'console=tty0 console=%s"'
                           % (ks_name, console_option))
    params.vm_base_cmd_add('initrd',
                           '"%s/initrd.img"' % isos_dir)

    test.sub_step_log('1.10 Boot this guest and ready to install os automaticlly.')
    params.vm_base_cmd_add('S', 'None')
    src_qemu_cmd = params.create_qemu_cmd()
    host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.main_step_log('2.start listenning mode in dst host '
                       'with "-incoming tcp:0:5800"')
    params.vm_base_cmd_del('S', 'None')
    params.vm_base_cmd_update('append',
                           '"ksdevice=link inst.repo=cdrom:/dev/sr0 '
                           'inst.ks=cdrom:/dev/sr1:/%s nicdelay=60 '
                           'biosdevname=0 net.ifnames=0 '
                           'console=tty0 console=%s"'
                           % (ks_name, console_option),
                           '\\""ksdevice=link inst.repo=cdrom:/dev/sr0 '
                           'inst.ks=cdrom:/dev/sr1:/%s nicdelay=60 '
                           'biosdevname=0 net.ifnames=0 '
                           'console=tty0 console=%s"\\"'
                           % (ks_name, console_option))
    params.vm_base_cmd_add('incoming',
                           'tcp:0:%s' % params.get('incoming_port'))
    dst_qemu_cmd = params.create_qemu_cmd()
    host_session.boot_remote_guest(cmd=dst_qemu_cmd,
                                   ip=dst_host_ip, vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)

    test.main_step_log('3. install guest and during guest formatting disk')
    src_serial = RemoteSerialMonitor(case_id=id, params=params,
                                     ip=src_host_ip, port=serial_port)
    src_remote_qmp.qmp_cmd_output('{ "execute": "cont" }')

    install_timeout = time.time() + int(params.get('install_timeout'))
    install_done = False
    started_install = False
    search_str = 'Checking software'
    while time.time() < install_timeout:
        output = src_serial.serial_output(max_recv_data=128,
                                          search_str=search_str)
        test.test_print(output)
        if re.findall(r'Found the searched keyword', output):
            started_install = True
            break

    if started_install == False:
        test.test_error('No started to install under %s sec.'
                        % params.get('install_timeout'))

    if started_install == True:
        test.main_step_log('4. migrate guest to destination host during guest'
                           ' formatting disk')
        ret = do_migration(remote_qmp=src_remote_qmp,
                           migrate_port=params.get('incoming_port'),
                           dst_ip=dst_host_ip)
        if ret == True:
            dst_serial = RemoteSerialMonitor(case_id=id, params=params,
                                             ip=dst_host_ip, port=serial_port)
            allput = ''
            while time.time() < install_timeout:
                output = dst_serial.serial_output()
                test.test_print(output)
                allput = allput + output
                if re.findall(r'Power down.', allput):
                   install_done = True
                   host_session.host_cmd_output('rm -rf %s/initrd.img' % isos_dir)
                   host_session.host_cmd_output('rm -rf %s/vmlinuz' % isos_dir)
                   host_session.host_cmd_output('rm -rf %s' % ks_iso)
                   break

            if install_done == False:
                host_session.host_cmd_output('rm -rf %s/initrd.img' % isos_dir)
                host_session.host_cmd_output('rm -rf %s/vmlinuz' % isos_dir)
                host_session.host_cmd_output('rm -rf %s' % ks_iso)
                test.test_error('Install failed under %s sec'
                                % params.get('install_timeout'))
            else:
                test.test_print('Install successfully.')

    params.vm_base_cmd_del('drive',
                           'id=drive_cd1,if=none,snapshot=off,aio=threads,'
                           'cache=none,media=cdrom,file=%s' % iso_name)

    params.vm_base_cmd_del('device',
                           'scsi-cd,id=cd1,drive=drive_cd1,bootindex=2')

    params.vm_base_cmd_del('drive',
                           'id=drive_unattended,if=none,snapshot=off,'
                           'aio=threads,cache=none,media=cdrom,'
                           'file=%s' % ks_iso)

    params.vm_base_cmd_del('device',
                           'scsi-cd,'
                           'id=unattended,drive=drive_unattended,bootindex=3')

    params.vm_base_cmd_del('kernel',
                           '"%s/vmlinuz"' % isos_dir)

    params.vm_base_cmd_del('append',
                           '\\""ksdevice=link inst.repo=cdrom:/dev/sr0 '
                           'inst.ks=cdrom:/dev/sr1:/%s nicdelay=60 '
                           'biosdevname=0 net.ifnames=0 '
                           'console=tty0 console=%s"\\"'
                           % (ks_name, console_option))

    params.vm_base_cmd_del('initrd',
                           '"%s/initrd.img"' % isos_dir)

    params.vm_base_cmd_del('incoming',
                           'tcp:0:%s' % params.get('incoming_port'))

    dst_qemu_cmd = params.create_qemu_cmd()
    test.sub_step_log('Boot guest again.')
    host_session.boot_remote_guest(cmd=dst_qemu_cmd,
                                   ip=dst_host_ip, vm_alias='dst')
    dst_serial = RemoteSerialMonitor(id, params, dst_host_ip, serial_port)

    dst_guest_ip = dst_serial.serial_login()
    dst_guest_session = GuestSession(case_id=id, params=params,
                                     ip=dst_guest_ip)
    test.sub_step_log('4.1 guest keyboard and mouse work normally.')

    test.sub_step_log('4.2 ping available, copy file succeed, network is fine.')
    external_host_ip = 'www.redhat.com'
    cmd_ping = 'ping %s -c 10' % external_host_ip
    output = dst_guest_session.guest_cmd_output(cmd=cmd_ping)
    if re.findall(r'100% packet loss', output):
        dst_guest_session.test_error('Ping failed')

    test.sub_step_log('4.3 Guest can reboot and shutdown successfully.')
    cmd_dd = 'dd if=/dev/zero of=file1 bs=1M count=1000 oflag=direct'
    output = dst_guest_session.guest_cmd_output(cmd=cmd_dd, timeout=600)
    if not output or re.findall('error', output):
        test.test_error('Failed to dd a file in guest')

    test.sub_step_log('4.4 Guest can reboot and shutdown successfully.')
    dst_serial.serial_cmd(cmd='reboot')
    dst_serial.serial_login()
    dst_serial.serial_shutdown_vm()

    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}',
                                           recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src end')
