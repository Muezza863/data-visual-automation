# 📊 Auto-Viz & Smart Data Cleaner

Aplikasi web berbasis **Streamlit** yang memungkinkan siapa saja — tanpa keahlian teknis — untuk mengunggah dataset CSV/Excel dan langsung mendapatkan laporan kesehatan data, pembersihan otomatis, serta visualisasi interaktif.

---

## ✨ Fitur Utama

| Fitur | Deskripsi |
|:------|:----------|
| **Unggah File** | Mendukung `.csv` (UTF-8 & Latin-1) dan `.xlsx` (sheet pertama). Batas 10 MB / 50.000 baris. |
| **Audit Kesehatan Data** | Laporan dimensi, duplikat, baris rusak, dan kolom dengan nilai kosong — dihitung *sebelum* perubahan apa pun. |
| **Pipeline Pembersihan Cerdas** | Konversi datetime → hapus duplikat → hapus baris rusak → hapus kolom kosong → imputasi numerik (Mean/Median) → imputasi kategori (Modus/"Unknown"). |
| **Log Perubahan Transparan** | Setiap tindakan pembersihan dicatat dengan nilai konkret (contoh: *"Kolom 'Usia' diisi Median (28.0), skew = 1.24"*). |
| **Unduh Data Bersih** | Tombol unduh langsung menghasilkan CSV UTF-8 tanpa index. |
| **Visualisasi Otomatis** | Hingga 6 grafik Plotly Express: Line Chart, Bar Chart, Scatter Plot, Histogram — dipilih berdasarkan tipe kolom. |
| **Zero-Configuration** | Tidak ada tombol, slider, atau pengaturan yang perlu diklik. Hasil muncul otomatis setelah unggah. |

---

## 🚀 Instalasi & Menjalankan Aplikasi

### Prasyarat
- Python **3.9** atau lebih baru
- `pip` (Python package manager)

### Langkah-langkah

```bash
# 1. Clone atau salin folder proyek
cd auto-viz-cleaner

# 2. (Opsional) Buat virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 3. Instal semua dependensi
pip install -r requirements.txt

# 4. Jalankan aplikasi
streamlit run app.py
```

Aplikasi akan terbuka di browser secara otomatis di `http://localhost:8501`.

---

## 📁 Struktur Proyek

```
auto-viz-cleaner/
├── app.py            # File utama: UI + seluruh logika (MVP)
├── requirements.txt  # Daftar dependensi Python
└── README.md         # Dokumentasi ini
```

---

## ⚙️ Batasan File

| Parameter | Nilai |
|:----------|:------|
| Format yang didukung | `.csv`, `.xlsx` |
| Ukuran maksimal | 10 MB |
| Baris maksimal diproses | 50.000 baris pertama |
| Encoding CSV | UTF-8 (otomatis fallback ke Latin-1) |
| Sheet Excel | Hanya sheet pertama |

---

## 🔬 Cara Kerja (How It Works)

### 1. Unggah & Validasi
File diperiksa ukurannya sebelum diproses. CSV dibaca dengan encoding UTF-8 terlebih dahulu; jika gagal, otomatis beralih ke Latin-1. Excel selalu membaca sheet pertama.

### 2. Audit Kesehatan Data
Sebelum mengubah data apa pun, sistem menghitung: jumlah baris & kolom asli, jumlah duplikat, jumlah baris rusak (>50% nilai kosong), dan daftar kolom bermasalah beserta persentase nilai kosongnya.

### 3. Pipeline Pembersihan (berurutan)
1. **Standarisasi tipe**: Kolom teks yang ≥80% nilainya dapat diurai sebagai tanggal akan dikonversi ke `datetime64`.
2. **Hapus duplikat**: Baris yang 100% identik dihapus.
3. **Hapus baris rusak**: Baris dengan >50% nilai kosong dihapus.
4. **Hapus kolom kosong**: Kolom dengan >70% nilai kosong dihapus.
5. **Imputasi numerik**: Skewness dihitung dengan rumus Fisher-Pearson. `|S| ≤ 0.5` → isi dengan **Mean**; `|S| > 0.5` → isi dengan **Median**.
6. **Imputasi kategori**: Missing ≤10% → isi dengan **Modus**; missing >10% → isi dengan `"Unknown"`.

### 4. Auto-Viz Engine
Setiap kolom diklasifikasikan sebagai *Temporal*, *Kategorikal*, *Numerik*, atau *Diabaikan*. Berdasarkan klasifikasi ini, sistem memilih hingga 6 grafik terbaik yang ditampilkan dalam grid 2 kolom.

---

## 🧪 Dataset Uji Sampel

Simpan teks berikut sebagai `sample_dirty.csv` untuk menguji semua fitur pembersihan:

```csv
ID,Tanggal,Produk,Pendapatan,Usia_Pelanggan
1,2024-01-05,Laptop,15000000,25
2,2024-01-12,Handphone,3500000,
3,2024-02-01,Laptop,15000000,25
4,2024-02-01,Laptop,15000000,25
5,2024-02-15,,8000000,42
6,2024-03-10,Tablet,,30
7,2024-03-22,Laptop,12000000,
8,2024-04-01,Handphone,4200000,55
9,2024-04-18,Tablet,7500000,
10,2024-05-05,Laptop,13500000,28
11,2024-05-20,Handphone,3800000,33
12,,,,,
13,2024-06-10,Laptop,14000000,40
14,2024-06-25,Tablet,8200000,
15,2024-07-01,Handphone,4100000,22
```

**Ekspektasi:**
- `st.warning` muncul karena ada nilai kosong & duplikat.
- Baris 3 & 4 (duplikat) dan baris 12 (rusak) akan dihapus.
- Kolom `Pendapatan` dan `Usia_Pelanggan` diimputasi dengan Mean atau Median.
- Kolom `Produk` diimputasi dengan Modus.
- Line Chart (`Tanggal` vs `Pendapatan`), Bar Chart (`Produk` vs `Pendapatan`), dan Histogram akan dirender.

---

## 📦 Dependensi

```
streamlit>=1.28.0
pandas>=2.0.0
numpy>=1.24.0
plotly>=5.17.0
openpyxl>=3.1.0
```
