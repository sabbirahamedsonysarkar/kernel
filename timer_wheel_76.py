class TimerWheel:
    """
    A Python representation of the Linux Kernel Timer Wheel logic.
    Based on the actual kernel code from timer.c.
    """
    def __init__(self, hz):
        # Store the HZ value (system timer frequency)
        self.hz = hz
        # Conversion factor: nanoseconds per second
        self.nsec_per_sec = 1_000_000_000
        
        # Kernel constants from the C code:
        # #define LVL_CLK_SHIFT	3
        self.LVL_CLK_SHIFT = 3
        # #define LVL_CLK_DIV	(1UL << LVL_CLK_SHIFT)  // 8
        self.LVL_CLK_DIV = 1 << self.LVL_CLK_SHIFT  # 8
        
        # #define LVL_BITS	6
        self.LVL_BITS = 6
        # #define LVL_SIZE	(1UL << LVL_BITS)  // 64
        self.LVL_SIZE = 1 << self.LVL_BITS  # 64
        # #define LVL_MASK	(LVL_SIZE - 1)  // 63
        self.LVL_MASK = self.LVL_SIZE - 1
        
        # Level depth depends on HZ (from the C preprocessor logic)
        # #if HZ > 100
        # # define LVL_DEPTH	9
        # # else
        # # define LVL_DEPTH	8
        # #endif
        self.LVL_DEPTH = 9 if hz > 100 else 8
        
        # Pre-calculate level granularities and start offsets
        self.level_gran = []    # Will store LVL_GRAN(n) for each level
        self.level_start = []   # Will store LVL_START(n) for each level
        
        # Calculate for each level (0 to LVL_DEPTH)
        # Note: We need LVL_START(LVL_DEPTH) for WHEEL_TIMEOUT_CUTOFF
        # So we calculate one extra
        for n in range(self.LVL_DEPTH + 1):  # +1 to include LVL_DEPTH
            # LVL_GRAN(n) = 1UL << LVL_SHIFT(n)
            # LVL_SHIFT(n) = ((n) * LVL_CLK_SHIFT)
            # So: 1 << (n * 3)
            self.level_gran.append(1 << (n * self.LVL_CLK_SHIFT))
            
            # LVL_START(n) = ((LVL_SIZE - 1) << (((n) - 1) * LVL_CLK_SHIFT))
            if n == 0:
                # Level 0 starts at 0
                self.level_start.append(0)
            else:
                # For level n, start = 63 << ((n-1) * 3)
                self.level_start.append(
                    (self.LVL_SIZE - 1) << ((n - 1) * self.LVL_CLK_SHIFT)
                )
        
        # Calculate cutoff and max timeout
        # #define WHEEL_TIMEOUT_CUTOFF	(LVL_START(LVL_DEPTH))
        self.WHEEL_TIMEOUT_CUTOFF = self.level_start[self.LVL_DEPTH]
        
        # #define WHEEL_TIMEOUT_MAX	(WHEEL_TIMEOUT_CUTOFF - LVL_GRAN(LVL_DEPTH - 1))
        self.WHEEL_TIMEOUT_MAX = (
            self.WHEEL_TIMEOUT_CUTOFF - self.level_gran[self.LVL_DEPTH - 1]
        )
    
    def get_base_tick_ms(self):
        """Get base tick duration in milliseconds."""
        # For HZ=1000: 1000/1000 = 1ms per tick
        # For HZ=250: 1000/250 = 4ms per tick
        # For HZ=100: 1000/100 = 10ms per tick
        return 1000 // self.hz
    
    def level_offset(self, n):
        """LVL_OFFS(n) = ((n) * LVL_SIZE)"""
        # Level 0: offset 0, Level 1: offset 64, Level 2: offset 128, etc.
        return n * self.LVL_SIZE
    
    def time_to_index(self, expires, clk):
        """
        Convert absolute expiry time to wheel index.
        This simulates calc_index() in kernel.
        """
        # Calculate delta = expires - clk (how many ticks in the future)
        delta = expires - clk
        
        # Find the appropriate level by comparing delta with LVL_START values
        # This is the logic from the kernel's calc_index() function
        if delta < self.level_start[1]:
            level = 0
        elif delta < self.level_start[2]:
            level = 1
        elif delta < self.level_start[3]:
            level = 2
        elif delta < self.level_start[4]:
            level = 3
        elif delta < self.level_start[5]:
            level = 4
        elif delta < self.level_start[6]:
            level = 5
        elif delta < self.level_start[7]:
            level = 6
        elif delta < self.level_start[8]:
            level = 7
        else:
            # For level 8 (only if LVL_DEPTH > 8)
            if self.LVL_DEPTH > 8 and delta < self.level_start[9]:
                level = 8
            else:
                # Beyond wheel capacity
                return None
        
        # Calculate bucket index within the level
        # This is: (expires >> (LVL_CLK_SHIFT * level)) & LVL_MASK
        # The kernel does: (expires >> (LVL_CLK_SHIFT * level)) & LVL_MASK
        idx = (expires >> (self.LVL_CLK_SHIFT * level)) & self.LVL_MASK
        
        # Add the level offset to get the wheel index
        # Total index = LVL_OFFS(level) + bucket_index
        return self.level_offset(level) + idx
    
    def analyze(self):
        """Analyze the timer wheel exactly as shown in kernel comments."""
        # Get the base tick duration in milliseconds
        tick_ms = self.get_base_tick_ms()
        
        # Print header information
        print(f"=== Timer Wheel Analysis for HZ = {self.hz} ===")
        print(f"Base tick duration: {tick_ms} ms")
        print(f"Level depth: {self.LVL_DEPTH}")
        print(f"Wheel timeout cutoff: {self.WHEEL_TIMEOUT_CUTOFF} ticks")
        print(f"Wheel timeout max: {self.WHEEL_TIMEOUT_MAX} ticks")
        print("-" * 65)
        
        # Print table header
        print(f"{'Level':<6} {'Offset':<8} {'Granularity':<20} {'Range (approx)'}")
        print("-" * 65)
        
        # Analyze each level
        for level in range(self.LVL_DEPTH):
            # 1. Calculate offset in the wheel array
            # LVL_OFFS(n) = n * 64
            offset = self.level_offset(level)
            
            # 2. Calculate granularity in ticks
            # LVL_GRAN(level) = 1 << (level * 3)
            gran_ticks = self.level_gran[level]
            # Convert to milliseconds
            gran_ms = gran_ticks * tick_ms
            
            # 3. Calculate range for this level
            # Level 0 starts at 0 ticks
            # Level 1 starts at LVL_START(1) = 63 ticks
            # Level 2 starts at LVL_START(2) = 63 << 3 = 504 ticks
            # etc.
            start_ticks = self.level_start[level]
            
            # The level ends at the start of the next level
            # Except for the last level, which ends at WHEEL_TIMEOUT_MAX
            if level < self.LVL_DEPTH - 1:
                end_ticks = self.level_start[level + 1]
            else:
                end_ticks = self.WHEEL_TIMEOUT_MAX
            
            # Convert ticks to milliseconds
            start_ms = start_ticks * tick_ms
            end_ms = end_ticks * tick_ms
            
            # Format granularity string for display
            if gran_ms < 1000:
                gran_str = f"{gran_ms:.0f} ms"
            elif gran_ms < 60000:  # less than 1 minute
                gran_str = f"{gran_ms/1000:.0f} s"
            elif gran_ms < 3600000:  # less than 1 hour
                gran_str = f"{gran_ms/60000:.0f} min"
            else:  # hours or more
                gran_str = f"{gran_ms/3600000:.0f} h"
            
            # Helper function to format time ranges
            def format_time(ms):
                if ms < 1000:
                    return f"{ms:.0f} ms"
                elif ms < 60000:  # less than 1 minute
                    return f"{ms/1000:.0f} s"
                elif ms < 3600000:  # less than 1 hour
                    return f"{ms/60000:.1f} min"
                elif ms < 86400000:  # less than 1 day
                    return f"{ms/3600000:.1f} h"
                else:  # days or more
                    return f"{ms/86400000:.1f} days"
            
            # Create the range string
            range_str = f"{format_time(start_ms)} - {format_time(end_ms)}"
            
            # Print the row for this level
            print(f"{level:<6} {offset:<8} {gran_str:<20} {range_str}")
        
        print("-" * 65)
        
        # Calculate and print maximum timer delay
        total_ms = self.WHEEL_TIMEOUT_MAX * tick_ms
        print(f"Maximum timer delay: {format_time(total_ms)}")


# Add this main execution block
if __name__ == "__main__":
    # Test with the exact HZ values from kernel comments
    test_hz_values = [1000, 300, 250, 100]
    
    for hz in test_hz_values:
        wheel = TimerWheel(hz)
        wheel.analyze()
        print()  # Add blank line between outputs
    
    # Optional: Demonstrate timer enqueue
    print("\n=== Timer Enqueue Example ===")
    wheel = TimerWheel(1000)
    print("For HZ=1000, timer of 100ms delay:")
    print(f"Wheel index: {wheel.time_to_index(100, 0)}")
