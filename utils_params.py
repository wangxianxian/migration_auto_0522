import os
import sys
import re
import yaml
import json
from usr_exceptions import Error
BASE_FILE = os.path.dirname(os.path.abspath(__file__))


class Params(object):
    def __init__(self, yaml_id=None, case_list=None):
        self._yaml_id = yaml_id
        self._case_list = case_list
        self._params = {}
        self.build_dict_from_yaml()
        if self._case_list:
            self.find_case_from_yaml()

    def get_requirement_id(self):
        return self._yaml_id

    def get(self, key, default=None):
        val = self._params.get(key)
        if default:
            self._params[key] = default
            val = self._params.get(key)
        return val

    def find_yaml_file(self):
        file_path = ''
        search_name = self._yaml_id + '.yaml'
        for (thisdir, subshere, fileshere) in os.walk(BASE_FILE):
            for fname in fileshere:
                path = os.path.join(thisdir, fname)
                last_file = re.split(r'/', path)[-1]
                if search_name == last_file:
                    file_path = path
                    return file_path

        if not file_path:
            info = 'No found corresponding yaml file : %s' % search_name
            print (info)
            sys.exit(1)

    def build_dict_from_yaml(self):
        params_dict = {}
        file = self.find_yaml_file()
        with open(file) as f:
            params_dict = yaml.load(f)
        self._params = params_dict

    def find_case_from_yaml(self):
        self._params['only_case_list'] = []
        for case in self._case_list:
            flag_match = False
            for k, v in self._params.get('test_cases').items():
                if case == k:
                    self._params['only_case_list'].append(case)
                    flag_match = True
            if not flag_match:
                info = 'No found corresponding case %s ' \
                       'in %s requirement yaml file.' % (case, self._yaml_id)
                print (info)
                sys.exit(1)

    def vm_base_cmd_add(self, option, value):
        val_list = []
        if self._params['vm_cmd_base'].has_key(option) == False:
            val_list.append(value)
            self._params['vm_cmd_base'][option] = val_list
        else:
            for opt, val_list in self._params['vm_cmd_base'].items():
                if opt == option:
                    val_list.append(value)

    def vm_base_cmd_del(self, option, value=None):
        if self._params['vm_cmd_base'].has_key(option) == True:
            for opt, val_list in self._params['vm_cmd_base'].items():
                if opt == option and not value:
                    del self._params['vm_cmd_base'][opt]
                elif opt == option and value:
                    try:
                        index = val_list.index(value)
                        del self._params['vm_cmd_base'][opt][index]
                    except ValueError:
                        err_info = 'Error: No such value: %s' % value
                        raise Error(err_info)
        else:
            err_info = 'Error: No such option: %s' % option
            raise Error(err_info)

    def vm_base_cmd_update(self, option, old_value, new_value):
        if self._params['vm_cmd_base'].has_key(option) == True:
            for opt, val_list in self._params['vm_cmd_base'].items():
                if opt == option:
                    try:
                        index = val_list.index(old_value)
                        self._params['vm_cmd_base'][opt][index] = new_value
                    except ValueError:

                        err_info = 'Error: No such value: %s' % old_value
                        raise Error(err_info)
        else:
            err_info = 'Error: No such option: %s' % option
            raise Error(err_info)

    def add_daemon_monitor(self):
        self.vm_base_cmd_add('chardev',
                             'socket,id=daemon_qmp_monitor,'
                             'host=%s,port=%s,server,nowait'
                             % (self._params.get('src_host_ip'),
                                self._params.get('daemon_qmp_port')))
        self.vm_base_cmd_add('mon', 'chardev=daemon_qmp_monitor,mode=control')

    def create_qemu_cmd(self):
        cmd_line = ''
        cmd_line_script = ''
        cmd_line += '/usr/libexec/qemu-kvm '
        cmd_line_script += cmd_line + ' \\' + '\n'
        for opt, val in self._params['vm_cmd_base'].items():
            for v in val:
                cmd_line += '-' + opt + ' '
                cmd_line += str(v) + ' '
                cmd_line_script += '-' + opt + ' '
                cmd_line_script += str(v) + ' \\' + '\n'

        cmd_line = cmd_line.replace('None', '')
        return cmd_line

    def convert_variables(self):
        str_json = json.dumps(self._params)
        vars = re.findall(r'{\w+}', str_json)

        for var in vars:
            for key, val in self._params.items():
                if key == var.strip('{').strip('}'):
                    str_json = re.sub(var, val, str_json)

        remain_vars = re.findall(r'{\w+}', str_json)
        if remain_vars:
            print ('%s variables not assigned in %s.yaml.'
                   % (remain_vars, self._yaml_id))
            sys.exit(1)
        self._params = json.loads(str_json)

