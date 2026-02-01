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
        
        # Initialize wheel data structures
        self.wheel_size = self.LVL_SIZE * self.LVL_DEPTH  # WHEEL_SIZE
        self.pending_map = [0] * self.wheel_size  # bitmap of pending timers
        self.vectors = [[] for _ in range(self.wheel_size)]  # timer lists per bucket
        
        # Current clock (in ticks)
        self.clk = 0
        
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
    
    def calc_index(self, expires):
        """
        Convert absolute expiry time to wheel index.
        This simulates calc_index() in kernel.
        """
        # Calculate delta = expires - clk (how many ticks in the future)
        delta = expires - self.clk
        
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
        idx = (expires >> (self.LVL_CLK_SHIFT * level)) & self.LVL_MASK
        
        # Add the level offset to get the wheel index
        # Total index = LVL_OFFS(level) + bucket_index
        return self.level_offset(level) + idx
    
    def add_timer(self, timer_id, timeout_ms):
        """Add a timer with given timeout in milliseconds."""
        tick_ms = self.get_base_tick_ms()
        timeout_ticks = timeout_ms // tick_ms
        expires = self.clk + timeout_ticks
        
        # Calculate wheel index
        idx = self.calc_index(expires)
        
        if idx is None:
            print(f"Timer {timer_id}: Timeout {timeout_ms}ms exceeds wheel capacity!")
            return None
        
        # Store timer in the bucket
        timer_data = {
            'id': timer_id,
            'expires': expires,
            'timeout_ms': timeout_ms,
            'wheel_idx': idx
        }
        self.vectors[idx].append(timer_data)
        self.pending_map[idx] = 1  # Mark bucket as non-empty
        
        print(f"Timer {timer_id} added:")
        print(f"  Timeout: {timeout_ms}ms ({timeout_ticks} ticks)")
        print(f"  Expires at: tick {expires} (current clk: {self.clk})")
        print(f"  Wheel index: {idx}")
        
        # Show which bucket this corresponds to
        level = idx // self.LVL_SIZE
        bucket = idx % self.LVL_SIZE
        print(f"  Level: {level}, Bucket: {bucket}")
        print(f"  Granularity: {self.level_gran[level]} ticks")
        
        return idx
    
    def advance_time(self, ms_to_advance):
        """Advance time by given milliseconds and process expired timers."""
        tick_ms = self.get_base_tick_ms()
        ticks_to_advance = ms_to_advance // tick_ms
        
        print(f"\n{'='*60}")
        print(f"Advancing time by {ms_to_advance}ms ({ticks_to_advance} ticks)")
        print(f"Current clk: {self.clk} -> New clk: {self.clk + ticks_to_advance}")
        print(f"{'='*60}")
        
        # Process each tick
        for tick in range(1, ticks_to_advance + 1):
            new_clk = self.clk + tick
            
            # The key insight: Each time the clock advances,
            # we check which buckets have expired timers
            
            # For each level, we calculate which bucket to check
            expired_count = 0
            
            print(f"\nTick {new_clk}:")
            
            # Check each level for expired buckets
            for level in range(self.LVL_DEPTH):
                # Calculate which bucket should fire at this tick for this level
                # The bucket index formula is similar to calc_index but for current time
                bucket_idx = (new_clk >> (self.LVL_CLK_SHIFT * level)) & self.LVL_MASK
                wheel_idx = self.level_offset(level) + bucket_idx
                
                # Only process if this bucket has pending timers
                if self.pending_map[wheel_idx]:
                    # Check if timers in this bucket have expired
                    timers_to_process = []
                    timers_to_keep = []
                    
                    for timer in self.vectors[wheel_idx]:
                        if timer['expires'] <= new_clk:
                            timers_to_process.append(timer)
                            expired_count += 1
                        else:
                            timers_to_keep.append(timer)
                    
                    # Update the bucket
                    self.vectors[wheel_idx] = timers_to_keep
                    if not timers_to_keep:
                        self.pending_map[wheel_idx] = 0
                    
                    # Process expired timers
                    for timer in timers_to_process:
                        actual_delay = new_clk - (timer['expires'] - timer['timeout_ms'] // self.get_base_tick_ms())
                        print(f"  ✓ Timer {timer['id']} expired (scheduled for tick {timer['expires']})")
                        print(f"    Actual delay: {actual_delay} ticks")
                        print(f"    From bucket: Level {level}, Bucket {bucket_idx}, Index {wheel_idx}")
            
            if expired_count > 0:
                print(f"  Total expired: {expired_count}")
        
        # Update the clock
        self.clk += ticks_to_advance
        
        # Return remaining timers
        remaining = sum(len(bucket) for bucket in self.vectors)
        print(f"\nAfter advancing: {remaining} timers remain")
        return remaining
    
    def run_simulation(self):
        """Run a complete simulation showing timer expiration."""
        print(f"\n{'='*60}")
        print(f"TIMER WHEEL SIMULATION - HZ={self.hz}")
        print(f"{'='*60}")
        
        # Add some timers
        print("\n=== Adding Timers ===")
        self.add_timer("A", 100)   # 100ms timer
        self.add_timer("B", 50)    # 50ms timer  
        self.add_timer("C", 150)   # 150ms timer
        self.add_timer("D", 75)    # 75ms timer
        
        # Show current state
        print("\n=== Initial Wheel State ===")
        self.print_wheel_state()
        
        # Advance time in steps to see expiration
        print("\n=== Time Progression ===")
        
        # Advance 25ms
        self.advance_time(25)
        self.print_wheel_state()
        
        # Advance 25ms more (total 50ms) - Timer B should expire
        self.advance_time(25)
        self.print_wheel_state()
        
        # Advance 25ms more (total 75ms) - Timer D should expire
        self.advance_time(25)
        self.print_wheel_state()
        
        # Advance 25ms more (total 100ms) - Timer A should expire
        self.advance_time(25)
        self.print_wheel_state()
        
        # Advance 50ms more (total 150ms) - Timer C should expire
        self.advance_time(50)
        self.print_wheel_state()
    
    def print_wheel_state(self):
        """Print current state of the timer wheel."""
        print(f"\nCurrent time: {self.clk} ticks ({self.clk * self.get_base_tick_ms()}ms)")
        print(f"Pending timers: {sum(len(bucket) for bucket in self.vectors)}")
        
        # Show non-empty buckets
        print("Non-empty buckets:")
        for idx, bucket in enumerate(self.vectors):
            if bucket:
                level = idx // self.LVL_SIZE
                bucket_num = idx % self.LVL_SIZE
                print(f"  Index {idx:3d} (Level {level}, Bucket {bucket_num:2d}): {len(bucket)} timers")
                for timer in bucket:
                    remaining = timer['expires'] - self.clk
                    print(f"    Timer {timer['id']}: expires in {remaining} ticks ({remaining * self.get_base_tick_ms()}ms)")
    
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
        print(f"Total wheel size: {self.wheel_size} buckets")
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


# Demonstration of how index 76 gets triggered
def demonstrate_expiration_process():
    print("\n" + "="*60)
    print("DEMONSTRATING EXPIRATION PROCESS")
    print("How index 76 actually gets triggered when time advances")
    print("="*60)
    
    # Create timer wheel for HZ=1000 (1ms per tick)
    wheel = TimerWheel(1000)
    
    # Let's trace through a specific example
    print("\n1. Adding a 100ms timer at time 0:")
    idx = wheel.add_timer("TEST", 100)
    
    if idx == 76:
        print(f"\n2. Timer placed at index {idx}. Let's understand why:")
        level = idx // wheel.LVL_SIZE  # 76 // 64 = 1
        bucket = idx % wheel.LVL_SIZE  # 76 % 64 = 12
        print(f"   Index {idx} corresponds to:")
        print(f"   - Level {level} (offset: {wheel.level_offset(level)})")
        print(f"   - Bucket {bucket} within that level")
        print(f"   - Granularity: {wheel.level_gran[level]} ticks ({wheel.level_gran[level]}ms)")
        
        # Show the calculation
        print(f"\n3. Calculation of bucket index:")
        print(f"   For level {level}, bucket = (expires >> (3 * {level})) & 63")
        print(f"   Timer expires at tick 100")
        print(f"   bucket = (100 >> {3*level}) & 63 = (100 >> 3) & 63")
        print(f"          = {100 >> 3} & 63 = {100 >> 3} & 63")
        print(f"          = {100 >> 3} & 63 = {(100 >> 3) & 63}")
        
        print(f"\n4. When does this bucket get checked?")
        print(f"   For level {level}, we check bucket when:")
        print(f"   (current_time >> (3 * {level})) & 63 == {bucket}")
        print(f"   So when current_time >> 3 == {bucket}")
        
        print(f"\n5. Let's find when bucket {bucket} fires:")
        print(f"   We need (t >> 3) == {bucket}")
        print(f"   So t must be in range [{bucket << 3} .. {((bucket + 1) << 3) - 1}]")
        print(f"   That's ticks [{bucket << 3} .. {((bucket + 1) << 3) - 1}]")
        print(f"   Which is [{bucket << 3}ms .. {((bucket + 1) << 3) - 1}ms]")
        
        print(f"\n6. Our timer expires at tick 100:")
        print(f"   Is 100 in range [{bucket << 3} .. {((bucket + 1) << 3) - 1}]?")
        lower = bucket << 3  # 12 << 3 = 96
        upper = ((bucket + 1) << 3) - 1  # 104 - 1 = 103
        print(f"   Range: {lower} to {upper}")
        print(f"   100 is in {lower}..{upper}: ✓ YES")
        
        print(f"\n7. Timer will fire sometime between ticks {lower} and {upper}")
        print(f"   (That's {lower}ms to {upper}ms)")
        print(f"   So it might fire up to {upper - 100}ms late (but that's OK for timeouts)")
    
    # Now simulate the expiration
    print("\n" + "="*60)
    print("SIMULATING TIME ADVANCEMENT")
    print("="*60)
    
    # Reset and run simulation
    wheel = TimerWheel(1000)
    wheel.clk = 0
    wheel.vectors = [[] for _ in range(wheel.wheel_size)]
    wheel.pending_map = [0] * wheel.wheel_size
    
    # Add our timer
    wheel.add_timer("EXP", 100)
    
    # Advance time to just before expiration
    print("\nAdvancing to tick 95 (just before expiration range):")
    wheel.advance_time(95)
    
    # Advance through the expiration range
    print("\nAdvancing through expiration range (96-103):")
    wheel.advance_time(10)  # Takes us through 96-105
    
    return wheel


# Main execution
if __name__ == "__main__":
    # Run the demonstration
    wheel = demonstrate_expiration_process()
    
    # Also show analysis for different HZ values
    print("\n" + "="*60)
    print("QUICK ANALYSIS FOR DIFFERENT HZ VALUES")
    print("="*60)
    
    for hz in [1000, 300, 250, 100]:
        wheel = TimerWheel(hz)
        print(f"\nHZ={hz}: Max delay: {wheel.WHEEL_TIMEOUT_MAX * wheel.get_base_tick_ms() / 1000:.1f}s")
