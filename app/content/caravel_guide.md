# Caravel tape-out rehberi — {{PROJECT_ID}}

Bu dosya, **LibreLane web arayüzündeki 5 adım** ile **gerçek tape-out** arasındaki farkı ve Caravel / IO pad wrapper rolünü açıklar.

---

## Önemli: GDS ≠ tape-out

| Kavram | Ne demek? |
|--------|-----------|
| **Wrapper GDS** (web adım 5) | Caravel’in size ayırdığı **user project alanının** layout dosyası (`user_project_wrapper`). |
| **Tape-out GDS** | Pad halkası + harness + yönetim SoC ile **fabrikaya gidebilecek tam çip** GDS’i. |

**Adım 5 bittiğinde elinizde GDS olur, ama iş tape-out için bitmiş sayılmaz.** Simülasyon sonrası “her şey tamam” hissi yanıltıcıdır: 1–4 RTL kontrolü, 5 fiziksel **wrapper** layout’udur.

---

## Web arayüzü — 5 + 5.1 adım

Derleme sekmesindeki şerit:

| Adım | Araç | GDS? | Tape-out? |
|------|------|------|-----------|
| **1** | Lint | Hayır | Hayır |
| **2** | Sentez | Hayır (`netlist.v`) | Hayır |
| **3** | Doğrulama | Hayır | Hayır |
| **4** | Simülasyon | Hayır (`.vcd`) | Hayır |
| **5** | OpenLane1 Flow | **Evet — wrapper GDS** | **Hayır** (henüz tam çip değil) |
| **5.1** | Caravel + IO pad wrapper | **Evet — tam çip GDS** | **Evet** (MPW / shuttle) |

### Adım 5’te `user_project_wrapper` nerede?

Ayrı bir düğme yok; **baştan projede vardır**:

- `verilog/rtl/user_project_wrapper.v` — Caravel portları + sizin IP bağlantısı
- `openlane/user_project_wrapper/config.json` — adım 5’in kullandığı ayarlar

Adım 5, bu RTL’yi OpenLane ile layout’a çevirir → `runs/.../final/gds/*.gds`.

### Adım 5.1 — Tape-out (web dışı + rehber)

**5.1**, şu an web’de otomatik job olarak yok; **manuel / Efabless araçları** ile yapılır:

