import re
from pathlib import Path

content_file = Path(r"C:\Users\tanvi\.gemini\antigravity-ide\brain\3b847d11-2af1-4f7a-a308-563002970d06\.system_generated\steps\13091\content.md")
with open(content_file, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

sections = ["prizes", "build", "judging", "faq", "rules"]
for sec in sections:
    pos = text.find(f'id="{sec}"')
    if pos != -1:
        chunk = text[pos:pos+5000]
        clean = re.sub(r"<[^>]+>", " ", chunk)
        clean = " ".join(clean.split())
        print(f"=== SECTION: {sec.upper()} ===")
        print(clean[:1500])
        print("\n" + "="*50 + "\n")
