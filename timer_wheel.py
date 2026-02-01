class TimerWheel:
    """
    A Python representation of the Linux Kernel Timer Wheel logic.
    Based on Linux kernel's timer.c implementation with cascading levels.
    """
    def __init__(self, hz):
        self.hz = hz
        self.nsec_per_sec = 1_000_000_000
        
        # Constants from Linux kernel (kernel/time/timer.c)
        self.LVL_DEPTH = 9      # 9 levels (0 to 8)
        self.LVL_BITS = 6       # 6 bits per level (2^6 = 64 buckets)
        self.LVL_SIZE = 1 << self.LVL_BITS  # 64 buckets
        self.LVL_CLK_DIV = 8    # Clock divider (2^3 = 8)
        self.LVL_CLK_DIV_BITS = 3  # Bits for clock divider

    def get_base_tick_ns(self):
        """Calculates the duration of 1 tick in nanoseconds."""
        return self.nsec_per_sec // self.hz

    def analyze(self, include_bits=False):
        """Analyze the timer wheel structure for the given HZ value."""
        print(f"=== Timer Wheel Analysis for HZ = {self.hz} ===")
        print(f"Base tick duration: {self.get_base_tick_ns()} ns ({1000//self.hz} ms)")
        print("-" * 60)
        
        headers = ["Lvl", "Offset", "Granularity", "Range (approx)"]
        if include_bits:
            headers.insert(2, "Bits")
            headers.insert(3, "Shift")
        
        print("{:<4} {:<8} {:<15} {:<}".format(*headers))
        
        tick_ns = self.get_base_tick_ns()
        total_range_start_ms = 0

        for level in range(self.LVL_DEPTH):
            # 1. Calculate offset (bit position in expiry index)
            offset = level * self.LVL_BITS
            
            # 2. Calculate granularity (time per bucket at this level)
            # Level 0: tick * 8^0 = tick
            # Level 1: tick * 8^1 = 8 * tick
            # Level 2: tick * 8^2 = 64 * tick, etc.
            granularity_ns = tick_ns * (self.LVL_CLK_DIV ** level)
            granularity_ms = granularity_ns // 1_000_000
            
            # 3. Calculate range for this level
            # Each level has LVL_SIZE (64) buckets
            level_capacity_ns = granularity_ns * self.LVL_SIZE
            level_capacity_ms = level_capacity_ns // 1_000_000
            
            range_end_ms = total_range_start_ms + level_capacity_ms
            
            # Format output
            gran_str = f"{granularity_ms} ms"
            if granularity_ms < 1:
                gran_str = f"{granularity_ns//1000} μs"
            
            range_str = f"{total_range_start_ms:,} ms - {range_end_ms:,} ms"
            
            row = [level, offset, gran_str, range_str]
            if include_bits:
                row.insert(2, f"{self.LVL_BITS}")
                row.insert(3, f"<< {level * self.LVL_CLK_DIV_BITS}")
            
            print("{:<4} {:<8} {:<15} {:<}".format(*row))
            
            total_range_start_ms = range_end_ms
        
        print("-" * 60)
        total_time_seconds = total_range_start_ms / 1000
        print(f"Total timer coverage: {total_range_start_ms:,} ms ({total_time_seconds:.1f} seconds)")
        print(f"Maximum timer delay: {total_time_seconds/3600:.2f} hours")

def analyze_cascading_example():
    """Example showing how timers cascade between levels."""
    print("\n=== Timer Cascading Example ===")
    print("When a timer's expiry time falls beyond the current level's range,")
    print("it gets pushed to a higher level with larger granularity.")
    print("\nExample for HZ=1000 (1ms tick):")
    print("- Level 0: handles timers 0-255ms (granularity 1ms)")
    print("- Level 1: handles timers 256-2047ms (granularity 8ms)")
    print("- Level 2: handles timers 2048-16383ms (granularity 64ms)")
    print("... and so on up to Level 8")

# Run the simulation
if __name__ == "__main__":
    # Standard HZ values used in Linux
    for hz in [1000, 250, 100]:
        TimerWheel(hz).analyze()
        print()
    
    # Additional analysis
    analyze_cascading_example()
    
    # Show effect of different HZ values
    print("\n=== Comparison of HZ Values ===")
    print("Higher HZ (1000): Better precision, more frequent interrupts")
    print("Lower HZ (100): Less precision, fewer interrupts, better for battery")
