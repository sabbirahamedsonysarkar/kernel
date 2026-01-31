import time
import ctypes

def python_sys_time(tloc=None):
    # 1. __kernel_old_time_t i = (...)ktime_get_real_seconds();
    # The kernel gets the raw seconds from the internal hardware clock.
    i = int(time.time())

    # 2. if (tloc) { ... }
    # In C, tloc is a memory address. In Python, we check if an object was passed.
    if tloc is not None:
        try:
            # 3. if (put_user(i, tloc)) return -EFAULT;
            # The kernel attempts to write the value 'i' into the user's memory.
            # If the memory is invalid/protected, it returns an error (-EFAULT).
            tloc.value = i 
        except Exception:
            return "-EFAULT"

    # 4. return i;
    # The syscall returns the time value directly to the CPU register.
    return i
