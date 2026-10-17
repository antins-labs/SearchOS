"""在 OS 隔离内设置继承资源限制后替换为技能解释器。"""
import math
import os
import resource
import sys

marker, timeout, *command = sys.argv[1:]
resource.setrlimit(resource.RLIMIT_FSIZE, (100_000_000, 100_000_000))
resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
resource.setrlimit(resource.RLIMIT_CPU, (math.ceil(float(timeout)) + 1,) * 2)
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
os.write(2, ('SEARCHOS-STARTED:' + marker + '\n').encode())
os.execv(command[0], command)
