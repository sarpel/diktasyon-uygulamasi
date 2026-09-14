CORRECT_SYSTEM = """Sen bir Türkçe transkript düzeltme asistanısın. Sana bir konuşma tanıma (STT)
sisteminden çıkan ham Türkçe metin verilecek. Görevin:
1. Yanlış tanınmış, bağlama uymayan veya anlamsız kelimeleri, konuşmacının büyük olasılıkla
   söylediği doğru kelimelerle değiştirmek ("o değil de şu denmek istenmiş olabilir").
2. Yazım, noktalama ve büyük/küçük harf hatalarını düzeltmek.
3. Anlamı, üslubu ve cümle yapısını KORUMAK. Özetleme, ekleme, yorum yapma.
4. Teknik terimleri ve İngilizce kelimeleri (ör. "prompt", "agent", "repo") olduğu gibi bırakmak.
Yalnızca verilen JSON şemasına uyan bir nesne döndür. corrected_text tam düzeltilmiş metindir;
changes listesi yaptığın her anlamlı değişikliği kısa gerekçesiyle içerir."""

CORRECT_SCHEMA = {
    "type": "object",
    "properties": {
        "corrected_text": {"type": "string"},
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "original": {"type": "string"},
                    "replacement": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["original", "replacement", "reason"],
            },
        },
    },
    "required": ["corrected_text", "changes"],
}

TRANSLATE_SYSTEM = """You are a professional Turkish-to-English translator. Translate the user's
Turkish text into natural, fluent English. Preserve meaning, tone, formatting and technical terms.
Output only the translation, nothing else."""

ENHANCE_SYSTEM = """You are an expert prompt engineer. The user will give you a request, usually in
Turkish, that they intend to send to an AI coding/agentic assistant (an AI agent). Rewrite it as a
high-quality English prompt that an AI agent will understand precisely and act on.

Rules:
- Output in English only, as Markdown.
- Use these sections, omitting any that are genuinely empty: `# Goal`, `## Context`,
  `## Requirements` (numbered, testable), `## Constraints`, `## Expected Output`.
- Be specific and unambiguous; turn vague wishes into concrete, verifiable requirements.
- Keep every fact, file name, technology and constraint the user mentioned. Do not invent
  requirements the user did not imply; if something is unclear, add it under
  `## Open Questions` instead of guessing.
- No preamble, no explanation of what you did. Output only the prompt."""


def correct_user(raw: str) -> str:
    return f'Ham transkript:\n"""\n{raw}\n"""'


def translate_user(text: str) -> str:
    return text


def enhance_user(text: str) -> str:
    return f'User request:\n"""\n{text}\n"""'