1. Adım 5’ten **wrapper GDS + LEF** alın.
2. **[caravel_user_project](https://github.com/efabless/caravel_user_project)** + **Caravel harness** repo’sunu kullanın.
3. **IO pad wrapper (padframe):** PDK pad hücreleri, `chip_io` / padring, pin sırası — harness içindeki `interactive.tcl` ve `caravel/README.md`.
4. `USE_GPIO_PADS`, `GPIO_PADS_VERILOG`, `EXTRA_LEFS` vb. ile pad’ler OpenLane tam-çip akışına dahil edilir (ayrı “pad sentez” butonu değil, aynı pipeline’ın parçası).
5. Birleşik layout signoff → **tape-out GDS**.

Detay: `caravel/README.md`

---

## Büyük resim (derinlik — 3 seviye)

```text
┌─────────────────────────────────────────────────────────────┐
│ 5.1 / Seviye 3 — Tape-out (tam çip GDS)                      │
│     Caravel harness + IO pad wrapper + wrapper GDS birleşimi │
├─────────────────────────────────────────────────────────────┤
│ 5 / Seviye 2 — user_project_wrapper Flow (WEB)               │
│     → Wrapper GDS (user alanı) — TAPE-OUT DEĞİL            │
├─────────────────────────────────────────────────────────────┤
│ Seviye 1 — user_module (opsiyonel macro-first)               │
│     → Macro GDS/LEF — ikinci Flow, user_module config        │
├─────────────────────────────────────────────────────────────┤
│ 1–4 — Lint, sentez, doğrulama, sim (WEB) — GDS yok           │
└─────────────────────────────────────────────────────────────┘
```

| Seviye | OpenLane design | Çıktı | Nerede? |
|--------|-----------------|-------|---------|
| 1 | `user_module` | Macro GDS/LEF | İkinci OpenLane1 Flow (`openlane/user_module/`) |
| 2 | `user_project_wrapper` | Wrapper GDS/LEF | Web adım **5** |
| 3 | Harness + padframe | **Tape-out GDS** | Web adım **5.1** (harici) |

---

## Aşama 0 — RTL doğrulama (web 1–4, GDS yok)

| Araç | Ne yapar? | Çıktı |
|------|-----------|--------|
| **Lint** | Hiyerarşi / okunabilirlik | Log |
| **Sentez** | Gate-level netlist | `netlist.v` |
| **Simülasyon** | Testbench | `.vcd`, `sim.vvp` |
| **Doğrulama** | Hızlı RTL stat | Log |

RTL: `verilog/rtl/` (`user_module.v`, `user_project_wrapper.v`).

---

## Beklenen dizin yapısı (Caravel user project)

Efabless [caravel_user_project](https://github.com/efabless/caravel_user_project) ile uyumlu iskelet. “İstediğimiz gibi” dağınık `.v` koymak simülasyon için bazen yeterlidir; **MPW / tape-out** için bu yapıya uymak gerekir.

```text
proje_koku/
├── guide.md                          # Bu rehber
├── README.md
├── flow.tcl                          # OpenLane 1 giriş (adım 5)
├── verilog/rtl/                      # Tüm sentezlenebilir RTL (asıl kaynak)
│   ├── defines.v                     # MPRJ_IO_PADS vb. ortak define'lar
│   ├── user_module.v                 # Sizin IP (ör. sayaç, UART, …)
│   ├── user_project_wrapper.v        # Caravel pin listesi + user_module örneği
│   └── …                             # Ek modüller (ör. counter10.v) — aşağıya bakın
├── tb/                               # Yalnızca testbench (.v)
│   ├── tb_user_project_wrapper.v     # Caravel wrapper sim (tb_*.v)
│   └── …                             # İsteğe bağlı ayrı bench (*_tb.v) — tek tek sim
├── openlane/
│   ├── user_module/                  # Opsiyonel: IP’yi önce macro olarak harden
│   │   └── config.json
│   └── user_project_wrapper/         # Web adım 5 — wrapper hardening
│       ├── config.json
│       └── pin_order.cfg
├── runs/                             # OpenLane çıktıları (GDS, log)
├── caravel/README.md                 # Adım 5.1 harness notları
├── plans/                            # AI plan modu
└── src/README.txt                    # Eski yol; yeni RTL buraya değil → verilog/rtl/
```

| Yol | Ne koyulur? | Ne koyulmaz? |
|-----|-------------|--------------|
| `verilog/rtl/` | Modül kaynakları (`.v`), `defines.v` | Testbench |
| `tb/` | `tb_*.v`, `*_tb.v` testbench | RTL modül kaynağı |
| `openlane/<design>/` | `config.json`, `pin_order.cfg` | RTL |
| Proje kökü | `flow.tcl`, `guide.md` | Çok sayıda dağınık `.v` (kaçının) |

**Web araçları hangi dosyayı okur?**

| Araç | Okuduğu yer |
|------|-------------|
| Lint / Sentez / Doğrulama | `verilog/rtl/*.v` (yoksa `src/*.v`) |
| Simülasyon | `verilog/rtl/*.v` + **tek** testbench: önce `tb/tb_*.v`, yoksa `tb/*_tb.v` |
| OpenLane1 Flow | `flow.tcl` + `openlane/user_project_wrapper/config.json` |

Simülasyonda `tb/*.v` **hepsi birden** derlenmez; Caravel için `tb/tb_user_project_wrapper.v` kullanın.

---

## Kendi devrenizi nereye koymalısınız? (örnek: `counter10.v`)

0–10 sayan bir sayaç (`counter10`) için tipik Caravel yolu:

### Yol A — Önerilen (tek IP = `user_module`)

1. RTL dosyası: `verilog/rtl/counter10.v` — `module counter10 (...);`
2. `verilog/rtl/user_module.v` içinde `counter10` örneğini bağlayın (portlar: `clk`, `rst_n`, `la_data_out` vb.).
3. `user_project_wrapper.v` **değiştirmeyin** (zaten `user_module` örneğini içerir).
4. Simülasyon: web adım **4** veya `tb/tb_user_project_wrapper.v` — tüm wrapper test edilir.
5. Layout: adım **5** (`user_project_wrapper`).

Bu, Efabless’in “user space = user_module” modeline uyar.

### Yol B — Sadece `user_module.v` içine yazmak

Küçük IP için ayrı dosya şart değil: sayaç kodunu doğrudan `verilog/rtl/user_module.v` içine yazın. Adım 5 ve sim aynı kalır.

### Yol C — Sadece bench ile hızlı deneme (Caravel dışı)

| Dosya | Konum |
|-------|--------|
| `counter10.v` | `verilog/rtl/counter10.v` |
| `counter10_tb.v` | `tb/counter10_tb.v` veya `tb/tb_counter10.v` |

Sim komutunda **yalnızca** bu iki dosyayı derleyin; `tb_user_project_wrapper.v` ile **aynı anda** derlemeyin. Bu yol tape-out wrapper’ını test etmez.

### Yapılmaması gerekenler

- `counter10.v` → `tb/` altına **koymayın** (testbench değil).
- Proje köküne tek başına `counter10.v` → web araçları bulamayabilir.
- `tb/counter_tb.v` + `tb/tb_user_project_wrapper.v` → **birlikte** simülasyon job’una vermeyin (çakışır).

### Macro-first (ileri)

IP büyükse önce `openlane/user_module/` Flow ile macro GDS/LEF, sonra wrapper `config.json` içinde `EXTRA_LEFS` / `EXTRA_GDS_FILES` (Efabless dokümantasyonu).

---

## Aşama 1 — IP macro (isteğe bağlı)

1. `verilog/rtl/user_module.v` — donanım IP’niz (Internet Protocol değil).
2. `openlane/user_module/config.json`
3. OpenLane1 Flow (bu config ile)
4. Çıktı: macro GDS/LEF → wrapper’a `EXTRA_LEFS` / `EXTRA_GDS_FILES` ile eklenebilir.

---

## Aşama 2 — Web adım 5 (wrapper GDS)

1. `user_project_wrapper.v` + `openlane/user_project_wrapper/config.json`
2. Web: **OpenLane1 Flow**
3. **Wrapper GDS** `runs/` altında — **tape-out değil**

---

## Aşama 3 — Web adım 5.1 (tape-out)

- Pad halkası (IO pad wrapper) + Caravel harness + önceki wrapper GDS/LEF
- `caravel/README.md` + Efabless dokümantasyonu
- Çıktı: **tam çip GDS** (shuttle / MPW)

---

## IO pad wrapper (kısa)

- Pad hücreleri sky130 PDK’dan gelir.
- Tam çipte OpenLane config ile pad LEF/Verilog birleştirilir.
- Wrapper-only Flow (adım 5) tek başına pad halkalı tape-out üretmez.

---

## Checklist

- [ ] 1–4: Lint / sentez / sim
- [ ] (Opsiyonel) `user_module` Flow → macro GDS/LEF
- [ ] **5:** `user_project_wrapper` Flow → **wrapper GDS** (iş burada bitmez)
- [ ] **5.1:** Caravel harness + IO pad wrapper → **tape-out GDS**

---

## GDS / KLayout görüntüleme (web)

| Yol | Ne yapar? |
|-----|-----------|
| Dosya ağacından `.gds` | Layout sekmesi açılır (varsayılan: **KLayout** modu) |
| **Hızlı** | Tarayıcıda poligon önizleme (katman detayı sınırlı) |
| **KLayout** | Backend OpenLane imajında KLayout → **PNG 2560×1440 (1440p)** |
| **OpenLane1 Flow bittiğinde** | Sunucu otomatik `layout_klayout_1440p.png` üretir; job önizleme sekmesinde gösterilir (`_jobs/<job_id>/`) |
| PNG yoksa | Aynı sekmede GDS için tarayıcı önizlemesi |

Flow çıktısındaki GDS `runs/.../final/gds/` altında kalır; PNG job artefaktıdır, tape-out dosyası değildir.

Tam interaktif KLayout web’de yok; detay için dosyayı indirip masaüstü KLayout kullanın.

## Dosya özeti

| Yol | Rol |
|-----|-----|
| `verilog/rtl/` | Tüm modül RTL + `defines.v` |
| `verilog/rtl/user_module.v` | Sizin IP veya IP örneği |
| `verilog/rtl/user_project_wrapper.v` | Caravel pinleri (adım 5 design) |
| `tb/tb_*.v` | Wrapper simülasyonu |
| `openlane/user_project_wrapper/` | Web adım 5 config |
| `openlane/user_module/` | Opsiyonel macro config |
| `flow.tcl` | OpenLane giriş |
| `runs/` | Wrapper GDS (adım 5) |
| `caravel/README.md` | Adım 5.1 harness |

```bash
make sim
```

Kaynaklar: [Caravel User Project](https://caravel-user-project.readthedocs.io/) · [Caravel Harness](https://caravel-harness.readthedocs.io/) · [OpenLane Chip Integration](https://openlane.readthedocs.io/en/latest/usage/chip_integration.html)
