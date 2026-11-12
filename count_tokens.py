"""Count the tokens in data/shop_handbook.md with tiktoken (o200k_base encoding)."""

from pathlib import Path

import tiktoken

HERE = Path(__file__).parent
text = (HERE / "data" / "shop_handbook.md").read_text(encoding="utf-8")

enc = tiktoken.get_encoding("o200k_base")
tokens = enc.encode(text)

print(f"characters: {len(text):,}")
print(f"words:      {len(text.split()):,}")
print(f"tokens:     {len(tokens):,}  (o200k_base)")
print(f"chars/token: {len(text) / len(tokens):.2f}")
