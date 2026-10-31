# Product Requirements Document (PRD)
**Nama Proyek:** Aplikasi Visualisasi Data Otomatis & Pembersihan Cerdas (*Auto-Viz & Smart Data Cleaner*)  
**Versi Dokumen:** 1.0 (MVP)  
**Target Waktu Pengerjaan:** 3,5 – 5 Jam  
**Status:** Siap Implementasi (*Ready for Development*)

---

## 1. Ringkasan Eksekutif (Executive Summary)
Banyak pengguna—terutama analis pemula, mahasiswa, dan profesional non-teknis—menghadapi hambatan saat melakukan eksplorasi data awal (*Exploratory Data Analysis*). Hambatan tersebut meliputi keharusan membersihkan data kotor secara manual (seperti *missing values* dan duplikasi), menentukan tipe grafik yang tepat, hingga melakukan konfigurasi sumbu (*axis*) pada perangkat lunak BI yang kompleks.

**Auto-Viz & Smart Data Cleaner** hadir sebagai solusi berbasis web satu halaman (*Single-Page Application*) yang memungkinkan pengguna mengunggah file `.csv` atau `.xlsx`. Sistem akan secara otonom mengaudit kesehatan data, melakukan pembersihan dan imputasi statistik secara cerdas, menyediakan opsi unduh data bersih, serta langsung merender visualisasi interaktif yang paling relevan tanpa intervensi manual.

---

## 2. Target Pengguna (Target Audience)
1. **Data Analyst Pemula & Mahasiswa:** Membutuhkan alat bantu cepat untuk melihat profil distribusi data, tren, dan korelasi awal sebelum melakukan pemodelan lebih lanjut.
2. **Profesional Bisnis / Non-Teknis:** Membutuhkan ringkasan visual instan dari laporan operasional/penjualan harian tanpa harus menguasai kode pemrograman atau *tools* rumit seperti Tableau/PowerBI.

---

## 3. Batasan & Lingkup Proyek (Scope & Limitations)

### 3.1. In-Scope (Dalam Lingkup MVP)
* Antarmuka berbasis komponen standar Streamlit (*Clean & Minimalist*) tanpa kustomisasi CSS/JS eksternal.
* Pemrosesan file `.csv` dan `.xlsx` (hanya membaca *sheet* pertama untuk file Excel).
* Deteksi dan pembersihan otomatis untuk *missing values*, duplikasi, dan baris rusak.
* Pembuatan grafik otomatis (Line, Bar, Histogram, Scatter) menggunakan Plotly Express.
* Fitur ekspor/unduh dataset yang telah dibersihkan ke dalam format `.csv`.

### 3.2. Out-of-Scope (Di Luar Lingkup MVP)
* Penyimpanan database permanen (semua pemrosesan dilakukan *in-memory* per sesi).
* Sistem autentikasi pengguna (Login/Register).
* Kustomisasi warna, *font*, atau pengubahan sumbu grafik secara manual oleh pengguna.
* Pemrosesan teks tingkat lanjut (NLP) atau penggabungan beberapa tabel (*multi-table join*).

---

## 4. Spesifikasi Fungsional & Aturan Bisnis (Core Features & Logic)

### 4.1. Modul Unggah & Validasi File (`File Upload & Validation`)
* **Input:** Pengguna mengunggah file berekstensi `.csv` atau `.xlsx`.
* **Batasan Ukuran:** Maksimal **10 MB** atau **50.000 baris** pertama untuk menjamin waktu pemrosesan di bawah 5 detik.
* **Penanganan Encoding:** Untuk file `.csv`, sistem mencoba membaca dengan encoding `utf-8` terlebih dahulu. Jika gagal, otomatis beralih (*fallback*) ke `latin-1`.

### 4.2. Modul Audit Kesehatan Data (`Data Health Check`)
Sebelum mengubah data, sistem memindai *DataFrame* dan mencatat metrik awal berikut:
* Dimensi awal (Jumlah baris $\times$ Jumlah kolom).
* Jumlah baris duplikat identik.
* Jumlah baris rusak parah (baris yang memiliki nilai kosong pada $> 50\%$ kolomnya).
* Daftar kolom yang memiliki *missing values* beserta persentasenya.
* **Output UI:** Menampilkan *Alert Box* (`st.warning` jika ditemukan data kotor, atau `st.success` jika data sudah 100% bersih) beserta ringkasan metrik di atas.

### 4.3. Modul Pembersihan Data Cerdas (`Smart Data Imputation & Cleaning`)
Sistem mengeksekusi langkah-langkah pembersihan secara berurutan (*pipeline*):

1. **Standardisasi Tipe Data:**
   * Mencoba mengonversi kolom bertipe objek/string yang memiliki format tanggal menjadi tipe `datetime64`.
2. **Penghapusan Baris & Kolom Ekstrem:**
   * **Drop Duplicate Rows:** Menghapus seluruh baris yang terdeteksi duplikat 100%.
   * **Drop Corrupted Rows:** Menghapus baris yang memiliki nilai valid kurang dari $50\%$ total kolom (`thresh = int(total_cols * 0.5)`).
   * **Drop Empty Columns:** Menghapus kolom yang memiliki nilai kosong (*missing values*) $> 70\%$ dari total baris karena dianggap tidak informatif.
