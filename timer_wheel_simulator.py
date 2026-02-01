#!/usr/bin/env python3
"""
Timer Wheel Simulation - Pure Python version
Simulates the Linux kernel timer wheel logic
"""

import math
from dataclasses import dataclass
from typing import List, Optional, Dict
from collections import defaultdict

@dataclass
class TimerWheelConfig:
    """Configuration matching kernel timer wheel constants"""
    HZ: int
    LVL_CLK_SHIFT: int = 3
    LVL_BITS: int = 6
    
    def __post_init__(self):
        self.LVL_CLK_DIV = 1 << self.LVL_CLK_SHIFT
        self.LVL_SIZE = 1 << self.LVL_BITS
        self.LVL_MASK = self.LVL_SIZE - 1
        
        # Level depth depends on HZ
        self.LVL_DEPTH = 9 if self.HZ > 100 else 8
        
        # Pre-calculate level values
        self.level_gran = []      # LVL_GRAN(n)
        self.level_start = []     # LVL_START(n)
        
        for n in range(self.LVL_DEPTH + 1):
            self.level_gran.append(1 << (n * self.LVL_CLK_SHIFT))
            if n == 0:
                self.level_start.append(0)
            else:
                self.level_start.append(
                    (self.LVL_SIZE - 1) << ((n - 1) * self.LVL_CLK_SHIFT)
                )
        
        # Wheel capacity
        self.WHEEL_TIMEOUT_CUTOFF = self.level_start[self.LVL_DEPTH]
        self.WHEEL_TIMEOUT_MAX = (
            self.WHEEL_TIMEOUT_CUTOFF - self.level_gran[self.LVL_DEPTH - 1]
        )
        self.WHEEL_SIZE = self.LVL_SIZE * self.LVL_DEPTH
        
    def get_tick_ms(self):
        """Get milliseconds per tick"""
        return 1000 // self.HZ

@dataclass
class Timer:
    """Represents a timer in the wheel"""
    id: str
    expires: int          # Absolute expiry time in ticks
    callback: callable
    data: any = None
    wheel_index: Optional[int] = None

