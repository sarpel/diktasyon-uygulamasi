# Güvenlik politikası

## Desteklenen sürümler

Güvenlik düzeltmeleri yalnızca en son yayımlanan sürüme ve `main` dalına yapılır.

## Güvenlik açığı bildirme

**Lütfen güvenlik açıklarını herkese açık bir issue olarak bildirmeyin.**

Bunun yerine GitHub'ın özel bildirim özelliğini kullanın:

1. Repodaki **Security** sekmesine gidin.
2. **Report a vulnerability** düğmesine basın.
3. Açığı, etkilediği sürümü ve mümkünse yeniden üretme adımlarını yazın.

Bildiriminiz yalnızca proje sahibine görünür. Makul bir süre içinde yanıt verilir; düzeltme
yayımlanınca, isterseniz adınızla teşekkür edilir.

## Kapsam

Özellikle şunlarla ilgili bildirimler önemlidir:

- API anahtarlarının diske yazılması, loglanması veya arayüzde görünmesi.
- Dikte metninin, geçmişin veya kayıtlı sesin başka kullanıcılar ya da süreçler tarafından okunabilmesi.
- Yerel IPC soketi üzerinden başka bir kullanıcının uygulamayı tetikleyebilmesi.
- Kurulum paketi veya Linux kurulum betiğinde yetki yükseltme.

Kapsam dışı olanlar:

- Kullanıcının kendi seçtiği uzak LLM sağlayıcısına metin gönderilmesi (belgelenmiş davranış).
- Üçüncü taraf bağımlılıklardaki açıklar. Bunları ilgili projeye bildirin; Dikte'yi doğrudan
  etkiliyorsa burada da haber verebilirsiniz.
