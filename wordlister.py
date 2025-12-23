#!/usr/bin/env python3

import threading
import asyncio
from queue import Queue, Empty
from pathlib import Path
from itertools import product
from typing import List, Set
import time

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Button, Input, Label, ProgressBar, Checkbox, Select
from textual.reactive import reactive
from textual import work
from textual.binding import Binding
from textual.screen import Screen


class PasswordGenerator:
    
    
    LEET_MAP = {
        'a': ['a', '4', '@'],
        'e': ['e', '3'],
        'i': ['i', '1', '!'],
        'o': ['o', '0'],
        's': ['s', '5', '$'],
        't': ['t', '7'],
        'l': ['l', '1'],
        'g': ['g', '9'],
    }
    
    SEPARATORS = ['', '-', '_', '.']
    CAPS_PATTERNS = ['lower', 'upper', 'title', 'first']
    
    @staticmethod
    def apply_caps(word: str, pattern: str) -> str:
        
        if pattern == 'lower':
            return word.lower()
        elif pattern == 'upper':
            return word.upper()
        elif pattern == 'title':
            return word.title()
        elif pattern == 'first':
            return word[0].upper() + word[1:].lower() if word else word
        return word
    
    @staticmethod
    def apply_leet(word: str, intensity: int = 1) -> List[str]:
        
        if intensity == 0:
            return [word]
        
        results = [word]
        word_lower = word.lower()
        
        if intensity >= 1:
            for char, replacements in PasswordGenerator.LEET_MAP.items():
                if char in word_lower:
                    for repl in replacements[1:2]:
                        new_word = word.replace(char, repl)
                        new_word = new_word.replace(char.upper(), repl)
                        if new_word != word:
                            results.append(new_word)
        
        return list(set(results))
    
    @staticmethod
    def generate_variations(words: List[str], year: str = "", depth: int = 2, 
                          use_leet: bool = True, use_caps: bool = True) -> Set[str]:
        
        variations = set()
        
        for word in words:
            caps_list = PasswordGenerator.CAPS_PATTERNS if use_caps else ['lower']
            for cap_pattern in caps_list:
                base = PasswordGenerator.apply_caps(word, cap_pattern)
                
                leet_intensity = min(depth, 1) if use_leet else 0
                for leet_word in PasswordGenerator.apply_leet(base, leet_intensity):
                    variations.add(leet_word)
                    
                    if year:
                        variations.add(f"{leet_word}{year}")
                        variations.add(f"{year}{leet_word}")
                        
                        if depth >= 2:
                            for sep in PasswordGenerator.SEPARATORS[:2]:
                                if sep:
                                    variations.add(f"{leet_word}{sep}{year}")
                                    variations.add(f"{year}{sep}{leet_word}")
        
        if depth >= 2 and len(words) >= 2:
            for w1, w2 in product(words[:min(3, len(words))], repeat=2):
                if w1 != w2:
                    caps_combos = [('lower', 'title'), ('title', 'lower')] if use_caps else [('lower', 'lower')]
                    for cap1, cap2 in caps_combos:
                        base1 = PasswordGenerator.apply_caps(w1, cap1)
                        base2 = PasswordGenerator.apply_caps(w2, cap2)
                        
                        for sep in PasswordGenerator.SEPARATORS[:2]:
                            combo = f"{base1}{sep}{base2}"
                            variations.add(combo)
                            
                            if year and depth >= 3:
                                variations.add(f"{combo}{year}")
        
        
        if depth >= 2:
            common_suffixes = ['!', '123', '1']
            for word in words:
                caps_list = ['lower', 'title'] if use_caps else ['lower']
                for cap_pattern in caps_list:
                    base = PasswordGenerator.apply_caps(word, cap_pattern)
                    for suffix in common_suffixes:
                        variations.add(f"{base}{suffix}")
        
        return variations


