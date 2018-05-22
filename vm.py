import os
import time
import subprocess
import socket
import usr_exceptions
import threading
import re
import select


class Test(object):
    def __init__(self, case_id, params):
        self.case_id = case_id
        self.pid_list = []
        self.start_time = time.time()
        self.params = params
        self.guest_name = params.get('vm_cmd_base')['name'][0]

    def log_echo_file(self, log_str, short_debug=True, serial_debug=False):
        prefix_file = self.case_id
        log_file_list = []
        dir_timestamp = self.params.get('sub_dir_timestamp')
        if not prefix_file:
            prefix_file = 'Untitled'
        sub_log_dir = os.path.join(self.params.get('log_dir'),
                                   self.case_id + '-'
                                   + dir_timestamp + '_logs')

        if not os.path.exists(sub_log_dir):
            os.mkdir(sub_log_dir)
        if short_debug == True and serial_debug == False:
            log_file = sub_log_dir + '/' + 'short_debug.log'
            log_file_list.append(log_file)
        if short_debug == True or serial_debug == True:
            log_file = sub_log_dir + '/' + 'long_debug.log'
            log_file_list.append(log_file)
        if serial_debug == True:
            log_file = sub_log_dir + '/' + 'serial_debug.log'
            log_file_list.append(log_file)
        for log_file in log_file_list:
            if os.path.exists(log_file):
                try:
                    run_log = open(log_file, "a")
                    for line in log_str.splitlines():
                        timestamp = time.strftime("%Y-%m-%d-%H:%M:%S")
                        run_log.write("%s: %s\n" % (timestamp, line))

                except Exception as err:
                    txt = "Fail to record log to %s.\n" % log_file
                    txt += "Log content: %s\n" % log_str
                    txt += "Exception error: %s" % err
                    self.test_error(err_info=txt)
            else:
                try:
                    run_log = open(log_file, "a")
                    for line in log_str.splitlines():
                        timestamp = time.strftime("%Y-%m-%d-%H:%M:%S")
                        run_log.write("%s: %s\n" % (timestamp, line))

                except Exception as err:
                    txt = "Fail to record log to %s.\n" % log_file
                    txt += "Log content: %s\n" % log_str
                    txt += "Exception error: %s" % err
                    self.test_error(err_info=txt)

    def test_print(self, info, short_debug=True, serial_debug=False):
        if self.params.get('verbose') == 'yes':
            print (info)
        self.log_echo_file(log_str=info, short_debug=short_debug,
                           serial_debug=serial_debug)

    def test_error(self, err_info):
        raise usr_exceptions.Error(err_info)

    def main_step_log(self, log):
        log_tag = '='
        log_tag_rept = 7
        log_info = '%s Step %s %s' % (log_tag * log_tag_rept,
                                      log, log_tag * log_tag_rept)
        if self.params.get('verbose') == 'yes':
            print (log_info)
        Test.log_echo_file(self, log_str=log_info)

    def sub_step_log(self, str):
        log_tag = '-'
        log_tag_rept = 5
        log_info = '%s %s %s' % (log_tag * log_tag_rept,
                                 str, log_tag * log_tag_rept)
        Test.test_print(self, info=log_info)


