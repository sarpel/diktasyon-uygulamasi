"""Sesli komutlar: "yeni satır", "yeni paragraf", "son cümleyi sil", "son kelimeyi sil".

"geri al" metne uygulanmaz: yalnızca tüm söyleyiş bu ifadeden ibaretse `is_undo_command`
bunu tanır; çağıran taraf yapıştırmak yerine geri alma kısayolu gönderir.

Noktalama komutları ("noktalı virgül" vb.) bilinçli olarak desteklenmez — Türkçede bu
ifadeler gerçek kelime/deyim olarak da kullanılır, komut sanılıp yanlışlıkla değiştirilebilir.
"""

from __future__ import annotations

import re

_NEWLINE_RE = re.compile(r"\s*yeni sat[ıi]r(?!\w)\s*[,.]?\s*", re.IGNORECASE)
_PARAGRAPH_RE = re.compile(r"\s*yeni paragraf(?!\w)\s*[,.]?\s*", re.IGNORECASE)
_DELETE_LAST_SENTENCE_RE = re.compile(r"\s*son cümleyi sil(?!\w)\s*[,.]?\s*", re.IGNORECASE)
_DELETE_LAST_WORD_RE = re.compile(r"\s*son kelimeyi sil(?!\w)\s*[,.]?\s*", re.IGNORECASE)
# Nokta cümle sonudur; iki istisna: rakam izliyorsa ("14.30" saat, "3.5" ondalık) ve
# rakamdan sonra gelip küçük harfle devam ediyorsa ("3. madde" sıra sayısı). "14.30." ve
# "Madde 3. Yeni cümle" içindeki son noktalar cümle sonu sayılır.
_SENTENCE_END_RE = re.compile(r"[!?]|\.(?!\d|(?<=\d\.)\s+[a-zçğıöşüâîû])")
# Metnin sonundaki cümle sonu noktalaması: Whisper komutu ayrı bir cümle olarak
# noktaladığında önceki cümleyi bitiren nokta, silinecek cümlenin kendi noktasıdır.
_TRAILING_SENTENCE_END_RE = re.compile(r"[.!?…]+$")
# Son kelime, yapışık noktalamasıyla birlikte ("dünya," / "dünya.").
_LAST_WORD_RE = re.compile(r"\S*\w\S*\W*$")
_UNDO_RE = re.compile(r"\s*geri al\s*[.!?,…]*\s*")


def _capitalize_turkish(text: str) -> str:
    """`str.capitalize()`in İngilizce `i`→`I` kuralını Türkçe `i`→`İ` ile değiştirir."""
    if not text:
        return text
    first = "İ" if text[0] == "i" else text[0].upper()
    return first + text[1:]


def _apply_break(text: str, pattern: re.Pattern[str], replacement: str) -> str:
    match = pattern.search(text)
    while match:
        text = text[: match.start()] + replacement + _capitalize_turkish(text[match.end() :])
        match = pattern.search(text)
    return text


def _without_last_sentence(before: str) -> tuple[str, bool]:
    body = _TRAILING_SENTENCE_END_RE.sub("", before.rstrip())
    boundary = 0
    for punct in _SENTENCE_END_RE.finditer(body):
        boundary = punct.end()
    return body[:boundary].rstrip(), True


def _without_last_word(before: str) -> tuple[str, bool]:
    kept = _LAST_WORD_RE.sub("", before.rstrip()).rstrip()
    return kept, not kept or kept[-1] in ".!?…"


_DELETIONS = (
    (_DELETE_LAST_SENTENCE_RE, _without_last_sentence),
    (_DELETE_LAST_WORD_RE, _without_last_word),
)


def _next_deletion(text: str):
    found = [(m, cut) for pattern, cut in _DELETIONS if (m := pattern.search(text))]
    return min(found, key=lambda pair: pair[0].start(), default=None)


def _apply_deletions(text: str) -> str:
    """Silme komutlarını soldan sağa, söylendikleri sırayla uygular."""
    pending = _next_deletion(text)
    while pending:
        match, cut = pending
        kept, new_sentence = cut(text[: match.start()])
        tail = text[match.end() :].lstrip()
        if new_sentence:
            tail = _capitalize_turkish(tail)
        text = f"{kept} {tail}".strip() if kept and tail else (kept or tail)
        pending = _next_deletion(text)
    return text


def is_undo_command(text: str) -> bool:
    """Söyleyişin tamamı "geri al" ise (büyük/küçük harf, İ/ı ve sondaki noktalama
    fark etmeksizin) True döner; "parayı geri al" gibi cümle içi kullanımlar komut değildir."""
    folded = text.replace("İ", "i").replace("I", "i").replace("ı", "i").lower()
    return _UNDO_RE.fullmatch(folded) is not None


def apply_commands(text: str) -> str:
    """Metindeki sesli komutları uygular: önce silme komutları (söylendikleri sırayla),
    sonra "yeni satır"/"yeni paragraf" kırılımları; kırılımdan sonraki harf büyütülür."""
    text = _apply_deletions(text)
    text = _apply_break(text, _NEWLINE_RE, "\n")
    text = _apply_break(text, _PARAGRAPH_RE, "\n\n")
    return text