3. **Imputasi Kolom Numerik (`int64`, `float64`):**
   * Sistem menghitung nilai kemiringan distribusi (*skewness*) dengan rumus Pearson/Fisher-Pearson pada kolom terkait:
     $$\text{Skewness } (S) = \frac{\sum_{i=1}^{N} (Y_i - \bar{Y})^3 / N}{s^3}$$
   * **Jika $|S| \le 0.5$ (Distribusi Normal/Simetris):** Nilai kosong diisi menggunakan **Mean** (rata-rata).
   * **Jika $|S| > 0.5$ (Distribusi Miring / Terdapat Outlier):** Nilai kosong diisi menggunakan **Median** (nilai tengah).
4. **Imputasi Kolom Kategori / Teks (`object`, `category`):**
   * Jika persentase kosong $\le 10\%$, isi menggunakan **Modus** (nilai yang paling sering muncul).
   * Jika persentase kosong $> 10\%$, isi menggunakan label string baru: `"Unknown"`.
5. **Log Perubahan & Ekspor:**
   * Menampilkan daftar tindakan yang telah diambil (contoh: *"Kolom `Usia` diisi dengan Median (28.0) karena distribusi miring (skew = 1.24)"*).
   * Menyediakan tombol **Download Cleaned CSV**.

### 4.4. Modul Deteksi Kolom & Auto-Visualization (`Auto-Viz Engine`)
Sistem mengklasifikasikan setiap kolom yang tersisa ke dalam 4 peran sebelum memilih grafik:

| Peran Kolom | Kriteria Deteksi | Tindakan Sistem |
| :--- | :--- | :--- |
| **Temporal (Waktu)** | Tipe data `datetime64` atau nama kolom mengandung kata kunci (`date`, `time`, `tahun`, `bulan`, `tanggal`). | Digunakan sebagai sumbu $X$ pada *Line Chart*. |
| **Kategorikal** | Tipe `object`/`category` dengan jumlah nilai unik (*cardinality*) $2 \le \text{unik} \le 15$. | Digunakan sebagai sumbu $X$ atau pengelompok warna pada *Bar Chart*. |
| **Numerik** | Tipe `int64` atau `float64` dengan jumlah nilai unik $> 2$ (bukan sekadar ID urut). | Digunakan sebagai sumbu $Y$ (agregasi) atau pasangan sumbu $X\text{-}Y$. |
| **Diabaikan (Ignored)** | Kolom konstan ($\text{unik} \le 1$), kolom ID ($100\%$ unik pada baris $> 50$), atau teks bebas dengan kardinalitas $> 15$. | Dikecualikan dari pembuatan grafik otomatis. |

#### Aturan Pemilihan & Pembatasan Grafik (Chart Selection Rules)
Untuk mencegah halaman web *freeze* akibat terlalu banyak kombinasi kolom, sistem membatasi maksimal **6 grafik terbaik** yang dibagi dalam 4 kategori:

1. **Tren Waktu (Line Chart) — Maksimal 2 Grafik:**
   * **Syarat:** Minimal 1 kolom *Temporal* + 1 kolom *Numerik*.
   * **Logika:** Mengagregasi rata-rata/jumlah nilai numerik berdasarkan urutan waktu.
2. **Komparasi Kategori (Bar Chart) — Maksimal 2 Grafik:**
   * **Syarat:** Minimal 1 kolom *Kategorikal* + 1 kolom *Numerik*.
   * **Logika:** Menampilkan rata-rata (*mean*) atau total (*sum*) kolom numerik untuk setiap kategori, diurutkan dari nilai terbesar ke terkecil.
3. **Korelasi Antar-Angka (Scatter Plot) — Maksimal 1 Grafik:**
   * **Syarat:** Minimal 2 kolom *Numerik*.
   * **Logika:** Jika terdapat $> 2$ kolom numerik, sistem menghitung matriks korelasi Pearson ($r$) dan memilih **1 pasang kolom dengan nilai $|r|$ tertinggi** (tetapi $< 1.0$) untuk ditampilkan sebagai *Scatter Plot*.
4. **Distribusi Data (Histogram) — Maksimal 1 Grafik:**
   * **Syarat:** Minimal 1 kolom *Numerik*.
   * **Logika:** Menampilkan distribusi frekuensi dari kolom numerik yang memiliki varians paling menarik (atau kolom numerik pertama jika tidak ada kategori/waktu).

---

## 5. Kebutuhan Non-Fungsional (Non-Functional Requirements)
* **Performa:** Waktu muat dari unggah file (ukuran $\le 5\text{ MB}$) hingga seluruh grafik ter-render harus di bawah **3 detik**.
* **Keandalan (Reliability):** Aplikasi tidak boleh *crash* (menampilkan *Traceback Error* merah di Streamlit) jika pengguna mengunggah file kosong, file yang hanya berisi teks tanpa angka, atau file dengan format rusak. Semua error harus ditangkap dengan blok `try-except` dan ditampilkan melalui pesan `st.error()` yang ramah pengguna.
* **Kemudahan Penggunaan (Usability):** *Zero-configuration*. Pengguna tidak perlu menekan tombol apa pun selain tombol *Browse File*.