class TestCmd(Test):
    def __init__(self, case_id, params):
        super(TestCmd, self).__init__(case_id=case_id, params=params)

    def subprocess_cmd_base(self, cmd, echo_cmd=True, verbose=True,
                            enable_output=True, timeout=300):
        output = ''
        errput = ''
        current_time = time.time()
        deadline = current_time + timeout
        pid = ''
        if echo_cmd == True:
            Test.test_print(self, '[root@host ~]# %s' % cmd)
        sub = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        while sub.poll() == None:
            if time.time() > deadline:
                err_info = 'Fail to run %s under %s sec.' % (cmd, timeout)
                TestCmd.test_error(self, err_info)

        fd = sub.stdout.fileno()
        pid = sub.pid
        if (enable_output == True):
            try:
                output = sub.communicate()[0]
            except ValueError:
                pass
            try:
                errput = sub.communicate()[1]
            except ValueError:
                pass
            allput = output + errput
            if verbose == True:
                self.test_print(info=allput)
            if re.findall(r'command not found', allput):
                TestCmd.test_error(self, 'Fail to run %s.' % cmd)
            return allput, fd
        elif (enable_output == False):
            return fd, pid

    def reader_select(self, name, stream, outbuf, vm_alias=None):
        timeout = 0.1
        while bool(select.select([stream], [], [], timeout)[0]):
            s = stream.readline()
            if not s:
                break
            s = s.decode('utf-8').rstrip()
            outbuf.append(s)
            if vm_alias:
                Test.test_print(self, '%s->%s: %s' % (vm_alias, name, s))
            else:
                Test.test_print(self, '%s: %s' % (name, s))
        stream.close()

    def check_status_qemu_boot(self, sub, vm_alias):
        while 1:
            qemu_stdout = sub.stdout.readline()
            qemu_stdout = qemu_stdout.decode('utf-8').rstrip()
            if qemu_stdout:
                if vm_alias:
                    Test.test_print(self, 'stdout->%s: %s' % (vm_alias, qemu_stdout))
                else:
                    Test.test_print(self, 'stdout: %s' % qemu_stdout)
                break

            qemu_stderr = sub.stderr.readline()
            qemu_stderr = qemu_stderr.decode('utf-8').rstrip()
            if qemu_stderr:
                if vm_alias:
                    Test.test_print(self, 'stderr->%s: %s' % (vm_alias, qemu_stderr))
                else:
                    Test.test_print(self, 'stderr: %s' % qemu_stderr)
                break

    def subprocess_cmd_advanced(self, cmd, echo_cmd=True, vm_alias=None):
        pid = ''
        stdout = []
        stderr = []
        if echo_cmd == True:
            Test.test_print(self, '[root@host ~]# %s' % cmd)
        sub = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        self.check_status_qemu_boot(sub, vm_alias)

        t1 = threading.Thread(target=self.reader_select,
                              args=('stdout', sub.stdout, stdout, vm_alias))
        t2 = threading.Thread(target=self.reader_select,
                              args=('stderr', sub.stderr, stderr, vm_alias))
        t1.daemon = True
        t1.name = 'stdout_thread'
        t1.start()

        t2.daemon = True
        t2.name = 'stderr_thread'
        t2.start()

        return sub.returncode, stdout, stderr

    def remove_cmd_echo_blank_space(self, output, cmd):
        if output:
            lines = output.splitlines()
            count = 0
            for line in lines:

                if line == cmd or line == '\n' \
                        or len(line) == 1 \
                        or len(line) == 0:

                    count = count + 1
                    lines.remove(line)
                    continue
                count = count + 1
            output = "\n".join(lines)
        return output

    def check_guest_process(self, kill_pid=True, src_ip=None, dst_ip=None):
        pid_list = []
        dst_pid_list = []
        output = ''
        if dst_ip:
            src_cmd_check = 'ssh root@%s ps -axu | grep %s | grep -v grep' \
                            % (dst_ip, self.guest_name)
            output, _ = self.subprocess_cmd_base(echo_cmd=False,
                                                 verbose=False, cmd=src_cmd_check)
            if output:
                pid = re.split(r"\s+", output)[1]
                info =  'Found a %s dst guest process : pid = %s' \
                        % (self.guest_name, pid)
                Test.test_print(self, info)
                if kill_pid == True:
                    self.kill_dst_guest_process(dst_ip, pid)
            else:
                info = 'No found %s dst guest process' % self.guest_name
                Test.test_print(self, info)
        if src_ip:
            src_cmd_check = "ps -axu| grep %s | grep -vE 'grep|ssh'" % self.guest_name
            output, _ = self.subprocess_cmd_base(echo_cmd=False,
                                                 verbose=False, cmd=src_cmd_check)
            if output:
                pid = re.split(r"\s+", output)[1]
                info =  'Found a %s guest process : pid = %s' % (self.guest_name, pid)
                Test.test_print(self, info)
                if kill_pid == True:
                    self.kill_guest_process(pid)
            else:
                info = 'No found %s guest process' % self.guest_name
                Test.test_print(self, info)

    def kill_guest_process(self, pid):
        cmd = 'kill -9 %s' % pid
        self.subprocess_cmd_base(cmd=cmd, enable_output=False)
        time.sleep(3)
        # Check pid until killed completely.
        self.check_guest_process()

    def kill_dst_guest_process(self, dst_ip, pid):
        cmd = 'ssh root@%s kill -9 %s' %(dst_ip, pid)
        self.subprocess_cmd_base(cmd=cmd, enable_output=False)
        time.sleep(3)
        # Check pid until killed completely.
        self.check_guest_process()

class CreateTest(TestCmd):
    def __init__(self, case_id, params):
        self.case_id = case_id
        self.id = case_id
        self.params = params
        self.dst_ip = params.get('dst_host_ip')
        self.src_ip = params.get('src_host_ip')
        self.timeout = params.get('timeout')
        self.passwd =params.get('host_passwd')
        super(CreateTest, self).__init__(case_id=case_id, params=params)
        self.clear_env()

    def get_id(self):
        info = 'Start to run case : %s' % self.case_id
        TestCmd.test_print(self, info)
        TestCmd.test_print(self, '%s\n' % ('*' * 50))
        return self.id

    def clear_env(self):
        pid_list = []
        dst_pid_list = []
        TestCmd.test_print(self, '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~')
        TestCmd.test_print(self, '======= Checking host kernel version: =======')
        TestCmd.subprocess_cmd_base(self, cmd='uname -r')
        if self.dst_ip:
            TestCmd.test_print(self, '======= Checking host kernel '
                                  'version on dst host: =======')
            cmd = 'ssh root@%s uname -r' %(self.dst_ip)
            TestCmd.subprocess_cmd_base(self, cmd=cmd)

        Test.test_print(self, '======= Checking the version of qemu: =======')
        TestCmd.subprocess_cmd_base(self, cmd='/usr/libexec/qemu-kvm -version')
        if self.dst_ip:
            TestCmd.test_print(self, '======= Checking the version of '
                                  'qemu on dst host: =======')
            cmd = 'ssh root@%s /usr/libexec/qemu-kvm -version' %(self.dst_ip)
            TestCmd.subprocess_cmd_base(self, cmd=cmd)

        TestCmd.test_print(self,'======= Checking guest process existed =======')
        TestCmd.check_guest_process(self, src_ip=self.src_ip, dst_ip=self.dst_ip)
        TestCmd.test_print(self, '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~')