class GenerationEngine:
   
    
    def __init__(self, output_file: str, num_threads: int):
        self.output_file = output_file
        self.num_threads = num_threads
        self.stop_flag = threading.Event()
        self.counter = 0
        self.lock = threading.Lock()
        self.result_queue = Queue(maxsize=10000)
        self.writer_thread = None
        
    def worker_task(self, words: List[str], year: str, depth: int, 
                   use_leet: bool, use_caps: bool) -> int:
       
        if self.stop_flag.is_set():
            return 0
            
        variations = PasswordGenerator.generate_variations(words, year, depth, use_leet, use_caps)
        count = 0
        
        for password in variations:
            if self.stop_flag.is_set():
                break
            self.result_queue.put(password)
            count += 1
            
        return count
    
    def writer_worker(self):
        
        with open(self.output_file, 'w') as f:
            while not self.stop_flag.is_set() or not self.result_queue.empty():
                try:
                    password = self.result_queue.get(timeout=0.1)
                    f.write(f"{password}\n")
                    f.flush()
                    with self.lock:
                        self.counter += 1
                except Empty:
                    continue
    
    def generate(self, words: List[str], year: str, depth: int = 2, 
                use_leet: bool = True, use_caps: bool = True):
        
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        self.writer_thread = threading.Thread(target=self.writer_worker, daemon=True)
        self.writer_thread.start()
        
        word_chunks = []
        if len(words) <= 3:
            word_chunks = [words]
        else:
            for i in range(0, len(words), 2):
                chunk = words[i:i+3]
                if len(chunk) >= 1:
                    word_chunks.append(chunk)
        
        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            futures = []
            for chunk in word_chunks:
                if self.stop_flag.is_set():
                    break
                future = executor.submit(self.worker_task, chunk, year, depth, use_leet, use_caps)
                futures.append(future)
            
            for future in as_completed(futures):
                if self.stop_flag.is_set():
                    break
                try:
                    future.result()
                except Exception as e:
                    print(f"Error: {e}")
        
        self.stop_flag.set()
        if self.writer_thread:
            self.writer_thread.join(timeout=5)
    
    def stop(self):
        
        self.stop_flag.set()
        if self.writer_thread:
            self.writer_thread.join(timeout=5)
    
    def get_count(self) -> int:
        
        with self.lock:
            return self.counter


class HelpScreen(Screen):
    
    
    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
    ]
    
    def compose(self) -> ComposeResult:
        with Container(id="help-container"):
            with Vertical(classes="help-box"):
                yield Label(" Wordlister - Help", classes="help-title")
                yield Label("")
                yield Label(" Usage Guide:", classes="help-section")
                yield Label("• Enter comma-separated words (e.g., company, admin, password)")
                yield Label("• Optionally add a significant year (e.g., 2024)")
                yield Label("• Choose depth level (1-3) for more combinations")
                yield Label("• Enable/disable leetspeak and capitalization")
                yield Label("")
                yield Label(" Generation Patterns:", classes="help-section")
                yield Label("• Case variations: lower, UPPER, Title, First")
                yield Label("• Leetspeak: a→4, e→3, i→1, o→0, s→5, t→7")
                yield Label("• Word combinations with separators (-, _, .)")
                yield Label("• Year appending/prepending")
                yield Label("• Common suffixes (!, 123, 1)")
                yield Label("")
                yield Label(" Performance Modes:", classes="help-section")
                yield Label("• Normal: Uses half your CPU threads")
                yield Label("• ThreadRipper: Unleashes all CPU threads")
                yield Label("")
                yield Label(" Keyboard Shortcuts:", classes="help-section")
                yield Label("• s - Start/Stop generation")
                yield Label("• h - Show this help")
                yield Label("• t - Cycle themes")
                yield Label("• q - Quit application")
                yield Label("")
                yield Button("Close", id="close-help", variant="primary")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()
    
    def action_dismiss(self) -> None:
        self.dismiss()


