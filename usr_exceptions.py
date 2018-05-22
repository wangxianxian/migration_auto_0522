import exceptions


class Error(Exception):
    def __init__(self, str):
        self.error_info = str
    def __str__(self):
        return self.error_info


class Fail(Exception):
    def __init__(self, str):
        self.fail_info = str
    def __str__(self):
        return self.fail_info


class Skip(Exception):
    def __init__(self, str):
        self.skip_info = str
    def __str__(self):
        return self.skip_info

