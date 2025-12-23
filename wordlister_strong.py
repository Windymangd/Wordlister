import asyncio
from itertools import product
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import (
    Header, Footer, Button, Input, Checkbox, ProgressBar, Static
)
from textual.containers import Vertical, Horizontal


# ======================
# Mutation logic
# ======================

def case_variants(word):
    return {word.lower(), word.upper(), word.capitalize()}


def leet_variants(word):
def leet_variants(word):
    leet = {
        'a': ['a', 'A', '@', '4'],
        'b': ['b', 'B', '8'],
        'c': ['c', 'C', '('],
        'd': ['d', 'D'],
        'e': ['e', 'E', '3'],
        'f': ['f', 'F'],
        'g': ['g', 'G', '6', '9'],
        'h': ['h', 'H', '#'],
        'i': ['i', 'I', '1', '!'],
        'j': ['j', 'J'],
        'k': ['k', 'K'],
        'l': ['l', 'L', '1', '|'],
        'm': ['m', 'M'],
        'n': ['n', 'N'],
        'o': ['o', 'O', '0'],
        'p': ['p', 'P'],
        'q': ['q', 'Q'],
        'r': ['r', 'R'],
        's': ['s', 'S', '$', '5'],
        't': ['t', 'T', '7', '+'],
        'u': ['u', 'U'],
        'v': ['v', 'V'],
        'w': ['w', 'W'],
        'x': ['x', 'X'],
        'y': ['y', 'Y'],
        'z': ['z', 'Z', '2'],
    }
    pools = [leet.get(c.lower(), [c]) for c in word]
    return {''.join(p) for p in product(*pools)}


def mutate_final(word, use_case, use_leet):
    variants = {word}
    if use_case:
        variants = set().union(*(case_variants(v) for v in variants))
    if use_leet:
        variants = set().union(*(leet_variants(v) for v in variants))
    return variants


# ======================
# Smart pattern logic
# ======================

def split_words(words):
    names = []
    numbers = []
    for w in words:
        if w.isdigit() and len(w) in (2, 4):
            numbers.append(w)
        else:
            names.append(w)
    return names, numbers


def combine_words(names, numbers):
    separators = ["", ".", "_"]
    symbols = ["", "@", "!"]

    results = set()

    # name + name patterns
    for a in names:
        for b in names:
            if a == b:
                continue
            for sep in separators:
                base = f"{a}{sep}{b}"
                results.add(base)
                for num in numbers:
                    for sym in symbols:
                        results.add(f"{base}{sym}{num}")
                        results.add(f"{num}{base}")

    # name + year patterns
    for name in names:
        for num in numbers:
            for sym in symbols:
                results.add(f"{name}{sym}{num}")
                results.add(f"{num}{name}")

    return results


# ======================
# Estimation (progress)
# ======================

def estimate_total(base_words, use_case, use_leet):
    total = 0
    for w in base_words:
        count = 1
        if use_case:
            count *= 3
        if use_leet:
            count *= 3 ** len(w)
        total += count

    names, numbers = split_words(base_words)
    combos = len(combine_words(names, numbers))
    if use_case:
        combos *= 3
    if use_leet and names:
        combos *= 3 ** max(len(n) for n in names)

    return max(total + combos, 1)


# ======================
# Async generator
# ======================

async def generate_words_smart(base_words, use_case, use_leet):
    seen = set()

    names, numbers = split_words(base_words)

    #  Original single-word mutations
    for w in base_words:
        for v in mutate_final(w, use_case, use_leet):
            if v not in seen:
                seen.add(v)
                yield v
                await asyncio.sleep(0)

    #  Smart human patterns
    combos = combine_words(names, numbers)
    for combo in combos:
        for v in mutate_final(combo, use_case, use_leet):
            if v not in seen:
                seen.add(v)
                yield v
                await asyncio.sleep(0)


# ======================
# TUI App
# ======================

class WordlistTUI(App):
    CSS = "Screen { layout: vertical; padding: 1; }"
    generating = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Static("Base words (names, keywords, years):")
            yield Input(id="base")

            with Horizontal():
                yield Checkbox("Case variants", id="case", value=True)
                yield Checkbox("Leetspeak", id="leet", value=True)

            yield Input(id="outfile", placeholder="Output file (default: wordlist.txt)")

            with Horizontal():
                yield Button("Generate", id="start")
                yield Button("Stop", id="stop", disabled=True)

            yield ProgressBar(id="progress")
            yield Static("Generated: 0", id="count")

        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "start" and not self.generating:
            await self.start_generation()
        elif event.button.id == "stop":
            self.generating = False

    async def start_generation(self):
        base_input = self.query_one("#base", Input).value
        base_words = base_input.replace(",", " ").split()

        if not base_words:
            self.notify("No base words provided", severity="error")
            return

        use_case = self.query_one("#case", Checkbox).value
        use_leet = self.query_one("#leet", Checkbox).value

        outfile = Path(self.query_one("#outfile", Input).value or "wordlist.txt")

        progress = self.query_one("#progress", ProgressBar)
        count_label = self.query_one("#count", Static)

        total = estimate_total(base_words, use_case, use_leet)
        progress.total = total
        progress.progress = 0

        self.generating = True
        self.query_one("#start", Button).disabled = True
        self.query_one("#stop", Button).disabled = False

        count = 0

        with outfile.open("w", encoding="utf-8") as f:
            async for word in generate_words_smart(base_words, use_case, use_leet):
                if not self.generating:
                    break
                f.write(word + "\n")
                count += 1
                progress.advance(1)
                count_label.update(f"Generated: {count}")

        self.generating = False
        self.query_one("#start", Button).disabled = False
        self.query_one("#stop", Button).disabled = True
        self.notify(f"Done — {count} entries written")


if __name__ == "__main__":
    WordlistTUI().run()