class WordlisterApp(App):
    
    
    CSS = """
    Screen {
        background: $surface;
    }
    
    #main-container {
        height: 100%;
        padding: 1;
    }
    
    .box {
        border: solid $primary;
        padding: 1;
        margin: 1;
    }
    
    #input-section {
        height: auto;
    }
    
    #controls {
        height: auto;
        margin-top: 1;
    }
    
    #options {
        height: auto;
        margin-top: 1;
    }
    
    #stats {
        height: auto;
        margin-top: 1;
    }
    
    .stat-value {
        color: $success;
        text-style: bold;
    }
    
    .section-title {
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }
    
    ProgressBar {
        margin-top: 1;
    }
    
    Button {
        margin: 0 1;
    }
    
    Input {
        margin: 1 0;
    }
    
    Checkbox {
        margin: 0 2 0 0;
    }
    
    Select {
        margin: 1 0;
    }
    
    /* Help Screen */
    #help-container {
        align: center middle;
    }
    
    .help-box {
        width: 80;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 2;
    }
    
    .help-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    
    .help-section {
        text-style: bold;
        color: $primary;
        margin-top: 1;
    }
    
    #close-help {
        width: 100%;
        margin-top: 2;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("s", "toggle_generation", "Start/Stop"),
        Binding("h", "show_help", "Help"),
        Binding("t", "cycle_theme", "Theme"),
    ]
    
    THEMES = ["textual-dark", "textual-light", "dracula", "monokai", "nord", "gruvbox", "catppuccin-mocha", "catppuccin-latte", "tokyo-night", "rose-pine", "rose-pine-moon", "rose-pine-dawn"]
    
    password_count = reactive(0)
    is_generating = reactive(False)
    current_theme_index = reactive(0)
    
    def __init__(self):
        super().__init__()
        self.engine = None
        self.generation_thread = None
        self.start_time = None
        self.theme = self.THEMES[0]
        
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with ScrollableContainer(id="main-container"):
            with Vertical(id="input-section", classes="box"):
                yield Label(" Input Configuration", classes="section-title")
                yield Label("Words (comma-separated):")
                yield Input(
                    placeholder="password, admin, user, company",
                    id="words-input"
                )
                yield Label("Significant Year (optional):")
                yield Input(
                    placeholder="2024",
                    id="year-input"
                )
                yield Label("Output File:")
                yield Input(
                    value="wordlist.txt",
                    id="output-input"
                )
                yield Label("Depth (1-3, higher = more combinations):")
                yield Select(
                    options=[("Light (1)", "1"), ("Medium (2)", "2"), ("Heavy (3)", "3")],
                    value="2",
                    id="depth-select"
                )
            
            with Horizontal(id="options", classes="box"):
                with Vertical():
                    yield Label(" Generation Options", classes="section-title")
                    yield Checkbox("Enable Leetspeak (a→4, e→3, i→1)", id="leet-check", value=True)
                    yield Checkbox("Enable Case Variations", id="caps-check", value=True)
            
            with Horizontal(id="controls", classes="box"):
                yield Button(" Start", id="start-btn", variant="success")
                yield Button("  Stop", id="stop-btn", variant="error", disabled=True)
                yield Button(" Use ThreadRipper", id="ripper-btn", variant="warning")
                yield Button(" Help", id="help-btn", variant="primary")
            
            with Vertical(id="stats", classes="box"):
                yield Label(" Statistics", classes="section-title")
                yield Label("Status: Idle", id="status-label")
                yield Label("Passwords Generated: 0", id="count-label")
                yield Label("Threads Used: 0", id="cores-label")
                yield Label("Speed: 0 pwd/sec", id="speed-label")
                yield Label(f"Theme: {self.THEMES[0]}", id="theme-label")
                yield ProgressBar(total=100, show_eta=False, id="progress-bar")
        
        yield Footer()  # lol footer sounds funny
    
    def on_mount(self) -> None:
        self.title = "Wordlister - Password Wordlist Generator"
        self.sub_title = "Realistic human-pattern password generation"
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start-btn":
            self.start_generation()
        elif event.button.id == "stop-btn":
            self.stop_generation()
        elif event.button.id == "ripper-btn":
            self.start_generation(threadripper=True)
        elif event.button.id == "help-btn":
            self.push_screen(HelpScreen())
    
    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())
    
    def action_cycle_theme(self) -> None:
        self.current_theme_index = (self.current_theme_index + 1) % len(self.THEMES)
        new_theme = self.THEMES[self.current_theme_index]
        self.theme = new_theme
        self.query_one("#theme-label", Label).update(f"Theme: {new_theme}")
        self.notify(f"Switched to {new_theme} theme")
    
    def start_generation(self, threadripper: bool = False):
        """Start the password generation process"""
        words_input = self.query_one("#words-input", Input).value
        year_input = self.query_one("#year-input", Input).value
        output_file = self.query_one("#output-input", Input).value
        depth_input = self.query_one("#depth-select", Select).value
        use_leet = self.query_one("#leet-check", Checkbox).value
        use_caps = self.query_one("#caps-check", Checkbox).value
        
        if not words_input.strip():
            self.notify("Please enter words", severity="error")
            self.query_one("#status-label", Label).update(" Error: Please enter words")
            return
        
        words = [w.strip() for w in words_input.split(",") if w.strip()]
        year = year_input.strip()
        
        try:
            depth = int(depth_input)
            depth = max(1, min(3, depth))
        except:
            depth = 2
        
        # Determine thread count
        import os
        cpu_count = os.cpu_count() or 4
        if threadripper:
            num_threads = cpu_count
            mode = "ThreadRipper"
        else:
            num_threads = max(1, cpu_count // 2)
            mode = "Normal"
        
        self.cores_used = num_threads
        
        # Create engine
        self.engine = GenerationEngine(output_file, num_threads)
        
        # Start generation in background thread
        def run_generation():
            self.engine.generate(words, year, depth, use_leet, use_caps)
            self.is_generating = False
        
        self.generation_thread = threading.Thread(target=run_generation, daemon=True)
        self.generation_thread.start()
        
        self.is_generating = True
        self.start_time = time.time()
        self._last_update_time = time.time()
        self._last_update_count = 0
        
        # Update UI
        self.query_one("#start-btn", Button).disabled = True
        self.query_one("#stop-btn", Button).disabled = False
        self.query_one("#ripper-btn", Button).disabled = True
        self.query_one("#status-label", Label).update(f"🔄 Generating ({mode} mode)...")
        self.notify(f"Generation started with {num_threads} threads", severity="information")
        
        # Set progress bar to indeterminate
        progress_bar = self.query_one("#progress-bar", ProgressBar)
        progress_bar.update(total=None)
        
        # Start monitoring with interval timer
        self.monitor_progress()
        
        # Start checking for completion
        self.check_completion()
    
    def monitor_progress(self):
        
        self.set_interval(0.5, self.update_progress_callback)
    
    def update_progress_callback(self):
        
        if not self.is_generating:
            return
            
        # Update stats
        if self.engine:
            count = self.engine.get_count()
            self.password_count = count
            
            self.query_one("#count-label", Label).update(
                f"Passwords Generated: {count:,}"
            )
            self.query_one("#cores-label", Label).update(
                f"Threads Used: {self.cores_used}"
            )
            
            # Calculate speed
            current_time = time.time()
            if not hasattr(self, '_last_update_time'):
                self._last_update_time = self.start_time
                self._last_update_count = 0
            
            time_diff = current_time - self._last_update_time
            if time_diff >= 1.0:
                speed = (count - self._last_update_count) / time_diff
                self.query_one("#speed-label", Label).update(
                    f"Speed: {int(speed):,} pwd/sec"
                )
                self._last_update_time = current_time
                self._last_update_count = count
    
    def check_completion(self):
        """Check if generation is complete"""
        if self.generation_thread and not self.generation_thread.is_alive():
            self.on_generation_complete()
        elif self.is_generating:
            self.set_timer(0.5, self.check_completion)
    
    def on_generation_complete(self):
        """Called when generation completes"""
        self.is_generating = False
        
        # Final update
        if self.engine:
            count = self.engine.get_count()
            self.password_count = count
            self.query_one("#count-label", Label).update(
                f"Passwords Generated: {count:,}"
            )
        
        self.query_one("#status-label", Label).update(
            f" Complete! Generated {self.password_count:,} passwords"
        )
        progress_bar = self.query_one("#progress-bar", ProgressBar)
        progress_bar.update(progress=100, total=100)
        self.notify(f"Generation complete: {self.password_count:,} passwords", severity="success")
        
        # Re-enable buttons
        self.query_one("#start-btn", Button).disabled = False
        self.query_one("#stop-btn", Button).disabled = True
        self.query_one("#ripper-btn", Button).disabled = False
    
    def stop_generation(self):
        """Stop the generation process"""
        if self.engine:
            self.engine.stop()
        
        self.is_generating = False
        
        # Update UI
        self.query_one("#start-btn", Button).disabled = False
        self.query_one("#stop-btn", Button).disabled = True
        self.query_one("#ripper-btn", Button).disabled = False
        
        if self.engine:
            count = self.engine.get_count()
            self.query_one("#status-label", Label).update(
                f"  Stopped. Generated {count:,} passwords"
            )
            self.notify(f"Generation stopped: {count:,} passwords", severity="warning")
    
    def action_toggle_generation(self):
        
        if self.is_generating:
            self.stop_generation()
        else:
            self.start_generation()


def main():
    
    app = WordlisterApp()
    app.run()


if __name__ == "__main__":
    main()