class TimerWheelSimulator:
    """Simulates the Linux kernel timer wheel"""
    
    def __init__(self, HZ: int = 1000):
        self.config = TimerWheelConfig(HZ)
        self.clock = 0  # Current time in ticks
        
        # Wheel data structures
        self.vectors = [[] for _ in range(self.config.WHEEL_SIZE)]
        self.pending_map = [0] * self.config.WHEEL_SIZE
        
        # Statistics
        self.timers_added = 0
        self.timers_expired = 0
        self.timers_cancelled = 0
        
    def calc_index(self, expires: int) -> Optional[int]:
        """Calculate wheel index for a timer (kernel's calc_index)"""
        delta = expires - self.clock
        
        # Find level
        level = None
        for lvl in range(self.config.LVL_DEPTH):
            if lvl == self.config.LVL_DEPTH - 1:
                if delta < self.config.WHEEL_TIMEOUT_MAX:
                    level = lvl
                break
            
            if delta < self.config.level_start[lvl + 1]:
                level = lvl
                break
        
        if level is None:
            return None  # Beyond wheel capacity
        
        # Calculate bucket
        bucket = (expires >> (self.config.LVL_CLK_SHIFT * level)) & self.config.LVL_MASK
        return (level * self.config.LVL_SIZE) + bucket
    
    def add_timer(self, timeout_ms: int, callback: callable, timer_id: str = None, data=None) -> Timer:
        """Add a timer with given timeout in milliseconds"""
        if timer_id is None:
            timer_id = f"timer_{self.timers_added}"
        
        timeout_ticks = timeout_ms // self.config.get_tick_ms()
        expires = self.clock + timeout_ticks
        
        # Calculate wheel index
        idx = self.calc_index(expires)
        
        if idx is None:
            # Force to maximum
            expires = self.clock + self.config.WHEEL_TIMEOUT_MAX
            idx = self.config.WHEEL_SIZE - 1
            print(f"⚠️  Timer {timer_id}: Timeout {timeout_ms}ms exceeds wheel capacity!")
            print(f"   Forced to maximum: {self.config.WHEEL_TIMEOUT_MAX} ticks")
        
        # Create and store timer
        timer = Timer(
            id=timer_id,
            expires=expires,
            callback=callback,
            data=data,
            wheel_index=idx
        )
        
        self.vectors[idx].append(timer)
        self.pending_map[idx] = 1
        self.timers_added += 1
        
        # Calculate level and bucket for info
        level = idx // self.config.LVL_SIZE
        bucket = idx % self.config.LVL_SIZE
        
        print(f"✅ Timer {timer_id} added:")
        print(f"   Timeout: {timeout_ms}ms ({timeout_ticks} ticks)")
        print(f"   Expires at: tick {expires} (current: {self.clock})")
        print(f"   Wheel index: {idx} (Level {level}, Bucket {bucket})")
        print(f"   Granularity: {self.config.level_gran[level]} ticks")
        
        # Show expiration window
        window_start = bucket << (level * self.config.LVL_CLK_SHIFT)
        window_end = ((bucket + 1) << (level * self.config.LVL_CLK_SHIFT)) - 1
        actual_expire = max(window_start, min(expires, window_end))
        
        tick_ms = self.config.get_tick_ms()
        print(f"   Will fire between: {window_start}-{window_end} ticks")
        print(f"   ({window_start*tick_ms}-{window_end*tick_ms} ms)")
        print(f"   Possible delay: {actual_expire - timeout_ticks} ticks")
        
        return timer
    
    def advance_time(self, ms_to_advance: int):
        """Advance time and process expired timers"""
        tick_ms = self.config.get_tick_ms()
        ticks_to_advance = ms_to_advance // tick_ms
        
        print(f"\n⏰ Advancing time by {ms_to_advance}ms ({ticks_to_advance} ticks)")
        print(f"   Current time: {self.clock} ticks ({self.clock * tick_ms}ms)")
        
        expired_in_this_advance = 0
        
        for _ in range(ticks_to_advance):
            self.clock += 1
            
            # Check each level for expired buckets
            for level in range(self.config.LVL_DEPTH):
                # Calculate which bucket to check at this level
                bucket = (self.clock >> (self.config.LVL_CLK_SHIFT * level)) & self.config.LVL_MASK
                idx = (level * self.config.LVL_SIZE) + bucket
                
                # Process timers in this bucket
                if self.pending_map[idx] and self.vectors[idx]:
                    timers_to_keep = []
                    
                    for timer in self.vectors[idx]:
                        if timer.expires <= self.clock:
                            # Timer expired!
                            expired_in_this_advance += 1
                            self.timers_expired += 1
                            
                            # Execute callback
                            try:
                                timer.callback(timer.id, timer.data, self.clock)
                            except Exception as e:
                                print(f"   ❌ Error in timer {timer.id} callback: {e}")
                        else:
                            # Timer not expired yet, keep it
                            timers_to_keep.append(timer)
                    
                    # Update bucket
                    self.vectors[idx] = timers_to_keep
                    if not timers_to_keep:
                        self.pending_map[idx] = 0
        
        if expired_in_this_advance:
            print(f"   {expired_in_this_advance} timer(s) expired")
        
        remaining = sum(len(bucket) for bucket in self.vectors)
        print(f"   After advance: {remaining} timers pending")
        
        return expired_in_this_advance
    
    def print_wheel_analysis(self):
        """Print detailed analysis of the timer wheel"""
        tick_ms = self.config.get_tick_ms()
        
        print("\n" + "="*80)
        print(f"TIMER WHEEL ANALYSIS - HZ={self.config.HZ}")
        print("="*80)
        
        print(f"\nConfiguration:")
        print(f"  HZ: {self.config.HZ} (tick every {tick_ms}ms)")
        print(f"  LVL_DEPTH: {self.config.LVL_DEPTH}")
        print(f"  WHEEL_SIZE: {self.config.WHEEL_SIZE} buckets")
        print(f"  WHEEL_TIMEOUT_MAX: {self.config.WHEEL_TIMEOUT_MAX} ticks")
        
        max_ms = self.config.WHEEL_TIMEOUT_MAX * tick_ms
        max_seconds = max_ms / 1000
        days = max_seconds / 86400
        print(f"  Maximum timeout: {max_ms:,.0f} ms ({max_seconds:,.1f} s, ~{days:.1f} days)")
        
        print(f"\nLevel Details:")
        print(f"{'Level':<6} {'Offset':<8} {'Granularity':<15} {'Range (ticks)':<25} {'Range (ms)':<25}")
        print("-"*80)
        
        for level in range(self.config.LVL_DEPTH):
            offset = level * self.config.LVL_SIZE
            gran_ticks = self.config.level_gran[level]
            gran_ms = gran_ticks * tick_ms
            
            start_ticks = self.config.level_start[level]
            if level < self.config.LVL_DEPTH - 1:
                end_ticks = self.config.level_start[level + 1]
            else:
                end_ticks = self.config.WHEEL_TIMEOUT_MAX
            
            start_ms = start_ticks * tick_ms
            end_ms = end_ticks * tick_ms
            
            # Format granularity
            if gran_ms < 1000:
                gran_str = f"{gran_ms:.0f} ms"
            elif gran_ms < 60000:
                gran_str = f"{gran_ms/1000:.0f} s"
            else:
                gran_str = f"{gran_ms/60000:.0f} min"
            
            range_ticks = f"{start_ticks:,} - {end_ticks:,}"
            range_ms = f"{start_ms:,.0f} - {end_ms:,.0f}"
            
            print(f"{level:<6} {offset:<8} {gran_str:<15} {range_ticks:<25} {range_ms:<25}")
        
        print("="*80)
    
    def print_current_state(self):
        """Print current state of the wheel"""
        tick_ms = self.config.get_tick_ms()
        
        print(f"\nCurrent state:")
        print(f"  Clock: {self.clock} ticks ({self.clock * tick_ms}ms)")
        print(f"  Pending timers: {sum(len(bucket) for bucket in self.vectors)}")
        
        # Show non-empty buckets
        non_empty = [(i, bucket) for i, bucket in enumerate(self.vectors) if bucket]
        if non_empty:
            print(f"  Non-empty buckets ({len(non_empty)}):")
            for idx, bucket in non_empty:
                level = idx // self.config.LVL_SIZE
                bucket_num = idx % self.config.LVL_SIZE
                print(f"    Index {idx:3d} (L{level}, B{bucket_num:2d}): {len(bucket)} timers")
                for timer in bucket:
                    remaining = timer.expires - self.clock
                    print(f"      Timer {timer.id}: expires in {remaining} ticks ({remaining * tick_ms}ms)")
    
    def run_demo(self):
        """Run a complete demonstration"""
        print("\n" + "="*80)
        print("TIMER WHEEL DEMONSTRATION")
        print("="*80)
        
        self.print_wheel_analysis()
        
        # Timer callback function
        def timer_callback(timer_id, data, current_time):
            tick_ms = self.config.get_tick_ms()
            print(f"   🔔 Timer {timer_id} fired at tick {current_time} ({current_time * tick_ms}ms)")
            if data:
                print(f"     Data: {data}")
        
        # Add test timers
        print("\n" + "-"*80)
        print("ADDING TEST TIMERS")
        print("-"*80)
        
        test_timeouts = [
            (10, "Short timer (10ms)"),
            (100, "Medium timer (100ms)"),
            (500, "Long timer (500ms)"),
            (1000, "Very long timer (1s)"),
            (5000, "Very very long timer (5s)"),
        ]
        
        timers = []
        for timeout_ms, description in test_timeouts:
            timer = self.add_timer(timeout_ms, timer_callback, description, f"data_{timeout_ms}")
            timers.append(timer)
        
        # Show initial state
        self.print_current_state()
        
        # Advance time in steps
        print("\n" + "-"*80)
        print("ADVANCING TIME")
        print("-"*80)
        
        advance_steps = [50, 50, 100, 300, 1000, 4000]
        total_advanced = 0
        
        for step_ms in advance_steps:
            print(f"\nAdvancing {step_ms}ms...")
            self.advance_time(step_ms)
            total_advanced += step_ms
            print(f"Total advanced: {total_advanced}ms")
            self.print_current_state()
        
        # Final statistics
        print("\n" + "="*80)
        print("FINAL STATISTICS")
        print("="*80)
        print(f"Timers added: {self.timers_added}")
        print(f"Timers expired: {self.timers_expired}")
        print(f"Timers still pending: {sum(len(bucket) for bucket in self.vectors)}")
        print(f"Final clock: {self.clock} ticks ({self.clock * self.config.get_tick_ms()}ms)")
        print("="*80)

def main():
    """Main function to run the simulation"""
    # Test different HZ values
    test_hz_values = [1000, 300, 250, 100]
    
    for hz in test_hz_values:
        print(f"\n\n{'#'*80}")
        print(f"RUNNING SIMULATION FOR HZ = {hz}")
        print(f"{'#'*80}")
        
        simulator = TimerWheelSimulator(hz)
        simulator.run_demo()

if __name__ == "__main__":
    main()
