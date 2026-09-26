## Ne değişti ve neden

<!-- Kısa özet. İlgili issue varsa: Closes #123 -->

## Nasıl test edildi

<!-- Eklenen/değişen testler; gerçek cihazda denendiyse ortam (Windows/Linux, GPU). -->

## Kontrol listesi

- [ ] `ruff check src tests scripts` ve `ruff format --check src tests scripts` temiz
- [ ] `pyright` temiz
- [ ] `pytest` geçiyor; yeni davranış için test eklendi
- [ ] Kullanıcıya görünen metinler Türkçe ve tam diakritikli
- [ ] Yeni ayar alanlarının varsayılan değeri var (eski `config.json` bozulmuyor)
- [ ] Kullanıcıya görünen değişiklikler için `docs/` ve `CHANGELOG.md` güncellendi
- [ ] Gerçek donanım gerektiren davranış için `docs/manual_test_checklist.md`'ye madde eklendi