---

## 6. Arsitektur & Tech Stack
* **Bahasa Pemrograman:** Python 3.9+
* **Web Framework:** `streamlit` (Antarmuka reaktif dan tata letak kolom).
* **Pengolahan Data & Statistik:** `pandas`, `numpy`, `openpyxl` (engine pembaca file `.xlsx`).
* **Engine Visualisasi:** `plotly.express` (mendukung *zoom*, *hover tooltip*, dan ekspor gambar `.png` secara bawaan).

### Struktur Direktori Proyek (Sederhana)
```text
auto-viz-cleaner/
├── app.py                 # File utama aplikasi (UI + Logic terintegrasi untuk MVP)
├── requirements.txt       # Daftar pustaka: streamlit, pandas, numpy, plotly, openpyxl
└── README.md              # Dokumentasi cara menjalankan proyek
```

---

## 7. Alur Pengguna & Tata Letak Antarmuka (User Journey & Wireframe)

### 7.1. Alur Pengguna (User Flow)
1. Pengguna membuka URL aplikasi Streamlit.
2. Pengguna memilih dan mengunggah file `.csv` atau `.xlsx`.
3. Sistem memvalidasi file $\rightarrow$ Menampilkan indikator *spinner* `"Memindai dan membersihkan data..."`.
4. Pengguna melihat kotak laporan **Data Health & Cleaning Log** (melihat apa saja yang diperbaiki oleh sistem).
5. Pengguna melihat pratinjau tabel (*Before vs After* atau tabel bersih beserta tombol unduh).
6. Pengguna menggulir ke bawah dan langsung berinteraksi dengan 2 hingga 6 grafik visualisasi otomatis yang tersusun rapi dalam grid 2 kolom.

### 7.2. Rancangan Tata Letak Layar (Wireframe Teks)
```text
+-----------------------------------------------------------------------+
| 📊 AUTO-VIZ & SMART DATA CLEANER                                      |
| Unggah dataset Anda, biarkan sistem membersihkan dan memvisualisasikan|
+-----------------------------------------------------------------------+
| [ Drag and drop file here (.csv, .xlsx) ]              [Browse files] |
+-----------------------------------------------------------------------+
| ⚠️ PERINGATAN KESEHATAN DATA: Ditemukan 15 nilai kosong & 2 duplikat. |
| ✅ Pembersihan otomatis selesai! (Klik untuk melihat detail log)      |
|    - Menghapus 2 baris duplikat.                                      |
|    - Kolom 'Pendapatan': Mengisi 12 nilai kosong dengan Median (4500) |
+-----------------------------------------------------------------------+
| 📋 PRATINJAU DATA BERSIH (Menampilkan 100 baris pertama)              |
| +------+------------+--------------+------------+                     |
| | ID   | Tanggal    | Kategori     | Pendapatan |                     |
| +------+------------+--------------+------------+                     |
| [ ⬇️ Unduh Data Bersih (.csv) ]                                       |
+-----------------------------------------------------------------------+
| 📈 VISUALISASI OTOMATIS                                               |
| +---------------------------------+ +-------------------------------+ |
| | Line Chart: Tren Pendapatan     | | Bar Chart: Rata-rata per Kat. | |
| |         /\                      | |   ||                          | |
| |     /\_/  \                     | |   ||  ||                      | |
| +---------------------------------+ +-------------------------------+ |
| +---------------------------------+ +-------------------------------+ |
| | Scatter: Usia vs Pendapatan     | | Histogram: Distribusi Usia    | |
| |    .  . .                       | |     _                         | |
| |  .  .                           | |   _| |_                       | |
| +---------------------------------+ +-------------------------------+ |
+-----------------------------------------------------------------------+
```

---

## 8. Rencana Pengerjaan (Timeline 4 Jam)

| Fase | Estimasi Waktu | Aktivitas Utama |
| :--- | :--- | :--- |
| **Fase 1: Setup & File Loader** | 30 Menit | Inisialisasi environment, instalasi pustaka, pembuatan UI unggah file, dan penanganan pembacaan `.csv`/`.xlsx` beserta *error handling*. |
| **Fase 2: Data Health & Smart Cleaner** | 90 Menit | Pembuatan fungsi deteksi *missing values*, perhitungan *skewness*, imputasi Mean/Median/Modus, penghapusan baris rusak, serta pembuatan *log* perubahan. |
| **Fase 3: Auto-Viz Engine** | 90 Menit | Pembuatan fungsi klasifikasi tipe kolom (Waktu, Kategori, Numerik, ID) dan pembuatan grafik otomatis menggunakan Plotly Express dalam *layout* 2 kolom. |
| **Fase 4: Testing & Polishing** | 30 Menit | Pengujian menggunakan 3 dataset berbeda (data bersih, data sangat kotor, data tanpa kolom tanggal), perapihan tampilan metrik Streamlit, dan penambahan tombol *Download*. |